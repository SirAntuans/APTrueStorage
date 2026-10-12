"""CLI de APTrueStorage."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from . import devices as devices_mod
from . import smart as smart_mod
from . import speed as speed_mod
from . import verify as verify_mod

MB = 1024 * 1024


def cmd_list(args: argparse.Namespace) -> int:
    devs = devices_mod.list_devices()
    if args.json:
        print(json.dumps([dataclasses_asdict(d) for d in devs], indent=2))
        return 0
    if not devs:
        print("No se encontraron dispositivos.")
        return 1
    print(f"{'Dispositivo':<14} {'Tipo':<15} {'Tamaño':>12}  Modelo")
    for d in devs:
        print(f"{d.path:<14} {d.device_type:<15} {d.size_human:>12}  {d.model or '-'}")
    return 0


def dataclasses_asdict(obj):
    import dataclasses

    return dataclasses.asdict(obj)


def cmd_info(args: argparse.Namespace) -> int:
    dev = devices_mod.get_device(args.device)
    if dev is None:
        print(f"Error: no se pudo leer {args.device}", file=sys.stderr)
        return 1
    print(json.dumps(dataclasses_asdict(dev), indent=2))
    return 0


def cmd_speed(args: argparse.Namespace) -> int:
    devices_mod.require_device_path(args.device)
    size = args.size_mb * MB
    if args.json:
        res = speed_mod.run_benchmark(args.device, size, destructive=args.destructive)
        print(json.dumps(dataclasses_asdict(res), indent=2))
        return 0 if not res.error else 1
    print("Advertencia: el benchmark destructivo BORRA los datos del disco.")
    print(f"Midiendo {args.device} ({args.size_mb} MiB)...")
    res = speed_mod.run_benchmark(args.device, size, destructive=args.destructive)
    print(res.summary())
    return 0 if not res.error else 1


def _progress(phase: str, done: int, total: int) -> None:
    pct = 100.0 * done / total if total else 0
    sys.stdout.write(f"\r{phase}: {done}/{total} bloques ({pct:.1f}%)")
    sys.stdout.flush()


def cmd_verify(args: argparse.Namespace) -> int:
    devices_mod.require_device_path(args.device)
    dev = devices_mod.get_device(args.device)
    if dev is None:
        print(f"Error: no se pudo leer {args.device}", file=sys.stderr)
        return 1
    max_blocks = None
    if args.max_blocks > 0:
        max_blocks = args.max_blocks
    print("¡ADVERTENCIA! Esta prueba es DESTRUCTIVA y borrará todos los datos.")
    print(f"Verificando {args.device} (capacidad declarada {dev.size_human})...")
    report = verify_mod.verify_device(
        args.device,
        dev.size_bytes,
        max_blocks=max_blocks,
        on_progress=None if args.json else _progress,
    )
    print()
    if args.json:
        print(json.dumps(dataclasses_asdict(report), indent=2))
    else:
        print(report.summary())
    return 0 if report.is_authentic else 2


def cmd_smart(args: argparse.Namespace) -> int:
    rep = smart_mod.read_smart(args.device)
    print(rep.summary())
    return 0 if rep.available else 1


def cmd_full(args: argparse.Namespace) -> int:
    devices_mod.require_device_path(args.device)
    dev = devices_mod.get_device(args.device)
    if dev is None:
        print(f"Error: no se pudo leer {args.device}", file=sys.stderr)
        return 1
    print(f"=== Informe completo: {args.device} ===")
    print(f"Tipo: {dev.device_type}  Tamaño declarado: {dev.size_human}")
    print(f"Modelo: {dev.model or '-'}  Serie: {dev.serial or '-'}")
    print()
    rep = smart_mod.read_smart(args.device)
    print(rep.summary())
    print()
    print("Benchmark (lectura, no destructivo)...")
    res = speed_mod.run_benchmark(args.device, 64 * MB, destructive=False)
    print(res.summary())
    if args.verify:
        print()
        return cmd_verify(args)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aptrue",
        description=(
            "Verifica legitimidad, velocidad y autenticidad de dispositivos "
            "de almacenamiento (HDD, SSD NVMe, MicroSD)."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="Lista los dispositivos detectados")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("info", help="Muestra detalles de un dispositivo")
    p.add_argument("device")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("speed", help="Benchmark de velocidad secuencial")
    p.add_argument("device")
    p.add_argument("--size-mb", type=int, default=256)
    p.add_argument("--destructive", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_speed)

    p = sub.add_parser("verify", help="Prueba destructiva de capacidad/autenticidad")
    p.add_argument("device")
    p.add_argument("--max-blocks", type=int, default=0)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("smart", help="Lectura SMART (requiere smartctl)")
    p.add_argument("device")
    p.set_defaults(func=cmd_smart)

    p = sub.add_parser("full", help="Informe completo (SMART + velocidad + verificación)")
    p.add_argument("device")
    p.add_argument("--verify", action="store_true")
    p.set_defaults(func=cmd_full)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    # Sin argumentos (doble clic en el exe): modo interactivo
    raw_argv = sys.argv[1:] if argv is None else list(argv)
    if not raw_argv:
        from .interactive import main_interactive

        return main_interactive()
    args = parser.parse_args(raw_argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except PermissionError:
        print("Error: permiso denegado. Ejecuta como root (sudo).", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
