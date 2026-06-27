"""
Session Manager — Manifest Parser & State Tracker
=====================================================
Parses task manifest JSON files and maintains active session state
throughout the agent orchestration loop.

Tracks:
- Current step counter
- Trace history (actions taken + observations)
- Active objective and domain restrictions
- Human review gates
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from agent.core.config import Settings, get_settings


# ── Manifest Schema ─────────────────────────────────────────────────────


@dataclass
class TaskManifest:
    """Parsed representation of a task manifest JSON file."""

    session_id: str
    objective: str
    target_domains: list[str]
    max_steps: int = 60
    human_review_required: list[str] = field(default_factory=list)
    credentials_ref: Optional[str] = None
    output_schema: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: Path) -> TaskManifest:
        """Load and validate a manifest from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskManifest:
        """Construct a TaskManifest from a dictionary."""
        required_fields = {"session_id", "objective", "target_domains"}
        missing = required_fields - set(data.keys())
        if missing:
            raise ValueError(f"Manifest missing required fields: {missing}")

        if not isinstance(data["target_domains"], list) or not data["target_domains"]:
            raise ValueError("target_domains must be a non-empty list")

        return cls(
            session_id=data["session_id"],
            objective=data["objective"],
            target_domains=data["target_domains"],
            max_steps=data.get("max_steps", 60),
            human_review_required=data.get("human_review_required", []),
            credentials_ref=data.get("credentials_ref"),
            output_schema=data.get("output_schema"),
            metadata={
                k: v
                for k, v in data.items()
                if k
                not in {
                    "session_id",
                    "objective",
                    "target_domains",
                    "max_steps",
                    "human_review_required",
                    "credentials_ref",
                    "output_schema",
                }
            },
        )


# ── Trace Entry ──────────────────────────────────────────────────────────


@dataclass
class TraceEntry:
    """A single entry in the session trace log."""

    step: int
    timestamp: str
    action: dict[str, Any]
    observation: Optional[str] = None
    success: bool = True
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise to dictionary for JSONL logging."""
        return {
            "step": self.step,
            "timestamp": self.timestamp,
            "action": self.action,
            "observation": self.observation,
            "success": self.success,
            "error": self.error,
        }


# ── Session State ────────────────────────────────────────────────────────


class SessionState:
    """
    Mutable state object maintained throughout a single task session.

    Responsibilities:
    - Track the current step counter
    - Accumulate trace history (actions + observations)
    - Enforce step limits from the manifest
    - Validate domain restrictions before navigation
    - Check whether an action requires human review
    """

    def __init__(self, manifest: TaskManifest) -> None:
        self._manifest = manifest
        self._current_step: int = 0
        self._trace: list[TraceEntry] = []
        self._status: str = "initialising"  # initialising | running | paused | completed | failed
        self._started_at: str = datetime.now(timezone.utc).isoformat()
        self._completed_at: Optional[str] = None

    # ── Properties ────────────────────────────────────────────────────

    @property
    def manifest(self) -> TaskManifest:
        """Return the task manifest."""
        return self._manifest

    @property
    def session_id(self) -> str:
        """Return the session identifier."""
        return self._manifest.session_id

    @property
    def objective(self) -> str:
        """Return the task objective string."""
        return self._manifest.objective

    @property
    def current_step(self) -> int:
        """Return the current step counter."""
        return self._current_step

    @property
    def max_steps(self) -> int:
        """Return the maximum steps allowed."""
        return self._manifest.max_steps

    @property
    def status(self) -> str:
        """Return the current session status."""
        return self._status

    @property
    def trace(self) -> list[TraceEntry]:
        """Return the full trace history."""
        return list(self._trace)

    @property
    def is_step_limit_reached(self) -> bool:
        """Check if the step limit has been reached."""
        return self._current_step >= self._manifest.max_steps

    # ── Step Management ───────────────────────────────────────────────

    def start(self) -> None:
        """Transition session to running state."""
        self._status = "running"

    def increment_step(self) -> int:
        """
        Advance the step counter by one.

        Returns the new step number.
        Raises RuntimeError if the step limit is exceeded.
        """
        if self.is_step_limit_reached:
            raise RuntimeError(
                f"Step limit reached ({self._manifest.max_steps}). "
                "Session must be terminated or escalated."
            )
        self._current_step += 1
        return self._current_step

    def record_action(
        self,
        action: dict[str, Any],
        observation: Optional[str] = None,
        success: bool = True,
        error: Optional[str] = None,
    ) -> TraceEntry:
        """
        Record an action and its outcome in the trace history.

        Args:
            action: The action dict (matching AgentAction schema).
            observation: Optional observation after the action.
            success: Whether the action succeeded.
            error: Optional error message if action failed.

        Returns:
            The created TraceEntry.
        """
        entry = TraceEntry(
            step=self._current_step,
            timestamp=datetime.now(timezone.utc).isoformat(),
            action=action,
            observation=observation,
            success=success,
            error=error,
        )
        self._trace.append(entry)
        return entry

    # ── Domain Validation ─────────────────────────────────────────────

    def is_domain_allowed(self, url: str) -> bool:
        """
        Check if a URL's domain is within the manifest's allowed list.

        Supports subdomains: 'careers.example.com' matches 'example.com'.
        """
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
        except Exception:
            return False

        for allowed_domain in self._manifest.target_domains:
            if hostname == allowed_domain or hostname.endswith(f".{allowed_domain}"):
                return True
        return False

    # ── Human Review Gates ────────────────────────────────────────────

    def requires_human_review(self, action_name: str) -> bool:
        """
        Check if the given action name is in the manifest's human review list.

        Args:
            action_name: The action type string (e.g. 'submit_application').
        """
        return action_name in self._manifest.human_review_required

    # ── Session Lifecycle ─────────────────────────────────────────────

    def pause(self) -> None:
        """Pause the session (e.g., for human review)."""
        self._status = "paused"

    def resume(self) -> None:
        """Resume a paused session."""
        if self._status != "paused":
            raise RuntimeError(f"Cannot resume session in '{self._status}' state")
        self._status = "running"

    def complete(self) -> None:
        """Mark the session as successfully completed."""
        self._status = "completed"
        self._completed_at = datetime.now(timezone.utc).isoformat()

    def fail(self, reason: str) -> None:
        """Mark the session as failed."""
        self._status = "failed"
        self._completed_at = datetime.now(timezone.utc).isoformat()
        self.record_action(
            action={"action": "fail", "reasoning": reason},
            success=False,
            error=reason,
        )

    # ── Serialisation ─────────────────────────────────────────────────

    def to_summary(self) -> dict[str, Any]:
        """Return a compact summary of the session state for logging."""
        return {
            "session_id": self.session_id,
            "objective": self.objective,
            "status": self._status,
            "current_step": self._current_step,
            "max_steps": self.max_steps,
            "total_actions": len(self._trace),
            "started_at": self._started_at,
            "completed_at": self._completed_at,
        }


# ── Factory Function ─────────────────────────────────────────────────────


def load_session(manifest_path: Path, settings: Optional[Settings] = None) -> SessionState:
    """
    Load a task manifest and create an initialised SessionState.

    Args:
        manifest_path: Path to the manifest JSON file.
        settings: Optional settings override.

    Returns:
        A ready-to-use SessionState instance.
    """
    settings = settings or get_settings()
    manifest = TaskManifest.from_file(manifest_path)
    return SessionState(manifest=manifest)
