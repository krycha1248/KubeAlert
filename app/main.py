#!/usr/bin/env python3
"""
Simple cloud-native HTTP application designed for Kubernetes.
Includes health check endpoints and graceful shutdown handling.
"""

import json
import logging
import os
import signal
import socket
import sys
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


class AppHandler(BaseHTTPRequestHandler):
    """HTTP request handler for application routes and health probes."""

    def log_message(self, format_str, *args):
        # Override default server logging to use standard logger format
        logger.info("%s - - %s", self.client_address[0], format_str % args)

    def _send_json_response(self, status_code: int, data: dict):
        response_bytes = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def do_GET(self):
        if self.path == "/" or self.path == "/info":
            # Main application information endpoint
            self._send_json_response(200, {
                "status": "ok",
                "app": "KubeAlert",
                "version": APP_VERSION,
                "hostname": HOSTNAME,
                "message": "Hello from Kubernetes!"
            })
        elif self.path == "/healthz":
            # Kubernetes liveness probe endpoint
            self._send_json_response(200, {
                "status": "healthy",
                "hostname": HOSTNAME
            })
        elif self.path == "/ready":
            # Kubernetes readiness probe endpoint
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

    logger.info("Starting KubeAlert app version %s on port %d (host: %s)", APP_VERSION, APP_PORT, HOSTNAME)
    try:
        httpd.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run_server()