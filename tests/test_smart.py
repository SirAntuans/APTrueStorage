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


def test_summary_hint_when_unavailable():
    from aptrue.smart import SmartReport

    rep = SmartReport(device="/dev/sda")
    rep.hint = "Ejecuta el programa como administrador"
    text = rep.summary()
    assert "administrador" in text


def test_smartmontools_url_exists():
    from aptrue.smart import SMARTMONTOOLS_URL

    assert SMARTMONTOOLS_URL.startswith("https://")


def test_parse_smartctl_nvme_text():
    from aptrue.smart import _parse_smartctl_text, SmartReport

    rep = SmartReport(device="/dev/nvme0")
    text = "Power On Hours:              3412\nPercentage Used:             3%\n"
    _parse_smartctl_text(rep, text)
    assert rep.power_on_hours == 3412
    assert rep.wear_level == 3
