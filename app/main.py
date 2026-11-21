#!/usr/bin/env python3
"""
KubeAlert - Kubernetes Pod Watcher & Email Notification Service
Monitors Pod lifecycle events in near real-time via Kubernetes Watch API,
filters and detects critical failures (CrashLoopBackOff, OOMKilled, ImagePullBackOff),
and sends automated email notifications to administrators via SMTP.
"""

import json
import logging
import os
import signal
import socket
import sys
import threading
import time
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any

from config import Config
from k8s_client import K8sClient
from analyzer import PodAnalyzer
from notifier import EmailNotifier
from store import ContainerStore

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [%(name)s] %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%SZ',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("kubealert.main")

HOSTNAME = socket.gethostname()
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "index.html")

# Global state for health and telemetry
app_state: Dict[str, Any] = {
    "version": Config.APP_VERSION,
    "hostname": HOSTNAME,
    "k8s_connected": False,
    "k8s_version": None,
    "watcher_running": False,
    "watcher_errors": 0,
    "alerts_dispatched": 0,
    "smtp_configured": Config.is_smtp_configured(),
    "last_seen_resource_version": None,
}

container_store = ContainerStore()
shutdown_event = threading.Event()


def get_index_html() -> str:
    """Loads Web UI template with graceful fallback."""
    if os.path.exists(TEMPLATE_PATH):
        try:
            with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error("Error reading template %s: %s", TEMPLATE_PATH, e)
    return """<!DOCTYPE html>
<html>
<head><title>KubeAlert</title></head>
<body style="font-family: sans-serif; padding: 40px; background: #0b0f19; color: #fff;">
  <h2>KubeAlert</h2>
  <p>Web UI template file is missing. Visit <a href="/api" style="color: #6366f1;">/api</a> for JSON output.</p>
</body>
</html>"""


class AppHandler(BaseHTTPRequestHandler):
    """HTTP server handler for Web UI, API, health probes, and operational endpoints."""

    def log_message(self, format_str, *args):
        logger.debug("%s - %s", self.client_address[0], format_str % args)

    def _send_json(self, status_code: int, data: dict):
        response_bytes = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def _send_html(self, status_code: int, html_content: str):
        response_bytes = html_content.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/ui", "/index.html"):
            self._send_html(200, get_index_html())
        elif path in ("/api", "/api/", "/api/containers"):
            payload = container_store.get_api_payload(
                cluster_connected=app_state["k8s_connected"],
                cluster_version=app_state["k8s_version"],
                in_cluster=K8sClient().is_in_cluster(),
            )
            self._send_json(200, payload)
        elif path == "/info":
            self._send_json(200, {
                "app": "KubeAlert",
                "version": Config.APP_VERSION,
                "status": "running",
                "hostname": HOSTNAME,
                "state": app_state,
                "monitored_namespaces": Config.MONITORED_NAMESPACES or "all",
                "ignored_namespaces": list(Config.IGNORED_NAMESPACES),
                "cooldown_seconds": Config.ALERT_COOLDOWN_SECONDS,
            })
        elif path == "/healthz":
            self._send_json(200, {"status": "healthy", "hostname": HOSTNAME})
        elif path == "/ready":
            self._send_json(200, {"status": "ready", "hostname": HOSTNAME})
        elif path == "/status":
            self._send_json(200, app_state)
        elif path == "/k8s":
            self._send_json(200, {
                "connected": app_state["k8s_connected"],
                "version": app_state["k8s_version"],
                "in_cluster": K8sClient().is_in_cluster(),
            })
        else:
            self._send_json(404, {"error": "Not Found", "path": self.path})


def pod_watcher_loop(k8s: K8sClient, analyzer: PodAnalyzer, notifier: EmailNotifier):
    """Background worker that continuously watches Kubernetes Pods and dispatches alerts."""
    logger.info("Initializing Kubernetes Pod Watcher thread...")

    while not shutdown_event.is_set():
        if not k8s.is_in_cluster():
            logger.info("Running in standalone mode (outside Kubernetes cluster). Watcher sleeping 30s...")
            app_state["watcher_running"] = False
            container_store.clear()
            shutdown_event.wait(30)
            continue

        try:
            # 1. Connect and verify cluster version
            version_info = k8s.get_version()
            app_state["k8s_connected"] = True
            app_state["k8s_version"] = version_info.get("gitVersion")
            logger.info("Connected to Kubernetes API (version %s).", app_state["k8s_version"])

            # 2. List pods to establish baseline and obtain initial resourceVersion
            logger.info("Performing initial Pod list to synchronize resourceVersion...")
            initial_pods, resource_version = k8s.list_pods()
            app_state["last_seen_resource_version"] = resource_version
            logger.info("Retrieved %d pods, baseline resourceVersion: %s", len(initial_pods), resource_version)

            # Synchronize container store with active pods
            container_store.sync_pods(initial_pods)

            # Analyze any currently failing pods on startup
            for pod in initial_pods:
                issues = analyzer.analyze_pod(pod)
                for issue in issues:
                    logs = None
                    if Config.INCLUDE_LOGS and not issue.container_name.startswith("["):
                        logs = k8s.get_pod_logs(issue.namespace, issue.pod_name, issue.container_name, Config.MAX_LOG_LINES)
                    notifier.send_alert(issue, logs)
                    app_state["alerts_dispatched"] += 1

            # 3. Stream Pod updates in real-time via Watch API
            app_state["watcher_running"] = True
            logger.info("Starting real-time Pod Watch API stream from resourceVersion %s...", resource_version)

            for event_type, pod, rv in k8s.watch_pods(resource_version=resource_version):
                if shutdown_event.is_set():
                    break

                if rv:
                    app_state["last_seen_resource_version"] = rv
                    resource_version = rv

                # Update container store based on watch event
                if event_type in ("ADDED", "MODIFIED"):
                    container_store.update_pod(pod)
                    issues = analyzer.analyze_pod(pod)
                    for issue in issues:
                        logs = None
                        if Config.INCLUDE_LOGS and not issue.container_name.startswith("["):
                            logs = k8s.get_pod_logs(issue.namespace, issue.pod_name, issue.container_name, Config.MAX_LOG_LINES)
                        notifier.send_alert(issue, logs)
                        app_state["alerts_dispatched"] += 1
                elif event_type == "DELETED":
                    container_store.remove_pod(pod)

            logger.info("Watch stream closed by server. Reconnecting in 2 seconds...")
            time.sleep(2)

        except Exception as exc:
            app_state["watcher_errors"] += 1
            app_state["k8s_connected"] = False
            app_state["watcher_running"] = False
            logger.error("Error in Watcher loop: %s. Reconnecting in 5 seconds...", exc)
            shutdown_event.wait(5)


def main():
    logger.info("Starting KubeAlert %s on host %s (Port %d)", Config.APP_VERSION, HOSTNAME, Config.PORT)

    k8s = K8sClient()
    analyzer = PodAnalyzer()
    notifier = EmailNotifier()

    if notifier.is_configured():
        logger.info("SMTP configured: Host %s:%d, Destination: %s", Config.SMTP_HOST, Config.SMTP_PORT, Config.ALERT_TO_EMAIL)
    else:
        logger.warning("SMTP is NOT fully configured (missing SMTP_HOST or ALERT_TO_EMAIL). Alerts will be logged to stdout.")

    # Start watcher in background daemon thread
    watcher_thread = threading.Thread(
        target=pod_watcher_loop,
        args=(k8s, analyzer, notifier),
        name="k8s-pod-watcher",
        daemon=True
    )
    watcher_thread.start()

    # Start HTTP server for probes and telemetry
    server_address = ("0.0.0.0", Config.PORT)
    httpd = HTTPServer(server_address, AppHandler)

    def handle_exit(signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info("Received signal %s, initiating graceful shutdown...", sig_name)
        shutdown_event.set()
        httpd.server_close()
        logger.info("KubeAlert stopped cleanly.")
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_exit)
    signal.signal(signal.SIGINT, handle_exit)

    logger.info("HTTP server listening on 0.0.0.0:%d", Config.PORT)
    try:
        httpd.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        shutdown_event.set()
        httpd.server_close()


if __name__ == "__main__":
    main()
