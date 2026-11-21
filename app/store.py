"""
Store module for KubeAlert.
Maintains thread-safe in-memory state of Kubernetes containers and pods.
"""

import threading
import time
from typing import Dict, List, Any, Optional, Tuple
from config import Config

CRITICAL_WAITING_REASONS = {
    "CrashLoopBackOff",
    "ImagePullBackOff",
    "ErrImagePull",
    "CreateContainerConfigError",
    "CreateContainerError",
    "InvalidImageName",
    "ContainerCannotRun",
}

CRITICAL_TERMINATED_REASONS = {
    "OOMKilled",
    "Error",
    "ContainerCannotRun",
}


class ContainerStore:
    """Thread-safe in-memory store for Kubernetes pod and container status."""

    def __init__(self):
        self._lock = threading.RLock()
        # Key: (namespace, pod_name) -> list of container dicts
        self._pods: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._last_updated: float = time.time()

    def clear(self):
        """Clears all stored pods."""
        with self._lock:
            self._pods.clear()
            self._last_updated = time.time()

    def sync_pods(self, pod_items: List[dict]):
        """Synchronizes the store with a full list of pods from list_pods."""
        with self._lock:
            new_pods: Dict[Tuple[str, str], Dict[str, Any]] = {}
            for pod in pod_items:
                parsed = self._parse_pod(pod)
                if parsed:
                    key = (parsed["namespace"], parsed["pod_name"])
                    new_pods[key] = parsed
            self._pods = new_pods
            self._last_updated = time.time()

    def update_pod(self, pod: dict):
        """Adds or updates a pod in the store."""
        with self._lock:
            parsed = self._parse_pod(pod)
            if parsed:
                key = (parsed["namespace"], parsed["pod_name"])
                self._pods[key] = parsed
                self._last_updated = time.time()

    def remove_pod(self, pod: dict):
        """Removes a pod from the store upon deletion."""
        with self._lock:
            metadata = pod.get("metadata", {})
            namespace = metadata.get("namespace", "default")
            pod_name = metadata.get("name", "unknown")
            key = (namespace, pod_name)
            if key in self._pods:
                del self._pods[key]
                self._last_updated = time.time()

    def _parse_pod(self, pod: dict) -> Optional[Dict[str, Any]]:
        metadata = pod.get("metadata", {})
        namespace = metadata.get("namespace", "default")
        pod_name = metadata.get("name", "unknown")

        if not Config.should_monitor_namespace(namespace):
            return None

        status = pod.get("status", {})
        spec = pod.get("spec", {})
        phase = status.get("phase", "Unknown")
        pod_ip = status.get("podIP")
        node_name = spec.get("nodeName")
        created_at = metadata.get("creationTimestamp")

        containers: List[Dict[str, Any]] = []

        # Map specs for image fallbacks
        spec_containers = {c.get("name"): c for c in spec.get("containers", [])}
        spec_init_containers = {c.get("name"): c for c in spec.get("initContainers", [])}

        raw_statuses: List[Tuple[dict, bool]] = [
            (cs, False) for cs in status.get("containerStatuses", [])
        ] + [
            (cs, True) for cs in status.get("initContainerStatuses", [])
        ]

        if not raw_statuses:
            # If pod status is not yet populated by kubelet, populate from spec
            for c_spec in spec.get("containers", []):
                containers.append({
                    "namespace": namespace,
                    "pod_name": pod_name,
                    "container_name": c_spec.get("name", "unknown"),
                    "image": c_spec.get("image", ""),
                    "is_init": False,
                    "ready": False,
                    "restart_count": 0,
                    "state": "waiting",
                    "reason": "Pending",
                    "message": "Pod container status is pending initialization.",
                    "exit_code": None,
                    "started_at": None,
                    "finished_at": None,
                    "pod_phase": phase,
                    "pod_ip": pod_ip,
                    "node_name": node_name,
                    "created_at": created_at,
                    "unhealthy": phase in ("Failed", "Unknown"),
                })
        else:
            for cs, is_init in raw_statuses:
                c_name = cs.get("name", "unknown")
                spec_ref = spec_init_containers.get(c_name) if is_init else spec_containers.get(c_name)
                image = cs.get("image") or (spec_ref.get("image") if spec_ref else "")
                ready = bool(cs.get("ready", False))
                restart_count = int(cs.get("restartCount", 0))

                state_dict = cs.get("state", {})
                last_state_dict = cs.get("lastState", {})

                state_name = "unknown"
                reason = ""
                message = ""
                exit_code = None
                started_at = None
                finished_at = None

                if "running" in state_dict:
                    state_name = "running"
                    reason = "Running"
                    started_at = state_dict["running"].get("startedAt")
                elif "waiting" in state_dict:
                    state_name = "waiting"
                    reason = state_dict["waiting"].get("reason", "Waiting")
                    message = state_dict["waiting"].get("message", "")
                elif "terminated" in state_dict:
                    state_name = "terminated"
                    reason = state_dict["terminated"].get("reason", "Terminated")
                    message = state_dict["terminated"].get("message", "")
                    exit_code = state_dict["terminated"].get("exitCode")
                    started_at = state_dict["terminated"].get("startedAt")
                    finished_at = state_dict["terminated"].get("finishedAt")

                # If container is waiting with CrashLoopBackOff, check lastState for previous exit code/reason
                if state_name == "waiting" and "terminated" in last_state_dict:
                    last_term = last_state_dict["terminated"]
                    if exit_code is None:
                        exit_code = last_term.get("exitCode")
                    if not message and last_term.get("message"):
                        message = f"Previous termination: {last_term.get('message')}"

                # Determine health
                is_unhealthy = False
                if reason in CRITICAL_WAITING_REASONS:
                    is_unhealthy = True
                elif reason in CRITICAL_TERMINATED_REASONS:
                    is_unhealthy = True
                elif state_name == "terminated" and exit_code is not None and exit_code != 0:
                    is_unhealthy = True
                elif phase in ("Failed", "Unknown"):
                    is_unhealthy = True
                elif not ready and restart_count > 0:
                    is_unhealthy = True

                containers.append({
                    "namespace": namespace,
                    "pod_name": pod_name,
                    "container_name": c_name,
                    "image": image,
                    "is_init": is_init,
                    "ready": ready,
                    "restart_count": restart_count,
                    "state": state_name,
                    "reason": reason,
                    "message": message,
                    "exit_code": exit_code,
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "pod_phase": phase,
                    "pod_ip": pod_ip,
                    "node_name": node_name,
                    "created_at": created_at,
                    "unhealthy": is_unhealthy,
                })

        return {
            "namespace": namespace,
            "pod_name": pod_name,
            "phase": phase,
            "containers": containers,
        }

    def get_api_payload(
        self,
        cluster_connected: bool,
        cluster_version: Optional[str],
        in_cluster: bool,
        error_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """Builds the full API payload with summary, cluster metadata, and containers."""
        with self._lock:
            # Flatten containers
            all_containers: List[Dict[str, Any]] = []
            for pod_info in self._pods.values():
                all_containers.extend(pod_info["containers"])

            total_pods = len(self._pods)
            total_containers = len(all_containers)
            running = sum(1 for c in all_containers if c["state"] == "running")
            waiting = sum(1 for c in all_containers if c["state"] == "waiting")
            terminated = sum(1 for c in all_containers if c["state"] == "terminated")
            ready = sum(1 for c in all_containers if c["ready"])
            unhealthy = sum(1 for c in all_containers if c["unhealthy"])

            # Human-readable cluster message
            if cluster_connected:
                msg = "Połączono z klastrem Kubernetes."
            elif not in_cluster:
                msg = "Aplikacja działa poza klastrem Kubernetes (tryb standalone)."
            else:
                msg = error_message or "Błąd połączenia z Kubernetes API w klastrze."

            return {
                "version": Config.APP_VERSION,
                "cluster": {
                    "connected": cluster_connected,
                    "version": cluster_version,
                    "in_cluster": in_cluster,
                    "status": "connected" if cluster_connected else "disconnected",
                    "message": msg,
                    "last_updated": self._last_updated,
                },
                "summary": {
                    "total_pods": total_pods,
                    "total_containers": total_containers,
                    "running": running,
                    "waiting": waiting,
                    "terminated": terminated,
                    "ready": ready,
                    "unhealthy": unhealthy,
                },
                "containers": all_containers,
            }
