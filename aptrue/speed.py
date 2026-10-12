"""Benchmark de velocidad secuencial para discos completos."""

from __future__ import annotations

import dataclasses
import os
import time

BLOCK_SIZE = 1024 * 1024  # 1 MiB


@dataclasses.dataclass
class SpeedResult:
    device: str
    write_mbps: float = 0.0
    read_mbps: float = 0.0
    error: str = ""

    def summary(self) -> str:
        if self.error:
            return f"{self.device}: ERROR ({self.error})"
        return (
            f"{self.device}: escritura {self.write_mbps:.2f} MB/s, "
            f"lectura {self.read_mbps:.2f} MB/s"
        )


def _write_test(fd: int, size_bytes: int) -> float:
    chunk = os.urandom(BLOCK_SIZE)
    start = time.monotonic()
    written = 0
    while written < size_bytes:
        n = os.write(fd, chunk)
        if n <= 0:
            break
        written += n
    os.fsync(fd)
    elapsed = time.monotonic() - start
    return (written / (1024 * 1024)) / elapsed if elapsed > 0 else 0.0


def _read_test(fd: int, size_bytes: int) -> float:
    os.lseek(fd, 0, os.SEEK_SET)
    start = time.monotonic()
    read = 0
    while read < size_bytes:
        n = os.read(fd, BLOCK_SIZE)
        if not n:
            break
        read += len(n)
    elapsed = time.monotonic() - start
    return (read / (1024 * 1024)) / elapsed if elapsed > 0 else 0.0


def run_benchmark(device: str, test_size_bytes: int, destructive: bool = False) -> SpeedResult:
    """Mide velocidad secuencial de lectura/escritura.

    Si destructive=True escribe datos en el disco (¡borra datos!).
    En modo no destructivo solo mide lectura (el disco debe contener datos).
    """
    result = SpeedResult(device=device)
    flags = os.O_RDONLY
    if destructive:
        flags = os.O_RDWR | os.O_SYNC if hasattr(os, "O_DIRECT") is False else os.O_RDWR
    try:
        fd = os.open(device, flags)
    except PermissionError:
        result.error = "permiso denegado (ejecuta como root)"
        return result

    try:
        if destructive:
            result.write_mbps = _write_test(fd, test_size_bytes)
        result.read_mbps = _read_test(fd, test_size_bytes)
    except OSError as exc:
        result.error = str(exc)
    finally:
        os.close(fd)
    return result
