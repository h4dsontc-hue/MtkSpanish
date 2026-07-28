"""Detección del dispositivo conectado y en qué modo está.

Un móvil MediaTek puede aparecer de cuatro formas distintas y cada una se
maneja con una herramienta diferente:

  ADB       -> el sistema Android arranca. Se puede reiniciar a fastboot.
  FASTBOOT  -> el bootloader responde. Se flashea con fastboot.
  BROM      -> el móvil está "muerto": solo responde el bootrom. MTKClient.
  PRELOADER -> arranca el preloader pero no llega a Android. MTKClient también.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from core import binarios

VID_MEDIATEK = "0e8d"

# Productos conocidos del VID de MediaTek. El PID dice en qué punto del
# arranque se ha quedado el móvil, que es justo lo que necesitamos saber.
PIDS_BROM = {"0003"}
PIDS_PRELOADER = {"2000", "2001"}

MODO_ADB = "ADB"
MODO_FASTBOOT = "FASTBOOT"
MODO_BROM = "BROM"
MODO_PRELOADER = "PRELOADER"

DESCRIPCION_MODOS = {
    MODO_ADB: "Android encendido con depuración USB activada",
    MODO_FASTBOOT: "Modo fastboot (bootloader)",
    MODO_BROM: "Modo BROM — el móvil no arranca, pero se puede rescatar",
    MODO_PRELOADER: "Modo preloader — arranca a medias, se puede rescatar",
}


@dataclass
class Dispositivo:
    modo: str
    modelo: str = "desconocido"
    codename: str = ""
    fabricante: str = ""
    android: str = ""
    serie: str = ""
    chipset: str = ""
    puerto_usb: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def descripcion_modo(self) -> str:
        return DESCRIPCION_MODOS.get(self.modo, self.modo)

    @property
    def se_puede_flashear(self) -> bool:
        return self.modo in (MODO_FASTBOOT, MODO_BROM, MODO_PRELOADER)

    def resumen(self) -> str:
        partes = [f"Modo: {self.descripcion_modo}"]
        if self.modelo and self.modelo != "desconocido":
            partes.append(f"Modelo: {self.modelo}")
        if self.codename:
            partes.append(f"Nombre en clave: {self.codename}")
        if self.chipset:
            partes.append(f"Chipset: {self.chipset}")
        if self.android:
            partes.append(f"Android: {self.android}")
        return "\n".join(partes)


def _usb_mediatek() -> list[tuple[str, str]]:
    """Lista de (pid, ruta_sysfs) de los dispositivos MediaTek conectados.

    Se lee de /sys en vez de usar lsusb: así funciona aunque usbutils no esté
    instalado, que es lo normal en un equipo recién puesto.
    """
    encontrados: list[tuple[str, str]] = []
    raiz = Path("/sys/bus/usb/devices")
    if not raiz.is_dir():
        return encontrados
    for dispositivo in sorted(raiz.iterdir()):
        fichero_vid = dispositivo / "idVendor"
        fichero_pid = dispositivo / "idProduct"
        if not fichero_vid.is_file() or not fichero_pid.is_file():
            continue
        try:
            vid = fichero_vid.read_text().strip().lower()
            pid = fichero_pid.read_text().strip().lower()
        except OSError:
            continue
        if vid == VID_MEDIATEK:
            encontrados.append((pid, str(dispositivo)))
    return encontrados


def _usb_mediatek_por_lsusb() -> list[tuple[str, str]]:
    """Plan B por si /sys no está accesible (contenedores, sandbox)."""
    resultado = binarios.ejecutar(["lsusb"], timeout=5)
    if not resultado.ok:
        return []
    encontrados = []
    for linea in resultado.salida.splitlines():
        coincidencia = re.search(rf"ID\s+{VID_MEDIATEK}:([0-9a-f]{{4}})", linea, re.I)
        if coincidencia:
            encontrados.append((coincidencia.group(1).lower(), linea.strip()))
    return encontrados


def dispositivos_mediatek() -> list[tuple[str, str]]:
    return _usb_mediatek() or _usb_mediatek_por_lsusb()


def _dispositivos_adb() -> list[str]:
    """Números de serie de los móviles en modo ADB y autorizados."""
    resultado = binarios.ejecutar(["adb", "devices"], timeout=10)
    if not resultado.ok:
        return []
    series = []
    for linea in resultado.salida.splitlines()[1:]:  # la primera es la cabecera
        partes = linea.split()
        if len(partes) >= 2 and partes[1] == "device":
            series.append(partes[0])
    return series


def _hay_adb_sin_autorizar() -> bool:
    resultado = binarios.ejecutar(["adb", "devices"], timeout=10)
    return "unauthorized" in resultado.texto.lower()


def _dispositivos_fastboot() -> list[str]:
    resultado = binarios.ejecutar(["fastboot", "devices"], timeout=10)
    # fastboot escribe en stdout, pero algunas versiones usan stderr.
    series = []
    for linea in resultado.texto.splitlines():
        partes = linea.split()
        if len(partes) >= 2 and partes[1].startswith("fastboot"):
            series.append(partes[0])
    return series


def detectar_modo() -> str | None:
    """Devuelve el modo del dispositivo conectado, o None si no hay ninguno.

    El orden importa: un móvil en BROM también podría tener un adb fantasma de
    una sesión anterior, así que se comprueba de más específico a más genérico.
    """
    mediatek = dispositivos_mediatek()
    for pid, _ in mediatek:
        if pid in PIDS_BROM:
            return MODO_BROM
    for pid, _ in mediatek:
        if pid in PIDS_PRELOADER:
            return MODO_PRELOADER

    if _dispositivos_fastboot():
        return MODO_FASTBOOT
    if _dispositivos_adb():
        return MODO_ADB

    # MediaTek conectado con un PID que no conocemos: sigue siendo rescatable.
    if mediatek:
        return MODO_BROM
    return None


def detectar() -> Dispositivo | None:
    """Detecta el dispositivo y rellena todos los datos que se puedan sacar."""
    modo = detectar_modo()
    if modo is None:
        return None

    if modo == MODO_ADB:
        from core import adb

        return adb.describir_dispositivo()

    if modo == MODO_FASTBOOT:
        from core import fastboot

        return fastboot.describir_dispositivo()

    # BROM / PRELOADER: por USB solo sabemos el PID. El modelo real se obtiene
    # más tarde, cuando MTKClient consiga hablar con el bootrom.
    mediatek = dispositivos_mediatek()
    pid = mediatek[0][0] if mediatek else ""
    return Dispositivo(
        modo=modo,
        puerto_usb=f"{VID_MEDIATEK}:{pid}" if pid else "",
        extra={"pid": pid},
    )


def diagnostico_sin_dispositivo() -> str:
    """Explica por qué no se ve nada, con el consejo que toque."""
    if not binarios.hay_binario("adb") and not binarios.hay_binario("fastboot"):
        return (
            "No están instalados ni adb ni fastboot, así que solo se pueden detectar "
            "móviles en modo BROM. Vuelve al paso anterior para instalarlos."
        )
    if _hay_adb_sin_autorizar():
        return (
            "Hay un móvil conectado pero no ha autorizado a este ordenador.\n"
            "Mira la pantalla del móvil y acepta el aviso de depuración USB."
        )
    return (
        "No se detecta ningún dispositivo.\n\n"
        "Si el móvil no enciende (modo BROM):\n"
        "  1. Desconecta el cable del todo.\n"
        "  2. Mantén pulsado Encendido + Volumen abajo 10 segundos para apagarlo.\n"
        "  3. Pulsa «Detectar de nuevo» aquí.\n"
        "  4. Conecta el cable manteniendo pulsado VOLUMEN ABAJO.\n\n"
        "Usa un cable de datos (los de solo carga no valen) enchufado directamente "
        "al ordenador, sin hubs ni alargadores."
    )
