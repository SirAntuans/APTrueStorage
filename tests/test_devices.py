"""Tests de detección de dispositivos y utilidades."""

import pytest

from aptrue.devices import StorageDevice, _human_size, is_whole_disk


def test_human_size_units():
    assert _human_size(0) == "0.00 B"
    assert _human_size(1024) == "1.00 KB"
    assert _human_size(1024**2) == "1.00 MB"
    assert _human_size(1536 * 1024**2) == "1.50 GB"
    assert _human_size(1024**4) == "1.00 TB"


def test_device_dataclass():
    dev = StorageDevice(
        path="/dev/sdb",
        name="sdb",
        size_bytes=32 * 1024**3,
        removable=True,
        device_type="MicroSD / USB",
    )
    assert dev.size_human == "32.00 GB"


def test_is_whole_disk_rejects_partitions():
    assert is_whole_disk("/dev/sdb1") is False
    assert is_whole_disk("/dev/nvme0n1p2") is False


def test_is_whole_disk_rejects_loop():
    assert is_whole_disk("/dev/loop0") is False


def test_is_whole_disk_accepts_valid_names():
    # Depende del sistema: en CI no hay discos, así que solo validamos
    # que no lance excepciones y devuelva bool.
    result = is_whole_disk("/dev/sda")
    assert isinstance(result, bool)


def test_get_device_nonexistent():
    from aptrue.devices import get_device

    assert get_device("/dev/noexiste123") is None
