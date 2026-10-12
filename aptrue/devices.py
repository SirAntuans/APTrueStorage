"""Detección e inventario de dispositivos de almacenamiento (Linux)."""

from __future__ import annotations

import dataclasses
import glob
import os
import re


@dataclasses.dataclass
class StorageDevice:
    """Representa un dispositivo de almacenamiento detectado."""

    path: str
    name: str
    size_bytes: int
    removable: bool
    model: str = ""
    serial: str = ""
    vendor: str = ""
    rotational: bool | None = None
    device_type: str = "desconocido"

    @property
    def size_human(self) -> str:
        return _human_size(self.size_bytes)


def _human_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} TB"


def _read_first_line(filepath: str) -> str:
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _detect_type(sys_path: str, removable: bool) -> str:
    if os.path.exists(os.path.join(sys_path, "device", "cns")):
        return "NVMe SSD"
    rotational_file = os.path.join(sys_path, "queue", "rotational")
    rotational = _read_first_line(rotational_file)
    if rotational == "1":
        return "HDD"
    if rotational == "0":
        if removable:
            return "MicroSD / USB"
        return "SSD"
    return "desconocido"


def get_device(path: str) -> StorageDevice | None:
    """Devuelve información de un dispositivo dado su path (p.ej. /dev/sdb)."""
    if not os.path.exists(path):
        return None
    name = os.path.basename(path)
    sys_path = None
    for candidate in (f"/sys/block/{name}",):
        if os.path.exists(candidate):
            sys_path = candidate
            break
    if sys_path is None:
        sys_path = f"/sys/class/block/{name}"

    size_sectors = _read_first_line(os.path.join(sys_path, "size"))
    try:
        size_bytes = int(size_sectors) * 512
    except ValueError:
        size_bytes = 0
    if size_bytes == 0:
        size_bytes = _size_ioctl(path)

    removable = _read_first_line(os.path.join(sys_path, "removable")) == "1"
    device_sys = os.path.join(sys_path, "device")
    model = _read_first_line(os.path.join(device_sys, "model"))
    vendor = _read_first_line(os.path.join(device_sys, "vendor"))
    serial = _read_first_line(os.path.join(device_sys, "serial"))
    rotational_raw = _read_first_line(os.path.join(sys_path, "queue", "rotational"))
    rotational = bool(int(rotational_raw)) if rotational_raw in ("0", "1") else None

    return StorageDevice(
        path=path,
        name=name,
        size_bytes=size_bytes,
        removable=removable,
        model=model,
        serial=serial,
        vendor=vendor,
        rotational=rotational,
        device_type=_detect_type(sys_path, removable),
    )


def _size_ioctl(path: str) -> int:
    """Obtiene el tamaño del dispositivo con BLKGETSIZE64 (fallback)."""
    import fcntl
    import struct

    BLKGETSIZE64 = 0x80081272
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            buf = fcntl.ioctl(fd, BLKGETSIZE64, struct.pack("Q", 0))
            return struct.unpack("Q", buf)[0]
        finally:
            os.close(fd)
    except OSError:
        return 0


def list_devices() -> list[StorageDevice]:
    """Enumera todos los discos físicos (excluye particiones y discos virtuales)."""
    devices: list[StorageDevice] = []
    hidden_prefixes = ("loop", "ram", "zram", "dm-", "sr", "md")
    for sys_path in sorted(glob.glob("/sys/block/*")):
        name = os.path.basename(sys_path)
        if name.startswith(hidden_prefixes):
            continue
        dev = get_device(f"/dev/{name}")
        if dev is not None and dev.size_bytes > 0:
            devices.append(dev)
    return devices


def is_whole_disk(path: str) -> bool:
    """True si el path apunta a un disco completo y no a una partición."""
    name = os.path.basename(os.path.realpath(path))
    if not re.fullmatch(r"(sd[a-z]+|nvme\d+n\d+|mmcblk\d+|vd[a-z]|hd[a-z])", name):
        return False
    return os.path.exists(f"/sys/block/{name}")


def require_device_path(path: str) -> str:
    """Valida que el path sea un disco válido, o lanza ValueError."""
    if not os.path.exists(path):
        raise ValueError(f"El dispositivo {path} no existe")
    if not is_whole_disk(path):
        raise ValueError(
            f"{path} no es un disco completo (las pruebas destructivas solo "
            "se ejecutan sobre discos completos como /dev/sdb o /dev/nvme0n1)"
        )
    return path
