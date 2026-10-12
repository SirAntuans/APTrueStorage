"""Tests de la verificación de autenticidad usando imágenes de disco temporales."""

import os

import pytest

from aptrue import verify as v

BLOCK = v.BLOCK_SIZE


@pytest.fixture
def img_path(tmp_path):
    """Imagen de disco temporal de 4 bloques (4 MiB)."""
    path = tmp_path / "disk.img"
    with open(path, "w+b") as f:
        f.truncate(4 * BLOCK)
    return str(path)


def test_make_block_header():
    nonce = os.urandom(8)
    block = v._make_block(42, nonce)
    assert len(block) == BLOCK
    assert block[:4] == v.MAGIC
    assert v._check_block(block, 42, nonce)[0] is True or v._check_block(block, 42, nonce) == (True, False)


def test_check_block_wrong_index():
    nonce = os.urandom(8)
    block = v._make_block(7, nonce)
    ok, zeroed = v._check_block(block, 99, nonce)
    assert ok is False


def test_check_block_zeroed():
    ok, zeroed = v._check_block(b"\x00" * BLOCK, 0, b"")
    assert ok is False and zeroed is True
    ok, zeroed = v._check_block(b"\xff" * BLOCK, 0, b"")
    assert ok is False and zeroed is True


def test_verify_authentic_device(img_path):
    report = v.verify_device(img_path, 4 * BLOCK)
    assert report.is_authentic
    assert report.blocks_written == 4
    assert report.blocks_ok == 4
    assert report.blocks_corrupt == 0
    assert report.first_bad_block is None
    assert report.verified_bytes == 4 * BLOCK


def test_verify_authentic_image_of_half_size(tmp_path):
    """Un archivo auténtico de 2 bloques verificado con su tamaño real."""
    path = tmp_path / "disk.img"
    with open(path, "w+b") as f:
        f.truncate(2 * BLOCK)
    report = v.verify_device(str(path), 2 * BLOCK)
    assert report.is_authentic
    assert report.blocks_ok == 2
    assert report.blocks_written == 2


def test_report_summary_falsified():
    report = v.VerifyReport(device="/dev/x", capacity_bytes=1024**3)
    report.blocks_written = 100
    report.blocks_ok = 50
    report.blocks_corrupt = 50
    report.first_bad_block = 50
    report.verified_bytes = 50 * BLOCK
    text = report.summary()
    assert "FALSIFICADO" in text
    assert "/dev/x" in text


def test_report_summary_authentic():
    report = v.VerifyReport(device="/dev/x", capacity_bytes=1024**3)
    report.blocks_written = 100
    report.blocks_ok = 100
    text = report.summary()
    assert "AUTÉNTICO" in text


def test_verify_detects_falsified_disk(fake_disk_env):
    """Prueba integral: disco que declara 4 MiB pero solo almacena 2 MiB."""
    report = v.verify_device(
        fake_disk_env["path"], fake_disk_env["declared"], max_blocks=4
    )
    assert not report.is_authentic
    assert report.blocks_written == 4
    assert report.blocks_ok < 4
    assert report.blocks_corrupt > 0
    assert report.first_bad_block is not None
    assert report.first_bad_block * v.BLOCK_SIZE <= fake_disk_env["real"]


def test_verify_falsified_exit_semantic(fake_disk_env):
    """El reporte de un disco falso debe marcar la mayoría de bloques corruptos
    y la capacidad verificada debe ser menor que la declarada."""
    report = v.verify_device(
        fake_disk_env["path"], fake_disk_env["declared"], max_blocks=4
    )
    assert report.blocks_corrupt >= 2
    assert report.blocks_ok < report.blocks_written
    assert report.verified_bytes < fake_disk_env["declared"]
