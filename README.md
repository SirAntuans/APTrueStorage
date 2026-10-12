# APTrueStorage

Herramienta para verificar la **legitimidad, velocidad y autenticidad** de dispositivos de almacenamiento: HDD, SSD NVMe y tarjetas MicroSD.

Inspirada en herramientas como `f3` (Fight Flash Fraud): detecta discos y tarjetas falsificadas que reportan más capacidad de la real, mide velocidades reales y consulta la salud SMART.

> ⚠️ **Advertencia**: los comandos `verify` y `speed --destructive` **borran todos los datos** del dispositivo. Haz copia de seguridad antes.

## Características

- **Inventario de dispositivos**: detecta discos conectados con tipo (HDD / SSD NVMe / MicroSD-USB), modelo, serie y tamaño.
- **Verificación de autenticidad** (destructiva): escribe bloques firmados en todo el dispositivo y los relee. Si el fabricante falsificó la capacidad, los bloques más allá de la capacidad real salen corruptos o rellenos con ceros/0xFF → el disco es **FALSIFICADO**.
- **Benchmark de velocidad**: escritura y lectura secuencial en MB/s.
- **SMART**: temperatura, horas encendido, sectores reasignados/pendientes, desgaste NVMe (requiere `smartctl`).
- Salida JSON en todos los subcomandos (`--json`) para integración con otros sistemas.

## Descarga del ejecutable

Cada vez que se publica un *release* (o en cada push a `main`), GitHub Actions **compila automáticamente** un ejecutable standalone para:

- **Windows**: `aptrue-Windows.exe` (no requiere Python instalado)
- **Linux**: `aptrue-Linux`
- **macOS**: `aptrue-macOS`

Descárgalo desde la pestaña **Releases** o **Actions → Artifacts**. Ejecútalo directamente:

```bash
# Windows (como administrador)
aptrue-Windows.exe list
aptrue-Windows.exe verify E:

# Linux
chmod +x aptrue-Linux
sudo ./aptrue-Linux verify /dev/sdb
```

## Compilación manual del ejecutable

```bash
pip install pyinstaller .
pyinstaller --onefile --name aptrue aptrue/cli.py
# El ejecutable queda en dist/aptrue (dist/aptrue.exe en Windows)
```

## Instalación

```bash
pip install .
```

Para SMART, instala `smartmontools`:

```bash
sudo apt install smartmontools   # Debian/Ubuntu
```

## Uso

### Modo interactivo (recomendado)

Ejecuta el programa **sin argumentos** (o doble clic en `aptrue-Windows.exe`) y aparece un menú para elegir qué probar:

```
==========================
 APTrueStorage 0.1.2
==========================
Verificación de legitimidad de dispositivos de almacenamiento

--- Menú principal ---
  1. Listar dispositivos
  2. Salud SMART de un dispositivo
  3. Benchmark de velocidad
  4. Verificar autenticidad (DESTRUCTIVA)
  5. Informe completo (SMART + velocidad)
  q. Salir

Elige una opción:
```

El menú guía todo el proceso: lista los discos detectados, te deja elegir uno por número, y antes de cualquier prueba destructiva pide confirmación escribiendo `BORRAR`. No necesitas recordar ningún parámetro.

### Modo CLI (avanzado)

Todos los comandos siguen disponibles para automatización y scripts:

```bash
# Lista los dispositivos
sudo aptrue list


# Información detallada
aptrue info /dev/sdb

# Verificación de autenticidad (DESTRUCTIVA)
sudo aptrue verify /dev/sdb

# Limitar la prueba a N bloques de 1 MiB (prueba rápida)
sudo aptrue verify /dev/sdb --max-blocks 1024

# Benchmark de velocidad (lectura no destructiva)
sudo aptrue speed /dev/sdb

# Benchmark completo con escritura (DESTRUCTIVA)
sudo aptrue speed /dev/sdb --size-mb 1024 --destructive

# Salud SMART
sudo aptrue smart /dev/nvme0n1

# Informe completo: SMART + velocidad + verificación
sudo aptrue full /dev/sdb --verify
```

## Códigos de salida de `verify`

| Código | Significado |
|---|---|
| 0 | Dispositivo auténtico |
| 1 | Error (permisos, dispositivo inválido) |
| 2 | Dispositivo **falsificado** |

## Ejemplo de informe

```
Dispositivo: /dev/sdb
Resultado: FALSIFICADO
Capacidad declarada: 512.00 GB
Capacidad verificada: 31.50 GB
Bloques escritos: 496000
Bloques correctos: 30500
Bloques corruptos: 465500
Primer bloque defectuoso: #30500 (offset 31.50 GB)
```

## Desarrollo

```bash
pip install -e .
python -m aptrue.cli list
```

## Licencia

MIT

## Ejemplos de salida

### `aptrue list`
```
Dispositivo     Tipo              Tamaño  Modelo
/dev/nvme0n1    SSD               476.94 GB  Samsung SSD 970 EVO Plus
/dev/sdb        MicroSD / USB       59.49 GB  Storage Device
```

### `aptrue verify /dev/sdb` (disco falsificado)
```
¡ADVERTENCIA! Esta prueba es DESTRUCTIVA y borrará todos los datos.
Verificando /dev/sdb (capacidad declarada 59.49 GB)...
Dispositivo: /dev/sdb
Resultado: FALSIFICADO
Capacidad declarada: 59.49 GB
Capacidad verificada: 31.50 GB
Bloques escritos: 57272
Bloques correctos: 30720
Bloques corruptos: 26552
Tiempo: 1874.3s (escritura 20.31 MB/s, lectura 18.45 MB/s)
Primer bloque defectuoso: #30720 (offset 31.50 GB)
```

### `aptrue smart /dev/nvme0n1`
```
/dev/nvme0n1: SMART PASSED
  Temperatura: 42°C
  Horas encendido: 3412
  Sectores reasignados: 0
  Sectores pendientes: 0
  Desgaste NVMe: 3%
```

## Verificación de integridad de los ejecutables

Cada release incluye `checksums.txt` con los hashes SHA256 de los ejecutables. Después de descargar, valida que el archivo no fue modificado:

```bash
sha256sum -c checksums.txt --ignore-missing
```
