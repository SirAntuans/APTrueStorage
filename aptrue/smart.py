"""Lectura de salud SMART vía smartctl (embebido en el exe) o PowerShell."""

from __future__ import annotations

import dataclasses
import os
import re
import shutil
import subprocess
import sys

SMARTMONTOOLS_URL = "https://sourceforge.net/projects/smartmontools/files/smartmontools/"


@dataclasses.dataclass
class SmartReport:
    device: str
    available: bool = False
    overall: str = "desconocido"
    temperature_c: int | None = None
    power_on_hours: int | None = None
    reallocated_sectors: int | None = None
    pending_sectors: int | None = None
    wear_level: int | None = None
    hint: str = ""
    raw_text: str = ""

    def summary(self) -> str:
        if not self.available:
            lines = [f"{self.device}: SMART no disponible"]
            if self.hint:
                lines.append(f"  {self.hint}")
            return "\n".join(lines)
        lines = [
            f"{self.device}: SMART {self.overall}",
            f"  Temperatura: {self.temperature_c}°C",
            f"  Horas encendido: {self.power_on_hours}",
            f"  Sectores reasignados: {self.reallocated_sectors}",
            f"  Sectores pendientes: {self.pending_sectors}",
        ]
        if self.wear_level is not None:
            lines.append(f"  Desgaste NVMe: {self.wear_level}%")
        return "\n".join(lines)


def _to_int(value) -> int | None:
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def _find_smartctl() -> str | None:
    """Busca smartctl en PATH, junto al exe y dentro del bundle PyInstaller."""
    found = shutil.which("smartctl")
    if found:
        return found
    exe_dir = (
        os.path.dirname(os.path.abspath(sys.executable))
        if getattr(sys, "frozen", False)
        else os.path.dirname(os.path.abspath(__file__))
    )
    candidates = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", exe_dir)
        candidates += [os.path.join(meipass, "smartctl.exe"), os.path.join(meipass, "smartctl")]
    candidates += [
        os.path.join(exe_dir, "smartctl.exe"),
        os.path.join(exe_dir, "smartctl"),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.R_OK):
            return candidate
    return None


def _run_powershell_json(command: str):
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
        return json.loads(proc.stdout.strip())
    except json.JSONDecodeError:
        return None


def _smart_via_powershell(device: str) -> SmartReport | None:
    """Fallback sin smartmontools: Get-StorageReliabilityCounter (Windows)."""
    m = re.search(r"PhysicalDrive(\d+)", device)
    if not m:
        return None
    data = _run_powershell_json(
        f"Get-PhysicalDisk -DeviceNumber {m.group(1)} | "
        "Get-StorageReliabilityCounter | ConvertTo-Json -Compress"
    )
    if not data:
        return None
    rep = SmartReport(device=device, available=True, overall="OK (vía PowerShell)")
    temp = _to_int(data.get("Temperature"))
    if temp is not None:
        rep.temperature_c = temp - 273 if temp > 100 else temp
    wear = _to_int(data.get("Wear"))
    if wear is not None:
        rep.wear_level = wear
    rep.power_on_hours = _to_int(data.get("PowerOnHours"))
    return rep


def _parse_smartctl_text(rep: SmartReport, text: str) -> None:
    for line in text.splitlines():
        stripped = line.strip()
        if "overall-health" in stripped:
            rep.overall = stripped.split(":")[-1].strip()
        elif stripped.startswith("Temperature:"):
            parts = stripped.split(":")
            if len(parts) > 1:
                rep.temperature_c = _to_int(parts[1].split()[0])
        elif "Power_On_Hours" in stripped and "0x" in stripped:
            rep.power_on_hours = _to_int(stripped.split()[-1])
        elif stripped.startswith("Power On Hours:"):
            rep.power_on_hours = _to_int(stripped.split(":")[-1])
        elif "Reallocated_Sector" in stripped:
            rep.reallocated_sectors = _to_int(stripped.split()[-1])
        elif "Current_Pending_Sector" in stripped:
            rep.pending_sectors = _to_int(stripped.split()[-1])
        elif stripped.startswith("Percentage Used:"):
            rep.wear_level = _to_int(stripped.split(":")[-1].replace("%", ""))


def read_smart(device: str) -> SmartReport:
    report = SmartReport(device=device)
    smartctl = _find_smartctl()

    if smartctl is None:
        if sys.platform == "win32":
            ps_rep = _smart_via_powershell(device)
            if ps_rep is not None:
                return ps_rep
        report.hint = (
            "smartctl no encontrado. Descárgalo de "
            f"{SMARTMONTOOLS_URL} (en Linux: apt install smartmontools)"
        )
        return report

    try:
        proc = subprocess.run(
            [smartctl, "-a", device],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        report.hint = f"No se pudo ejecutar smartctl ({smartctl})"
        return report

    report.raw_text = proc.stdout
    # smartctl exit codes: bit 0 = error de CLI, bit 1 (2) = fallo al abrir
    if proc.returncode & 1:
        report.hint = "smartctl no reconoce el dispositivo o los argumentos."
        return report
    if proc.returncode & 2:
        report.available = True
        report.overall = "SIN ACCESO"
        report.hint = (
            "smartctl no pudo abrir el dispositivo. "
            "Ejecuta el programa como administrador "
            "(clic derecho > Ejecutar como administrador)."
        )
        return report

    report.available = True
    if "overall-health" not in proc.stdout:
        report.overall = "datos leídos"
    _parse_smartctl_text(report, proc.stdout)
    if report.overall == "desconocido" and proc.returncode == 0:
        report.overall = "PASSED"
    return report
