import json

from watchglass.alertstore import (
    MAX_ALERTS,
    alert_key,
    alert_summary,
    clear_alerts,
    read_alerts,
    record_alert,
)


def test_record_read_and_clear_round_trip(xdg):
    assert read_alerts(xdg, "w") == []
    first = record_alert(xdg, "w", "psg-env-1 failed SHA-256 verification", hook="on_true", poll_id="p1",
                         now=1_000_000)
    second = record_alert(xdg, "w", "psg-env-2 failed", now=1_000_001)
    alerts = read_alerts(xdg, "w")
    assert [alert.message for alert in alerts] == [
        "psg-env-1 failed SHA-256 verification",
        "psg-env-2 failed",
    ]
    assert alerts[0] == first and alerts[0].hook == "on_true" and alerts[0].poll_id == "p1"
    assert alert_summary(alerts) == {"count": 2, "message": "psg-env-2 failed", "since": second.since, "hook": None}
    assert json.loads(xdg.alert_file("w").read_text())["version"] == 1
    assert clear_alerts(xdg, "w") == 2
    assert read_alerts(xdg, "w") == [] and clear_alerts(xdg, "w") == 0


def test_the_file_keeps_the_newest_alerts(xdg):
    for index in range(MAX_ALERTS + 5):
        record_alert(xdg, "w", f"bad item {index}", now=1_000_000 + index)
    alerts = read_alerts(xdg, "w")
    assert len(alerts) == MAX_ALERTS
    assert alerts[0].message == "bad item 5" and alerts[-1].message == f"bad item {MAX_ALERTS + 4}"


def test_an_unreadable_file_is_one_alert_not_silence(xdg):
    path = xdg.alert_file("w")
    path.parent.mkdir(parents=True)
    path.write_text("{oops")
    (alert,) = read_alerts(xdg, "w")
    assert str(path) in alert.message and "watchglass ack w" in alert.message
    assert clear_alerts(xdg, "w") == 1 and read_alerts(xdg, "w") == []


def test_a_new_alert_changes_the_key_and_a_cleared_file_has_none(xdg):
    assert alert_key(read_alerts(xdg, "w")) is None
    record_alert(xdg, "w", "first", now=1_000_000)
    key = alert_key(read_alerts(xdg, "w"))
    assert key is not None and "first" in key
    record_alert(xdg, "w", "first", now=1_000_000)  # the same message again is a new alert (a new failure)
    assert alert_key(read_alerts(xdg, "w")) == key  # the same second, the same message: nothing new to report
