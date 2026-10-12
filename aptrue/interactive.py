"""Modo interactivo: menú para elegir dispositivo y prueba sin argumentos."""

from __future__ import annotations

import argparse

from . import __version__
from . import devices as devices_mod
from . import smart as smart_mod
from . import speed as speed_mod
from . import verify as verify_mod

MB = 1024 * 1024


def _input(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return "q"


def _pause() -> None:
    _input("\nPresiona Enter para volver al menú...")


def _choose_device() -> devices_mod.StorageDevice | None:
    devs = devices_mod.list_devices()
    if not devs:
        print("\nNo se encontraron dispositivos de almacenamiento.")
        print("Conecta un disco, SSD o MicroSD y vuelve a intentarlo.")
        _pause()
        return None
    print("\n--- Dispositivos detectados ---")
    for i, d in enumerate(devs, start=1):
        print(f"  {i}. {d.path:<14} {d.device_type:<15} {d.size_human:>12}  {d.model or '-'}")
    choice = _input("\nElige un dispositivo (número, o 'q' para salir): ")
    if choice.lower() == "q":
        return None
    try:
        idx = int(choice)
        return devs[idx - 1]
    except (ValueError, IndexError):
        print("Selección inválida.")
        _pause()
        return None


def _confirm_destructive(dev) -> bool:
    print(f"\n*** ADVERTENCIA ***")
    print(f"Esta prueba BORRARÁ TODOS LOS DATOS de {dev.path} ({dev.size_human}).")
    print("Si es un disco con información importante, haz copia de seguridad primero.")
    answer = _input(f"Escribe BORRAR para confirmar y destruir {dev.path}: ")
    return answer == "BORRAR"


def _do_smart(dev) -> int:
    rep = smart_mod.read_smart(dev.path)
    print()
    print(rep.summary())
    _pause()
    return 0 if rep.available else 1


def _do_speed(dev) -> int:
    print("\n--- Benchmark de velocidad ---")
    print("  1. Lectura (no destructiva)")
    print("  2. Escritura + lectura (DESTRUCTIVA: borra el disco)")
    choice = _input("Elige el tipo de benchmark (1/2): ")
    if choice == "2":
        if not _confirm_destructive(dev):
            print("Cancelado.")
            _pause()
            return 1
        print(f"\nMidiendo {dev.path}...")
        res = speed_mod.run_benchmark(dev.path, 256 * MB, destructive=True)
    else:
        print(f"\nMidiendo {dev.path}...")
        res = speed_mod.run_benchmark(dev.path, 256 * MB, destructive=False)
    print()
    print(res.summary())
    _pause()
    return 0 if not res.error else 1


def _progress(phase: str, done: int, total: int) -> None:
    pct = 100.0 * done / total if total else 0
    print(f"\r{phase}: {done}/{total} bloques ({pct:.1f}%)", end="", flush=True)


def _do_verify(dev) -> int:
    print(f"\nCapacidad declarada: {dev.size_human}")
    choice = _input("¿Probar el disco COMPLETO o una muestra rápida (completo/muestra)? ")
    max_blocks = None
    if choice.lower().startswith("m"):
        size_str = _input("Tamaño de la muestra en MiB (ej. 1024): ")
        try:
            max_blocks = max(1, int(size_str))
        except ValueError:
            print("Tamaño inválido; se usará 1024 MiB.")
            max_blocks = 1024
    if not _confirm_destructive(dev):
        print("Cancelado.")
        _pause()
        return 1
    print(f"\nVerificando {dev.path} (capacidad declarada {dev.size_human})...")
    report = verify_mod.verify_device(
        dev.path, dev.size_bytes, max_blocks=max_blocks, on_progress=_progress
    )
    print()
    print(report.summary())
    if not report.is_authentic:
        print("\n*** EL DISPOSITIVO ES FALSIFICADO ***")
    _pause()
    return 0 if report.is_authentic else 2


def _do_full(dev) -> int:
    print(f"\n=== Informe completo: {dev.path} ===")
    print(f"Tipo: {dev.device_type}  Tamaño declarado: {dev.size_human}")
    print(f"Modelo: {dev.model or '-'}  Serie: {dev.serial or '-'}")
    rep = smart_mod.read_smart(dev.path)
    print()
    print(rep.summary())
    print("\nBenchmark (lectura, no destructiva)...")
    res = speed_mod.run_benchmark(dev.path, 64 * MB, destructive=False)
    print(res.summary())
    _pause()
    return 0


def run_interactive() -> int:
    """Menú principal. Se ejecuta cuando la CLI no recibe argumentos."""
    while True:
        print(f"\n==========================")
        print(f" APTrueStorage {__version__}")
        print(f"==========================")
        print("Verificación de legitimidad de dispositivos de almacenamiento")
        print("\n--- Menú principal ---")
        print("  1. Listar dispositivos")
        print("  2. Salud SMART de un dispositivo")
        print("  3. Benchmark de velocidad")
        print("  4. Verificar autenticidad (DESTRUCTIVA)")
        print("  5. Informe completo (SMART + velocidad)")
        print("  q. Salir")
        choice = _input("\nElige una opción: ").lower()

        if choice == "q":
            print("Hasta pronto.")
            return 0
        if choice == "1":
            devs = devices_mod.list_devices()
            if not devs:
                print("\nNo se encontraron dispositivos.")
            else:
                print()
                print(f"{'Dispositivo':<14} {'Tipo':<15} {'Tamaño':>12}  Modelo")
                for d in devs:
                    print(f"{d.path:<14} {d.device_type:<15} {d.size_human:>12}  {d.model or '-'}")
            _pause()
        elif choice in ("2", "3", "4", "5"):
            dev = _choose_device()
            if dev is None:
                if choice == "q":
                    return 0
                continue
            if choice == "2":
                _do_smart(dev)
            elif choice == "3":
                _do_speed(dev)
            elif choice == "4":
                _do_verify(dev)
            else:
                _do_full(dev)
        else:
            print("Opción inválida.")


def main_interactive() -> int:
    """Punto de entrada interactivo (usado por el exe sin argumentos)."""
    try:
        return run_interactive()
    except KeyboardInterrupt:
        print("\nCancelado.")
        return 130
