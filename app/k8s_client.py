"""
Kubernetes API client module using Python standard library.
Supports In-Cluster authentication, Watch API streaming, and log retrieval.
"""

import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Generator, Optional, Tuple, Dict, Any

from config import Config

logger = logging.getLogger("kubealert.k8s")


class K8sClient:
    def __init__(self):
        self.host = Config.KUBERNETES_SERVICE_HOST
        self.port = Config.KUBERNETES_SERVICE_PORT
        self.token_path = Config.SERVICE_ACCOUNT_TOKEN_PATH
        self.ca_path = Config.SERVICE_ACCOUNT_CA_PATH
        self.base_url = f"https://{self.host}:{self.port}" if self.host else None
        self._token: Optional[str] = None
        self._ssl_context: Optional[ssl.SSLContext] = None

    def is_in_cluster(self) -> bool:
        return bool(self.host and os.path.exists(self.token_path))

    def _get_token(self) -> str:
        if not self._token and os.path.exists(self.token_path):
            with open(self.token_path, "r", encoding="utf-8") as f:
                self._token = f.read().strip()
        return self._token or ""

    def _get_ssl_context(self) -> ssl.SSLContext:
        if not self._ssl_context:
            if os.path.exists(self.ca_path):
                self._ssl_context = ssl.create_default_context(cafile=self.ca_path)
            else:
                self._ssl_context = ssl.create_default_context()
                self._ssl_context.check_hostname = False
                self._ssl_context.verify_mode = ssl.CERT_NONE
        return self._ssl_context

    def _build_request(self, endpoint: str, query_params: Optional[Dict[str, str]] = None) -> urllib.request.Request:
        url = f"{self.base_url}{endpoint}"
        if query_params:
            url += f"?{urllib.parse.urlencode(query_params)}"

        headers = {
            "Authorization": f"Bearer {self._get_token()}",
            "Accept": "application/json",
            "User-Agent": f"KubeAlert/{Config.APP_VERSION}"
        }
        return urllib.request.Request(url, headers=headers)

    def get_version(self) -> Dict[str, Any]:
        if not self.is_in_cluster():
            return {"status": "standalone", "error": "Not running in cluster"}

        req = self._build_request("/version")
        with urllib.request.urlopen(req, context=self._get_ssl_context(), timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_pod_logs(self, namespace: str, pod_name: str, container_name: str, tail_lines: int = 15) -> str:
        """Retrieves the last lines of logs for a container."""
        if not self.is_in_cluster():
            return "Logs unavailable (standalone mode)"

        endpoint = f"/api/v1/namespaces/{namespace}/pods/{pod_name}/log"
        params = {
            "container": container_name,
            "tailLines": str(tail_lines)
        }
        try:
            req = self._build_request(endpoint, params)
            with urllib.request.urlopen(req, context=self._get_ssl_context(), timeout=5) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as exc:
            logger.debug("Could not fetch logs for pod %s/%s container %s: %s", namespace, pod_name, container_name, exc)
            return f"(Unable to retrieve container logs: {exc})"

    def list_pods(self, namespace: Optional[str] = None) -> Tuple[list, str]:
        """Lists pods and returns (pod_list, latest_resource_version)."""
        if namespace:
            endpoint = f"/api/v1/namespaces/{namespace}/pods"
        else:
            endpoint = "/api/v1/pods"

        req = self._build_request(endpoint)
        with urllib.request.urlopen(req, context=self._get_ssl_context(), timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            resource_version = data.get("metadata", {}).get("resourceVersion", "")
            items = data.get("items", [])
            return items, resource_version

    def watch_pods(
        self,
        resource_version: Optional[str] = None,
        namespace: Optional[str] = None,
        timeout_seconds: int = 300
    ) -> Generator[Tuple[str, Dict[str, Any], str], None, None]:
        """
        Streams Pod events from Kubernetes Watch API line by line.
        Yields (event_type, pod_object, resource_version).
        """
        if namespace:
            endpoint = f"/api/v1/namespaces/{namespace}/pods"
        else:
            endpoint = "/api/v1/pods"

        params = {
            "watch": "true",
            "timeoutSeconds": str(timeout_seconds)
        }
        if resource_version:
            params["resourceVersion"] = resource_version

        req = self._build_request(endpoint, params)
        # Using a socket timeout slightly larger than timeoutSeconds to catch idle disconnects
        with urllib.request.urlopen(req, context=self._get_ssl_context(), timeout=timeout_seconds + 30) as resp:
            for raw_line in resp:
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    event_type = event.get("type", "UNKNOWN")
                    obj = event.get("object", {})

                    if event_type == "ERROR":
                        # e.g. 410 Gone when resourceVersion is too old
                        logger.warning("Watch API returned ERROR event: %s", obj.get("message"))
                        return

                    rv = obj.get("metadata", {}).get("resourceVersion", "")
                    yield event_type, obj, rv
                except json.JSONDecodeError:
                    continue
