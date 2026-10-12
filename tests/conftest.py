"""Fixtures compartidas: simulación de discos falsificados."""

import os

import pytest

import aptrue.verify as verify_mod
from aptrue.verify import BLOCK_SIZE


class FakeFraudulentDisk:
    """Emula un disco falsificado: declara N bytes pero solo almacena M.

    Los writes más allá de la capacidad real (M) se redirigen al inicio
    del disco, sobrescribiendo los primeros bloques — exactamente como
    se comportan las tarjetas MicroSD falsas y los pendrives clonados.
    """

    def __init__(self, path, real_bytes):
        self.path = path
        self.real_bytes = real_bytes
        self.f = open(path, "w+b")
        self.f.truncate(real_bytes)

    def write(self, data):
        pos = self.f.tell()
        if pos >= self.real_bytes:
            self.f.seek(pos - self.real_bytes)
            n = self.f.write(data)
            self.f.seek(min(pos - self.real_bytes + n, self.real_bytes - 1))
            return n
        end = pos + len(data)
        n = self.f.write(data[: max(0, self.real_bytes - pos)])
        self.f.seek(end if end <= self.real_bytes else self.real_bytes - 1)
        return len(data)

    def read(self, size):
        return self.f.read(size)

    def seek(self, *args):
        return self.f.seek(*args)

    def tell(self):
        return self.f.tell()

    def close(self):
        return self.f.close()


@pytest.fixture
def fake_disk_env(tmp_path, monkeypatch):
    """Redirige os.open/os.write/os.read de aptrue.verify a un disco falso."""
    img = tmp_path / "fraud.img"
    img.write_bytes(b"\x00" * 64)  # placeholder
    real_bytes = 2 * BLOCK_SIZE  # capacidad real: 2 MiB
    declared_bytes = 4 * BLOCK_SIZE  # declarada: 4 MiB (falsificada)

    disk = FakeFraudulentDisk(str(img), real_bytes)
    fd_map = {}

    orig_open = os.open
    orig_close = os.close

    def fake_open(path, flags, *args, **kwargs):
        if str(path) == str(img):
            fd_map["only"] = disk
            return -1000  # fd sintético
        return orig_open(path, flags, *args, **kwargs)

    def fake_write(fd, data):
        if fd == -1000:
            return fd_map["only"].write(data)
        return os.write(fd, data)

    def fake_read(fd, size):
        if fd == -1000:
            return fd_map["only"].read(size)
        return os.read(fd, size)

    def fake_lseek(fd, offset, whence):
        if fd == -1000:
            return fd_map["only"].seek(offset, whence) or 0
        return os.lseek(fd, offset, whence)

    def fake_fsync(fd):
        if fd == -1000:
            return fd_map["only"].flush() if hasattr(fd_map["only"], "flush") else None
        return os.fsync(fd)

    def fake_close(fd):
        if fd != -1000:
            orig_close(fd)

    monkeypatch.setattr(verify_mod.os, "open", fake_open, raising=False)
    monkeypatch.setattr(verify_mod.os, "write", fake_write, raising=False)
    monkeypatch.setattr(verify_mod.os, "read", fake_read, raising=False)
    monkeypatch.setattr(verify_mod.os, "lseek", fake_lseek, raising=False)
    monkeypatch.setattr(verify_mod.os, "fsync", fake_fsync, raising=False)
    monkeypatch.setattr(verify_mod.os, "close", fake_close, raising=False)

    return {"path": str(img), "declared": declared_bytes, "real": real_bytes}
