"""Lectura de salud SMART vía smartctl (si está instalado)."""

from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
import sys


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
    raw_text: str = ""

    def summary(self) -> str:
        if not self.available:
            return (
                f"{self.device}: SMART no disponible "
                "(instala smartmontools: apt install smartmontools)"
            )
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


def _to_int(value: str) -> int | None:
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return None


def _find_smartctl() -> str | None:
    """Busca smartctl en PATH, junto al ejecutable y dentro del bundle PyInstaller."""
    found = shutil.which("smartctl")
    if found:
        return found
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
        for candidate in (os.path.join(base, "smartctl"), os.path.join(base, "smartctl.exe")):
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
    return None


def read_smart(device: str) -> SmartReport:
    report = SmartReport(device=device)
    smartctl = _find_smartctl()
    if smartctl is None:
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
        return report

    report.available = proc.returncode in (0, 4)
    report.raw_text = proc.stdout
    text = proc.stdout

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("overall-health") or "SMART overall-health" in stripped:
            report.overall = stripped.split(":")[-1].strip()
        elif stripped.startswith("Temperature:"):
            report.temperature_c = _to_int(stripped.split(":")[1].split()[0])
        elif "Power_On_Hours" in stripped and "0x" in stripped:
            parts = stripped.split()
            try:
                report.power_on_hours = int(parts[-1])
            except ValueError:
                pass
        elif "Reallocated_Sector" in stripped:
            parts = stripped.split()
            report.reallocated_sectors = _to_int(parts[-1])
        elif "Current_Pending_Sector" in stripped:
            parts = stripped.split()
            report.pending_sectors = _to_int(parts[-1])
        elif "Percentage Used" in stripped:
            report.wear_level = _to_int(stripped.split(":")[-1].replace("%", ""))
    return report
