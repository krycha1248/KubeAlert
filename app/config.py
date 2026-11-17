"""
Configuration module for KubeAlert.
Parses environment variables according to 12-Factor principles.
"""

import os
import logging

logger = logging.getLogger("kubealert.config")


class Config:
    # HTTP Server
    PORT = int(os.environ.get("PORT", "8080"))
    APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")

    # Kubernetes In-Cluster Settings
    KUBERNETES_SERVICE_HOST = os.environ.get("KUBERNETES_SERVICE_HOST")
    KUBERNETES_SERVICE_PORT = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
    SERVICE_ACCOUNT_TOKEN_PATH = os.environ.get(
        "K8S_TOKEN_PATH", "/var/run/secrets/kubernetes.io/serviceaccount/token"
    )
    SERVICE_ACCOUNT_CA_PATH = os.environ.get(
        "K8S_CA_PATH", "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    )

    # Namespaces filtering
    # Empty string means monitor all namespaces (cluster-wide)
    raw_monitored = os.environ.get("MONITORED_NAMESPACES", "").strip()
    MONITORED_NAMESPACES = [ns.strip() for ns in raw_monitored.split(",") if ns.strip()]

    raw_ignored = os.environ.get("IGNORED_NAMESPACES", "kube-system,local-path-storage").strip()
    IGNORED_NAMESPACES = set(ns.strip() for ns in raw_ignored.split(",") if ns.strip())

    # Alert rules & Anti-Flapping
    ALERT_COOLDOWN_SECONDS = int(os.environ.get("ALERT_COOLDOWN_SECONDS", "900"))  # 15 minutes default
    INCLUDE_LOGS = os.environ.get("INCLUDE_LOGS", "true").lower() in ("true", "1", "yes")
    MAX_LOG_LINES = int(os.environ.get("MAX_LOG_LINES", "15"))

    # SMTP Settings
    SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER", "").strip()
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").strip()
    SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")
    SMTP_USE_SSL = os.environ.get("SMTP_USE_SSL", "false").lower() in ("true", "1", "yes")
    ALERT_FROM_EMAIL = os.environ.get("ALERT_FROM_EMAIL", "kubealert@wlodek.net").strip()
    ALERT_TO_EMAIL = os.environ.get("ALERT_TO_EMAIL", "").strip()

    @classmethod
    def is_smtp_configured(cls) -> bool:
        return bool(cls.SMTP_HOST and cls.ALERT_TO_EMAIL)

    @classmethod
    def should_monitor_namespace(cls, namespace: str) -> bool:
        if namespace in cls.IGNORED_NAMESPACES:
            return False
        if cls.MONITORED_NAMESPACES:
            return namespace in cls.MONITORED_NAMESPACES
        return True
