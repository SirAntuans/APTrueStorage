"""Tests del modo interactivo."""

import io

import pytest

from aptrue import interactive


def _run_interactive_with_inputs(monkeypatch, responses):
    outputs = []

    class FakeInput:
        def __init__(self):
            self.calls = 0

        def __call__(self, prompt=""):
            outputs.append(prompt)
            if self.calls < len(responses):
                value = responses[self.calls]
            else:
                value = "q"
            self.calls += 1
            return value

    monkeypatch.setattr(interactive, "_input", FakeInput())
    code = interactive.run_interactive()
    return code, outputs


def test_quit_immediately(monkeypatch):
    code, _ = _run_interactive_with_inputs(monkeypatch, ["q"])
    assert code == 0


def test_invalid_option_then_quit(monkeypatch):
    code, _ = _run_interactive_with_inputs(monkeypatch, ["zz", "q"])
    assert code == 0


def test_list_devices_option(monkeypatch):
    code, _ = _run_interactive_with_inputs(monkeypatch, ["1", "", "q"])
    assert code == 0


def test_confirm_destructive_requires_exact_word(monkeypatch):
    class Dev:
        path = "/dev/sdz"
        size_human = "32.00 GB"

    monkeypatch.setattr(interactive, "_input", lambda prompt="": "si")
    assert interactive._confirm_destructive(Dev()) is False
    monkeypatch.setattr(interactive, "_input", lambda prompt="": "BORRAR")
    assert interactive._confirm_destructive(Dev()) is True


def test_choose_device_cancel(monkeypatch, tmp_path):
    import aptrue.devices as devices_mod

    monkeypatch.setattr(devices_mod, "list_devices", lambda: [])
    code, _ = _run_interactive_with_inputs(monkeypatch, ["2", "", "q"])
    assert code == 0
