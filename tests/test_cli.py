"""Tests de la CLI."""

import pytest

from aptrue.cli import build_parser, main


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "aptrue" in out


def test_list_json(capsys):
    code = main(["list", "--json"])
    assert code in (0, 1)
    import json

    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, list)


def test_info_nonexistent(capsys):
    code = main(["info", "/dev/noexiste123"])
    assert code == 1


def test_verify_rejects_partition():
    # Las particiones deben rechazarse para evitar borrar medios por error
    code = main(["verify", "/dev/sdb1"])
    assert code == 1


def test_parser_requires_command():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])
