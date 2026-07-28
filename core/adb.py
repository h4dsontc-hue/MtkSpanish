"""Órdenes de ADB, para cuando el móvil todavía arranca Android."""

from __future__ import annotations

from core import binarios
from core.detector import MODO_ADB, Dispositivo

# Propiedades de Android que interesan, con el nombre que les damos por dentro.
PROPIEDADES = {
    "ro.product.model": "modelo",
    "ro.product.device": "codename",
    "ro.product.manufacturer": "fabricante",
    "ro.build.version.release": "android",
    "ro.board.platform": "chipset",
    "ro.serialno": "serie",
}


def _getprop_todas() -> dict[str, str]:
    """Lee todas las propiedades de una sola vez.

    Llamar a `adb shell getprop X` una vez por propiedad, como haría el bucle
    obvio, tarda casi un segundo por cada una. `getprop` a secas las devuelve
    todas juntas en formato [clave]: [valor].
    """
    resultado = binarios.ejecutar(["adb", "shell", "getprop"], timeout=15)
    if not resultado.ok:
        return {}
    propiedades: dict[str, str] = {}
    for linea in resultado.salida.splitlines():
        if not linea.startswith("["):
            continue
        try:
            clave, valor = linea.split("]: [", 1)
        except ValueError:
            continue
        propiedades[clave[1:]] = valor.rstrip("]").strip()
    return propiedades


def describir_dispositivo() -> Dispositivo:
    """Construye el Dispositivo con todo lo que Android nos quiera contar."""
    propiedades = _getprop_todas()
    datos = {
        nombre: propiedades.get(clave, "")
        for clave, nombre in PROPIEDADES.items()
    }
    return Dispositivo(
        modo=MODO_ADB,
        modelo=datos["modelo"] or "desconocido",
        codename=datos["codename"],
        fabricante=datos["fabricante"],
        android=datos["android"],
        chipset=datos["chipset"],
        serie=datos["serie"],
    )


def reiniciar_a_fastboot() -> binarios.Resultado:
    """Reinicia el móvil al bootloader para poder flashearlo."""
    return binarios.ejecutar(["adb", "reboot", "bootloader"], timeout=20)


def reiniciar_a_recovery() -> binarios.Resultado:
    return binarios.ejecutar(["adb", "reboot", "recovery"], timeout=20)


def reiniciar() -> binarios.Resultado:
    return binarios.ejecutar(["adb", "reboot"], timeout=20)


def sideload(ruta_zip: str, al_recibir_linea) -> binarios.ProcesoEnVivo:
    """Instala un ZIP desde recovery. Puede tardar minutos, va en vivo."""
    return binarios.ejecutar_en_vivo(
        ["adb", "sideload", ruta_zip], al_recibir_linea
    )


def esperar_dispositivo(timeout: int = 60) -> bool:
    """Bloquea hasta que aparezca un móvil por ADB. True si apareció."""
    resultado = binarios.ejecutar(["adb", "wait-for-device"], timeout=timeout)
    return resultado.ok
