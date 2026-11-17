"""
Analyzer module for KubeAlert.
Evaluates Pod state changes, detects failure reasons, and manages anti-flapping cooldowns.
"""

import time
import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple

from config import Config

logger = logging.getLogger("kubealert.analyzer")

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


@dataclass
class PodIssue:
    namespace: str
    pod_name: str
    container_name: str
    reason: str
    message: str
    restart_count: int
    exit_code: Optional[int]
    phase: str
    detected_at: float


class AlertCache:
    """In-memory cache for anti-flapping and deduplication."""

    def __init__(self, cooldown_seconds: int = 900):
        self.cooldown_seconds = cooldown_seconds
        # Key: (namespace, pod_name, container_name, reason) -> last_alert_timestamp
        self._history: Dict[Tuple[str, str, str, str], float] = {}

    def should_alert(self, issue: PodIssue) -> bool:
        key = (issue.namespace, issue.pod_name, issue.container_name, issue.reason)
        now = time.time()
        last_alert = self._history.get(key)

        if last_alert is None or (now - last_alert) >= self.cooldown_seconds:
            self._history[key] = now
            return True

        logger.debug(
            "Suppressing alert for %s/%s [%s: %s] - cooldown active (%.1fs remaining)",
            issue.namespace,
            issue.pod_name,
            issue.container_name,
            issue.reason,
            self.cooldown_seconds - (now - last_alert),
        )
        return False

    def cleanup(self):
        """Purges entries older than twice the cooldown."""
        now = time.time()
        cutoff = now - (self.cooldown_seconds * 2)
        keys_to_remove = [k for k, ts in self._history.items() if ts < cutoff]
        for k in keys_to_remove:
            del self._history[k]


class PodAnalyzer:
    def __init__(self):
        self.cache = AlertCache(cooldown_seconds=Config.ALERT_COOLDOWN_SECONDS)

    def analyze_pod(self, pod: dict) -> List[PodIssue]:
        metadata = pod.get("metadata", {})
        namespace = metadata.get("namespace", "default")
        pod_name = metadata.get("name", "unknown")

        if not Config.should_monitor_namespace(namespace):
            return []

        status = pod.get("status", {})
        phase = status.get("phase", "Unknown")

        # Periodically clean up stale cache keys
        self.cache.cleanup()

        issues: List[PodIssue] = []

        # 1. Check containers and initContainers statuses
        container_statuses = status.get("containerStatuses", []) + status.get("initContainerStatuses", [])
        for cs in container_statuses:
            c_name = cs.get("name", "unknown")
            restart_count = cs.get("restartCount", 0)
            state = cs.get("state", {})
            last_state = cs.get("lastState", {})

            # Check currently waiting state
            waiting = state.get("waiting")
            if waiting:
                reason = waiting.get("reason", "")
                if reason in CRITICAL_WAITING_REASONS:
                    issue = PodIssue(
                        namespace=namespace,
                        pod_name=pod_name,
                        container_name=c_name,
                        reason=reason,
                        message=waiting.get("message", "No detailed message provided."),
                        restart_count=restart_count,
                        exit_code=None,
                        phase=phase,
                        detected_at=time.time(),
                    )
                    if self.cache.should_alert(issue):
                        issues.append(issue)

            # Check terminated state (e.g. OOMKilled or non-zero exit)
            terminated = state.get("terminated") or last_state.get("terminated")
            if terminated:
                reason = terminated.get("reason", "")
                exit_code = terminated.get("exitCode")
                if reason in CRITICAL_TERMINATED_REASONS or (exit_code is not None and exit_code != 0):
                    effective_reason = reason if reason else f"ExitCode:{exit_code}"
                    issue = PodIssue(
                        namespace=namespace,
                        pod_name=pod_name,
                        container_name=c_name,
                        reason=effective_reason,
                        message=terminated.get("message", f"Container exited with code {exit_code}."),
                        restart_count=restart_count,
                        exit_code=exit_code,
                        phase=phase,
                        detected_at=time.time(),
                    )
                    if self.cache.should_alert(issue):
                        issues.append(issue)

        # 2. Check PodConditions for Scheduling failures (e.g. Unschedulable)
        for condition in status.get("conditions", []):
            if condition.get("type") == "PodScheduled" and condition.get("status") == "False":
                reason = condition.get("reason", "")
                if reason in ("Unschedulable",):
                    issue = PodIssue(
                        namespace=namespace,
                        pod_name=pod_name,
                        container_name="[PodSchedule]",
                        reason=reason,
                        message=condition.get("message", "Pod cannot be scheduled."),
                        restart_count=0,
                        exit_code=None,
                        phase=phase,
                        detected_at=time.time(),
                    )
                    if self.cache.should_alert(issue):
                        issues.append(issue)

        return issues
