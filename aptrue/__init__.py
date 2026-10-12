"""APTrueStorage - Verificación de legitimidad de dispositivos de almacenamiento.

Herramienta para auditar HDD, SSD NVMe y tarjetas MicroSD:
- Detección e inventario de dispositivos
- Benchmark de velocidad secuencial (lectura/escritura)
- Verificación de capacidad real y autenticidad (estilo f3)
- Salud SMART (si smartctl está disponible)
"""

__version__ = "0.2.1"
