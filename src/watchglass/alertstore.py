"""alerts.json: failures a hook reports with `ctx.alert` without parking the watch (issue 45).

The file sits beside offline.json in the watch's state directory, so an unacknowledged failure survives a
service restart and `watchglass status` can read it whether or not a service is running. `watchglass ack
<watch>` clears it. It never stops the scheduler: "should the watch keep polling?" and "has something failed
that the operator has not seen?" are separate questions.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from watchglass.offline import iso_time
from watchglass.paths import Paths, write_json_atomic

MAX_ALERTS = 20  # the newest alerts are the ones an operator acts on; the file stays small


@dataclass(frozen=True)
class Alert:
    message: str
    since: str
    hook: str | None = None
    poll_id: str | None = None

    def since_epoch(self) -> float:
        try:
            return datetime.fromisoformat(self.since).timestamp()
        except ValueError:
            return 0.0


def _unreadable(path: Path, watch: str) -> list[Alert]:
    return [Alert(message=f"{path} is unreadable; run: watchglass ack {watch}", since=iso_time(time.time()))]


def read_alert_file(path: Path, watch: str) -> list[Alert]:
    """The alerts recorded for WATCH, oldest first. A file that cannot be read is one unreadable alert."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        return _unreadable(path, watch)
    entries = data.get("alerts") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return _unreadable(path, watch)
    alerts = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("message"), str):
            continue
        hook, poll_id = entry.get("hook"), entry.get("poll_id")
        alerts.append(
            Alert(
                message=entry["message"],
                since=str(entry.get("since") or ""),
                hook=hook if isinstance(hook, str) else None,
                poll_id=poll_id if isinstance(poll_id, str) else None,
            )
        )
    return alerts


def read_alerts(paths: Paths, watch: str) -> list[Alert]:
    return read_alert_file(paths.alert_file(watch), watch)


def record_alert_file(
    path: Path,
    message: str,
    *,
    hook: str | None = None,
    poll_id: str | None = None,
    watch: str = "watch",
    now: float | None = None,
) -> Alert:
    """Append one alert and keep the newest MAX_ALERTS. Callers run one hook at a time, so the read-modify-write
    races only with `watchglass ack`, whose unlink wins or loses as a whole either way."""
    alert = Alert(message=message, since=iso_time(time.time() if now is None else now), hook=hook, poll_id=poll_id)
    alerts = [*read_alert_file(path, watch), alert][-MAX_ALERTS:]
    write_json_atomic(path, {"version": 1, "alerts": [asdict(item) for item in alerts]})
    return alert


def record_alert(
    paths: Paths, watch: str, message: str, *, hook: str | None = None, poll_id: str | None = None, now: float | None = None
) -> Alert:
    return record_alert_file(
        paths.alert_file(watch), message, hook=hook, poll_id=poll_id, watch=watch, now=now
    )


def clear_alerts(paths: Paths, watch: str) -> int:
    """Acknowledge every alert. Returns how many were cleared (a file that cannot be read counts as one)."""
    path = paths.alert_file(watch)
    cleared = len(read_alerts(paths, watch))
    try:
        path.unlink()
    except FileNotFoundError:
        return 0
    return cleared


def alert_key(alerts: list[Alert]) -> str | None:
    """A value that changes when a new alert arrives: the newest one's time and message."""
    return None if not alerts else f"{alerts[-1].since}|{alerts[-1].message}"


def alert_summary(alerts: list[Alert]) -> dict[str, Any] | None:
    """The compact form status.json carries: how many, and the newest one."""
    if not alerts:
        return None
    latest = alerts[-1]
    return {
        "count": len(alerts),
        "message": latest.message,
        "since": latest.since,
        "hook": latest.hook,
    }
