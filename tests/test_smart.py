"""Tests del parser SMART (sin necesidad de smartctl real)."""

from aptrue.smart import SmartReport, _to_int


def test_to_int():
    assert _to_int("42") == 42
    assert _to_int("  7  ") == 7
    assert _to_int("abc") is None
    assert _to_int("") is None
    assert _to_int(None) is None


def test_report_defaults():
    rep = SmartReport(device="/dev/sda")
    assert rep.available is False
    assert "no disponible" in rep.summary()


def test_report_summary_with_data():
    rep = SmartReport(device="/dev/sda")
    rep.available = True
    rep.overall = "PASSED"
    rep.temperature_c = 34
    rep.power_on_hours = 1200
    rep.reallocated_sectors = 0
    rep.pending_sectors = 0
    rep.wear_level = 5
    text = rep.summary()
    assert "PASSED" in text
    assert "34°C" in text
    assert "5%" in text
