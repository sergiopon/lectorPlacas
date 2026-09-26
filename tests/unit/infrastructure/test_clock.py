from __future__ import annotations

from datetime import timedelta

from lector_placas.infrastructure.clock import SystemClock


def test_system_clock_returns_utc() -> None:
    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)
