"""Detección e inventario de dispositivos de almacenamiento (multiplataforma).

- Linux: /sys/block
- Windows: Get-Disk (PowerShell) con fallback a \\\\.\\PhysicalDriveN vía CreateFileW
- macOS: diskutil
"""

from __future__ import annotations

import dataclasses
import glob
import os
import re
import subprocess
import sys

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"


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


# ---------------------------------------------------------------- Linux ----


def _detect_type(sys_path: str, removable: bool) -> str:
    if re.search(r"nvme\d+n\d+$", sys_path):
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


def _get_device_linux(path: str) -> StorageDevice | None:
    name = os.path.basename(os.path.realpath(path))
    sys_path = f"/sys/block/{name}"
    if not os.path.exists(sys_path):
        sys_path = f"/sys/class/block/{name}"
    if not os.path.exists(sys_path):
        return None

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
    """Obtiene el tamaño del dispositivo con BLKGETSIZE64 (Linux)."""
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


def _list_devices_linux() -> list[StorageDevice]:
    devices: list[StorageDevice] = []
    hidden_prefixes = ("loop", "ram", "zram", "dm-", "sr", "md")
    for sys_path in sorted(glob.glob("/sys/block/*")):
        name = os.path.basename(sys_path)
        if name.startswith(hidden_prefixes):
            continue
        dev = _get_device_linux(f"/dev/{name}")
        if dev is not None and dev.size_bytes > 0:
            devices.append(dev)
    return devices


# -------------------------------------------------------------- Windows ----

INVALID_HANDLE = 0xFFFFFFFFFFFFFFFF


def _win_create_file(path: str, access: int):
    """Abre un device path con CreateFileW; devuelve handle o None.

    access=0 (query) no requiere privilegios de administrador.
    """
    import ctypes

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CreateFileW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    handle = kernel32.CreateFileW(path, access, 3, None, 3, 0, None)
    if handle is None or handle == INVALID_HANDLE or handle == 0:
        return None
    return handle


def _windows_disk_size(path: str) -> int:
    """Tamaño del disco físico con IOCTL_DISK_GET_LENGTH_INFO (sin admin)."""
    import ctypes
    import struct

    IOCTL_DISK_GET_LENGTH_INFO = 0x0007405C
    kernel32 = ctypes.windll.kernel32
    handle = _win_create_file(path, 0)
    if handle is None:
        return 0
    try:
        buf = ctypes.create_string_buffer(8)
        ret = kernel32.DeviceIoControl(
            ctypes.c_void_p(handle), IOCTL_DISK_GET_LENGTH_INFO, None, 0, buf, 8, None, None
        )
        if ret:
            return struct.unpack("<Q", bytes(buf))[0]
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(handle))
    return 0


def _run_powershell_json(command: str):
    """Ejecuta PowerShell y devuelve el JSON parseado o None."""
    import json

    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        data = json.loads(proc.stdout.strip())
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        data = [data]
    return data


def _list_devices_windows_powershell() -> list[StorageDevice] | None:
    """Enumera discos con Get-Disk (funciona sin ser administrador)."""
    data = _run_powershell_json("Get-Disk | ConvertTo-Json -Compress")
    if data is None:
        return None
    devices = []
    for d in data:
        number = d.get("DeviceId")
        if number is None:
            number = d.get("Number")
        size = d.get("Size")
        if number is None or not size:
            continue
        bus = str(d.get("BusType", "")).lower()
        device_type = "disco"
        if "nvme" in bus:
            device_type = "NVMe SSD"
        elif "usb" in bus:
            device_type = "MicroSD / USB"
        else:
            rotation = d.get("RotationSpeed")
            if isinstance(rotation, int):
                device_type = "HDD" if rotation > 0 else "SSD"
        devices.append(
            StorageDevice(
                path=f"\\\\.\\PhysicalDrive{number}",
                name=f"PhysicalDrive{number}",
                size_bytes=int(size),
                removable=bus in ("usb", "sd", "mmc"),
                model=str(d.get("FriendlyName") or ""),
                serial=str(d.get("SerialNumber") or ""),
                vendor=str(d.get("Manufacturer") or ""),
                device_type=device_type,
            )
        )
    return devices


def _win_disk_model(index: int) -> str:
    """Modelo del disco vía PowerShell (fallback)."""
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Get-PhysicalDisk -DeviceNumber {index} | "
                "Select-Object -ExpandProperty FriendlyName",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        model = proc.stdout.strip()
        return model if model else ""
    except Exception:
        return ""


def _list_devices_windows_probe() -> list[StorageDevice]:
    """Fallback: probe directo de \\\\.\\PhysicalDrive0..31 vía CreateFileW."""
    devices: list[StorageDevice] = []
    for i in range(32):
        path = f"\\\\.\\PhysicalDrive{i}"
        size = _windows_disk_size(path)
        if size == 0:
            continue
        devices.append(
            StorageDevice(
                path=path,
                name=f"PhysicalDrive{i}",
                size_bytes=size,
                removable=False,
                model=_win_disk_model(i),
                device_type="disco",
            )
        )
    return devices


def _list_devices_windows() -> list[StorageDevice]:
    devs = _list_devices_windows_powershell()
    if devs:
        return devs
    return _list_devices_windows_probe()


def _get_device_windows(path: str) -> StorageDevice | None:
    m = re.search(r"PhysicalDrive(\d+)$", path)
    if not m:
        return None
    index = int(m.group(1))
    for dev in _list_devices_windows():
        if dev.name == f"PhysicalDrive{index}":
            return dev
    size = _windows_disk_size(path)
    if size == 0:
        return None
    return StorageDevice(
        path=path,
        name=f"PhysicalDrive{index}",
        size_bytes=size,
        removable=False,
        model=_win_disk_model(index),
        device_type="disco",
    )


# ----------------------------------------------------------------- macOS ----


def _list_devices_macos() -> list[StorageDevice]:
    try:
        proc = subprocess.run(
            ["diskutil", "list", "-plist"],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    import plistlib

    try:
        data = plistlib.loads(proc.stdout)
    except Exception:
        return []
    devices = []
    for d in data.get("AllDisksAndPartitions", []):
        identifier = d.get("DeviceIdentifier", "")
        if not re.fullmatch(r"disk\d+", identifier):
            continue
        size = d.get("TotalSize", 0)
        internal = d.get("Internal", False)
        if size > 0:
            devices.append(
                StorageDevice(
                    path=f"/dev/{identifier}",
                    name=identifier,
                    size_bytes=size,
                    removable=not internal,
                    model=d.get("UserVisibleName", ""),
                    device_type="disco",
                )
            )
    return devices


# ------------------------------------------------------------- API común ----


def get_device(path: str) -> StorageDevice | None:
    """Devuelve información de un dispositivo dado su path."""
    if IS_WINDOWS:
        return _get_device_windows(path)
    if IS_MACOS:
        for dev in _list_devices_macos():
            if dev.path == path:
                return dev
        return None
    if not os.path.exists(path):
        return None
    return _get_device_linux(path)


def list_devices() -> list[StorageDevice]:
    """Enumera los discos físicos del sistema (excluye virtuales)."""
    if IS_WINDOWS:
        return _list_devices_windows()
    if IS_MACOS:
        return _list_devices_macos()
    return _list_devices_linux()


def is_whole_disk(path: str) -> bool:
    """True si el path apunta a un disco completo y no a una partición."""
    if IS_WINDOWS:
        return bool(re.search(r"PhysicalDrive\d+$", path))
    name = os.path.basename(os.path.realpath(path))
    if IS_MACOS:
        return bool(re.fullmatch(r"disk\d+", name))
    if not re.fullmatch(r"(sd[a-z]+|nvme\d+n\d+|mmcblk\d+|vd[a-z]|hd[a-z])", name):
        return False
    return os.path.exists(f"/sys/block/{name}")


def require_device_path(path: str) -> str:
    """Valida que el path sea un disco válido, o lanza ValueError."""
    if IS_WINDOWS:
        if not is_whole_disk(path):
            raise ValueError(
                f"{path} no es un disco físico válido "
                "(usa \\\\.\\PhysicalDrive1 o el número del menú interactivo)"
            )
        return path
    if not os.path.exists(path):
        raise ValueError(f"El dispositivo {path} no existe")
    if not is_whole_disk(path):
        raise ValueError(
            f"{path} no es un disco completo (las pruebas destructivas solo "
            "se ejecutan sobre discos completos como /dev/sdb o /dev/nvme0n1)"
        )
    return path
