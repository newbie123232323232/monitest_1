from datetime import UTC, datetime

from app.workers.tasks.expiry import (
    _extract_domain,
    _next_threshold_to_alert,
    _normalize_whois_expiration,
    _parse_thresholds,
    _serialize_thresholds,
    _state_from_days,
)


def test_state_from_days_thresholds() -> None:
    assert _state_from_days(None) == "unknown"
    assert _state_from_days(-1) == "expired"
    assert _state_from_days(0) == "warn_1d"
    assert _state_from_days(1) == "warn_1d"
    assert _state_from_days(2) == "warn_7d"
    assert _state_from_days(7) == "warn_7d"
    assert _state_from_days(8) == "warn_14d"
    assert _state_from_days(14) == "warn_14d"
    assert _state_from_days(15) == "warn_30d"
    assert _state_from_days(30) == "warn_30d"
    assert _state_from_days(31) == "ok"


def test_expiry_threshold_tracking_helpers() -> None:
    assert _parse_thresholds("") == set()
    assert _parse_thresholds("30,14,7") == {30, 14, 7}
    assert _serialize_thresholds({30, 7, 14}) == "30,14,7"
    assert _next_threshold_to_alert(40, set()) is None
    assert _next_threshold_to_alert(20, set()) == 30
    assert _next_threshold_to_alert(10, {30}) == 14
    assert _next_threshold_to_alert(6, {30, 14}) == 7
    assert _next_threshold_to_alert(0, {30, 14, 7}) == 1
    assert _next_threshold_to_alert(-1, set()) is None


def test_whois_normalization_helpers() -> None:
    assert _extract_domain("https://example.com/path") == "example.com"
    dt = datetime(2026, 12, 31, tzinfo=UTC)
    assert _normalize_whois_expiration(dt) == dt
    assert _normalize_whois_expiration("2026-12-31") == datetime(2026, 12, 31, tzinfo=UTC)
    assert _normalize_whois_expiration(["", "2026-12-31"]) == datetime(2026, 12, 31, tzinfo=UTC)
    assert _normalize_whois_expiration("not-a-date") is None
