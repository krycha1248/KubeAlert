#!/usr/bin/env python3
"""
KubeAlert Application
Lightweight cloud-native HTTP service that connects to Kubernetes API.
"""

import json
import logging
import os
import signal
import socket
import ssl
import sys
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

# Configure structured logging to stdout for Kubernetes log collectors
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%SZ',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("kubealert-app")

APP_PORT = int(os.environ.get("PORT", 8080))
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")
HOSTNAME = socket.gethostname()

# Global state for Kubernetes API connection
k8s_status = {
    "connected": False,
    "mode": "disconnected",
    "cluster_version": None,
    "endpoint": None,
    "error": None
}


def connect_to_kube_api() -> dict:
    """
    Connects to the Kubernetes API server using the in-cluster ServiceAccount credentials.
    Logs success or error and returns connection metadata.
    """
    token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    ca_path = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    k8s_host = os.environ.get("KUBERNETES_SERVICE_HOST")
    k8s_port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")

    if not k8s_host or not os.path.exists(token_path):
        msg = "Running outside Kubernetes cluster (in-cluster ServiceAccount token not found)."
        logger.info("%s KubeAPI live connection skipped.", msg)
        k8s_status["connected"] = False
        k8s_status["mode"] = "standalone"
        k8s_status["error"] = msg
        return k8s_status

    api_url = f"https://{k8s_host}:{k8s_port}/version"
    try:
        with open(token_path, "r", encoding="utf-8") as f:
            token = f.read().strip()

        ssl_ctx = ssl.create_default_context(cafile=ca_path)
        req = urllib.request.Request(
            api_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json"
            }
        )

        with urllib.request.urlopen(req, context=ssl_ctx, timeout=10) as response:
            if response.status == 200:
                payload = json.loads(response.read().decode("utf-8"))
                git_version = payload.get("gitVersion", "unknown")
                platform = payload.get("platform", "unknown")
                k8s_status["connected"] = True
                k8s_status["mode"] = "in-cluster"
                k8s_status["cluster_version"] = git_version
                k8s_status["endpoint"] = f"https://{k8s_host}:{k8s_port}"
                k8s_status["error"] = None

                logger.info(
                    "Connected successfully to Kubernetes API at https://%s:%s! "
                    "Cluster version: %s (platform: %s)",
                    k8s_host, k8s_port, git_version, platform
                )
            else:
                raise RuntimeError(f"Unexpected HTTP status {response.status} from KubeAPI")

    except Exception as exc:
        k8s_status["connected"] = False
        k8s_status["mode"] = "in-cluster"
        k8s_status["error"] = str(exc)
        logger.error("Failed to connect to Kubernetes API server: %s", exc)

    return k8s_status


class AppHandler(BaseHTTPRequestHandler):
    """HTTP request handler for application routes and health probes."""

    def log_message(self, format_str, *args):
        logger.info("%s - - %s", self.client_address[0], format_str % args)

    def _send_json_response(self, status_code: int, data: dict):
        response_bytes = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def do_GET(self):
        if self.path in ("/", "/info"):
            self._send_json_response(200, {
                "status": "ok",
                "app": "KubeAlert",
                "version": APP_VERSION,
                "hostname": HOSTNAME,
                "kubernetes": k8s_status,
                "message": "Hello from KubeAlert on Kubernetes!"
            })
        elif self.path == "/k8s":
            self._send_json_response(200, k8s_status)
        elif self.path == "/healthz":
            # Kubernetes liveness probe
            self._send_json_response(200, {
                "status": "healthy",
                "hostname": HOSTNAME
            })
        elif self.path == "/ready":
            # Kubernetes readiness probe
            self._send_json_response(200, {
                "status": "ready",
                "hostname": HOSTNAME
            })
        else:
            self._send_json_response(404, {
                "error": "Not Found",
                "path": self.path
            })


def run_server():
    # Attempt connection to Kubernetes API on startup
    connect_to_kube_api()

    server_address = ("0.0.0.0", APP_PORT)
    httpd = HTTPServer(server_address, AppHandler)

    def shutdown_signal_handler(signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info("Received %s signal, initiating graceful shutdown...", sig_name)
        httpd.server_close()
        logger.info("Server stopped.")
        sys.exit(0)

    # Register POSIX signal handlers for Kubernetes pod lifecycle management
    signal.signal(signal.SIGTERM, shutdown_signal_handler)
    signal.signal(signal.SIGINT, shutdown_signal_handler)

    logger.info("Starting KubeAlert version %s on port %d (host: %s)", APP_VERSION, APP_PORT, HOSTNAME)
    try:
        httpd.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run_server()
