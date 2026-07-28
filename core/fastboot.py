"""Órdenes de fastboot, para cuando responde el bootloader.

Ojo con una particularidad: fastboot escribe *todo* (incluidos los datos que
devuelve `getvar`) en stderr, no en stdout. Por eso aquí se lee siempre
`resultado.texto`, que junta las dos salidas.
"""

from __future__ import annotations

import re
from pathlib import Path

from core import binarios
from core.detector import MODO_FASTBOOT, Dispositivo

VARIABLES = {
    "product": "modelo",
    "version-bootloader": "bootloader",
    "serialno": "serie",
    "secure": "seguro",
    "unlocked": "desbloqueado",
}

# Particiones que no se tocan nunca en un flasheo normal: son las que guardan
# el IMEI, las calibraciones de radio y las claves del dispositivo. Escribirlas
# con datos de otro móvil lo deja sin cobertura de forma irreversible.
PARTICIONES_PROHIBIDAS = {
    "nvram", "nvdata", "nvcfg", "persist", "protect1", "protect2",
    "seccfg", "sec1", "proinfo", "efuse", "frp",
}


def _getvar(nombre: str) -> str:
    resultado = binarios.ejecutar(["fastboot", "getvar", nombre], timeout=15)
    for linea in resultado.texto.splitlines():
        coincidencia = re.match(rf"{re.escape(nombre)}:\s*(.*)", linea.strip())
        if coincidencia:
            return coincidencia.group(1).strip()
    return ""


def describir_dispositivo() -> Dispositivo:
    datos = {nombre: _getvar(var) for var, nombre in VARIABLES.items()}
    desbloqueado = datos.get("desbloqueado", "").lower()
    return Dispositivo(
        modo=MODO_FASTBOOT,
        modelo=datos.get("modelo") or "desconocido",
        codename=datos.get("modelo", ""),
        serie=datos.get("serie", ""),
        extra={
            "bootloader": datos.get("bootloader", ""),
            "desbloqueado": desbloqueado,
        },
    )


def bootloader_desbloqueado() -> bool | None:
    """True/False si se puede saber, None si el móvil no contesta a la pregunta."""
    valor = _getvar("unlocked").lower()
    if valor in ("yes", "true", "1"):
        return True
    if valor in ("no", "false", "0"):
        return False
    return None


def flashear_particion(particion: str, ruta_img: str) -> binarios.Resultado:
    return binarios.ejecutar(
        ["fastboot", "flash", particion, ruta_img], timeout=600
    )


def flashear_lote(
    particiones: list[tuple[str, Path]],
    al_recibir_linea,
    al_terminar=None,
    saltar_criticas: bool = True,
):
    """Flashea varias particiones seguidas informando del progreso.

    Se hace en Python en vez de llamar al flash_all.sh del firmware porque ese
    script asume que hay una terminal, no informa del progreso de forma legible
    y a menudo incluye pasos que borran cosas que aquí no queremos tocar.
    """
    import threading

    handle = binarios.ProcesoEnVivo()

    def trabajar() -> None:
        total = len(particiones)
        fallos = 0
        for indice, (nombre, ruta) in enumerate(particiones, start=1):
            if handle.cancelado:
                al_recibir_linea("Cancelado por el usuario.")
                break
            if saltar_criticas and nombre in PARTICIONES_PROHIBIDAS:
                al_recibir_linea(
                    f"[{indice}/{total}] Se salta «{nombre}»: contiene datos únicos "
                    "de este móvil (IMEI, calibración) y no debe sobrescribirse."
                )
                continue
            al_recibir_linea(f"[{indice}/{total}] Escribiendo la partición {nombre}...")
            resultado = flashear_particion(nombre, str(ruta))
            if resultado.ok:
                al_recibir_linea(f"[{indice}/{total}] {nombre}: correcto")
            else:
                fallos += 1
                al_recibir_linea(f"ERROR al escribir {nombre}: {resultado.texto}")
        if al_terminar:
            al_terminar(-1 if handle.cancelado else (1 if fallos else 0))

    handle.hilo = threading.Thread(target=trabajar, daemon=True)
    handle.hilo.start()
    return handle


def desbloquear_bootloader() -> binarios.Resultado:
    """Pide el desbloqueo. BORRA TODOS LOS DATOS del móvil."""
    resultado = binarios.ejecutar(["fastboot", "flashing", "unlock"], timeout=60)
    if not resultado.ok:
        # Los bootloaders antiguos usan la orden vieja.
        resultado = binarios.ejecutar(["fastboot", "oem", "unlock"], timeout=60)
    return resultado


def borrar_datos_usuario() -> binarios.Resultado:
    return binarios.ejecutar(["fastboot", "-w"], timeout=300)


def reiniciar() -> binarios.Resultado:
    return binarios.ejecutar(["fastboot", "reboot"], timeout=30)
