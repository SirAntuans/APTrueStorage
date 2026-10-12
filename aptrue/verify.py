"""Verificación de capacidad real y autenticidad (inspirado en f3/fakeflash).

Escribe bloques con un patrón firmado (offset + nonce + hora), luego los
relee. Un disco falsificado reporta una capacidad mayor a la real: al
reescribir los datos los pierde, y la relectura revela bloques corruptos
o rellenados con ceros/0xFF.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import os
import struct
import time

BLOCK_SIZE = 1024 * 1024  # 1 MiB por bloque
MAGIC = b"APTR"


@dataclasses.dataclass
class VerifyReport:
    device: str
    blocks_written: int = 0
    blocks_ok: int = 0
    blocks_corrupt: int = 0
    blocks_zeroed: int = 0
    first_bad_block: int | None = None
    verified_bytes: int = 0
    capacity_bytes: int = 0
    elapsed_seconds: float = 0.0
    write_mbps: float = 0.0
    read_mbps: float = 0.0

    @property
    def is_authentic(self) -> bool:
        return self.blocks_corrupt == 0 and self.blocks_written > 0

    @property
    def real_capacity_human(self) -> str:
        return _human(self.verified_bytes)

    def summary(self) -> str:
        if self.blocks_written == 0:
            return f"{self.device}: no se escribieron bloques"
        status = "AUTÉNTICO" if self.is_authentic else "FALSIFICADO"
        lines = [
            f"Dispositivo: {self.device}",
            f"Resultado: {status}",
            f"Capacidad declarada: {_human(self.capacity_bytes)}",
            f"Capacidad verificada: {self.real_capacity_human}",
            f"Bloques escritos: {self.blocks_written}",
            f"Bloques correctos: {self.blocks_ok}",
            f"Bloques corruptos: {self.blocks_corrupt}",
            f"Tiempo: {self.elapsed_seconds:.1f}s  "
            f"(escritura {self.write_mbps:.2f} MB/s, lectura {self.read_mbps:.2f} MB/s)",
        ]
        if self.first_bad_block is not None:
            lines.append(
                f"Primer bloque defectuoso: #{self.first_bad_block} "
                f"(offset {_human(self.first_bad_block * BLOCK_SIZE)})"
            )
        return "\n".join(lines)


def _human(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} TB"


def _make_block(index: int, nonce: bytes) -> bytes:
    header = MAGIC + struct.pack("<Qd", index, time.time()) + nonce[:8]
    payload = header + os.urandom(BLOCK_SIZE - len(header))
    return payload


def _check_block(data: bytes, index: int, nonce: bytes) -> tuple[bool, bool]:
    """Devuelve (ok, es_cero_o_ff)."""
    if data[:4] != MAGIC:
        zeros = all(b in (0x00, 0xFF) for b in data[:64])
        return False, zeros
    stored_index = struct.unpack("<Q", data[4:12])[0]
    return stored_index == index, False


def _full_write(fd: int, data: bytes) -> int:
    """Escribe todo el buffer, manejando escrituras parciales (Windows)."""
    view = memoryview(data)
    while view:
        n = os.write(fd, view)
        if n <= 0:
            break
        view = view[n:]
    return len(data) - len(view)


def _full_read(fd: int, size: int) -> bytes:
    """Lee exactamente size bytes (o menos en EOF), manejando lecturas parciales."""
    chunks = []
    remaining = size
    while remaining > 0:
        chunk = os.read(fd, remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def verify_device(
    device: str,
    capacity_bytes: int,
    max_blocks: int | None = None,
    on_progress=None,
) -> VerifyReport:
    """Prueba destructiva: escribe y relee todo el disco (o max_blocks bloques).

    ¡ADVERTENCIA: borra todos los datos del dispositivo!
    """
    report = VerifyReport(device=device, capacity_bytes=capacity_bytes)
    total_blocks = capacity_bytes // BLOCK_SIZE
    if max_blocks is not None:
        total_blocks = min(total_blocks, max_blocks)

    nonce = os.urandom(8)
    start = time.monotonic()
    write_start = time.monotonic()
    flags = os.O_RDWR | getattr(os, "O_BINARY", 0) | getattr(os, "O_LARGEFILE", 0)
    fd = os.open(device, flags)

    try:
        for index in range(total_blocks):
            block = _make_block(index, nonce)
            _full_write(fd, block)
            report.blocks_written += 1
            if on_progress and index % 16 == 0:
                on_progress("escritura", index + 1, total_blocks)
        os.fsync(fd)
        written_secs = max(time.monotonic() - write_start, 1e-6)
        report.write_mbps = report.blocks_written / written_secs

        os.lseek(fd, 0, os.SEEK_SET)
        read_start = time.monotonic()
        for index in range(report.blocks_written):
            data = _full_read(fd, BLOCK_SIZE)
            if len(data) < BLOCK_SIZE:
                break
            ok, zeroed = _check_block(data, index, nonce)
            if ok:
                report.blocks_ok += 1
                report.verified_bytes += BLOCK_SIZE
            else:
                report.blocks_corrupt += 1
                if zeroed:
                    report.blocks_zeroed += 1
                if report.first_bad_block is None:
                    report.first_bad_block = index
            if on_progress and index % 16 == 0:
                on_progress("lectura", index + 1, total_blocks)
        read_secs = max(time.monotonic() - read_start, 1e-6)
        report.read_mbps = report.blocks_ok / read_secs
    finally:
        os.close(fd)

    report.elapsed_seconds = time.monotonic() - start
    if report.blocks_corrupt > 0 and report.first_bad_block is not None:
        report.verified_bytes = report.first_bad_block * BLOCK_SIZE
    return report
