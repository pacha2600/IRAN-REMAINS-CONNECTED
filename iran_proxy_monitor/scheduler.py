"""Clock-based automatic scan schedule, separate from the Tkinter UI.

Uses the wall clock so sleep and hibernation count toward the configured
refresh interval. Never accumulates missed runs: one due execution after wake
and a fresh interval only after the cycle finishes. Does not persist auto mode;
the user must re-enable it when opening the application.
"""
from __future__ import annotations
from dataclasses import dataclass
import time


@dataclass
class AutoScheduler:
    enabled: bool = False
    due_at: float | None = None
    interval_seconds: float = 120 * 60

    def arm(self, minutes: int, *, now: float | None = None) -> None:
        if not 5 <= minutes <= 10080:
            raise ValueError('Refresh interval must be 5–10080 minutes')
        stamp = time.time() if now is None else now
        self.interval_seconds = minutes * 60
        self.enabled = True
        self.due_at = stamp + self.interval_seconds

    def disarm(self) -> None:
        self.enabled = False
        self.due_at = None

    def cycle_finished(self, *, now: float | None = None) -> None:
        if self.enabled:
            stamp = time.time() if now is None else now
            self.due_at = stamp + self.interval_seconds

    def defer_failed(self, *, now: float | None = None) -> None:
        if self.enabled:
            stamp = time.time() if now is None else now
            self.due_at = stamp + min(300, self.interval_seconds)

    def ready(self, *, now: float | None = None) -> bool:
        stamp = time.time() if now is None else now
        return self.enabled and self.due_at is not None and stamp >= self.due_at

    def remaining(self, *, now: float | None = None) -> int:
        stamp = time.time() if now is None else now
        return max(0, int((self.due_at or stamp) - stamp))
