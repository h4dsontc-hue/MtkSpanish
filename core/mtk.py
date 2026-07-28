"""Envoltorio de MTKClient (bkerler) — el motor real del rescate.

MTKClient se usa como proceso externo, no como librería. Es a propósito:

  * MTKClient necesita permisos de USB que a menudo obligan a lanzarlo con
    privilegios distintos a los de la interfaz gráfica.
  * Si el bootrom cuelga el proceso —cosa que pasa— se puede matar sin llevarse
    por delante la ventana del wizard.
  * Sus dependencias (pyusb, libusb) pueden vivir en un intérprete distinto al
    que ejecuta esta aplicación.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from core import binarios, errores


class MTKClientNoEncontrado(RuntimeError):
    """Se lanza cuando no hay forma de localizar mtk.py."""


@dataclass
class ConfiguracionObjetivo:
    """Lo que `gettargetconfig` cuenta sobre las protecciones del móvil."""

    sbc: bool | None = None
    daa: bool | None = None
    sla: bool | None = None
    hwcode: str = ""
    crudo: str = ""

    @property
    def protegido(self) -> bool:
        return bool(self.sbc or self.daa or self.sla)

    def explicacion(self) -> str:
        if not self.protegido:
            return (
                "Este móvil no tiene las protecciones del fabricante activadas: "
                "se puede rescatar por BROM sin problemas."
            )
        activas = [
            nombre
            for nombre, valor in (("SBC", self.sbc), ("DAA", self.daa), ("SLA", self.sla))
            if valor
        ]
        return (
            f"Este móvil tiene activadas las protecciones {', '.join(activas)}. "
            "Significa que el bootrom solo acepta cargadores firmados por el fabricante. "
            "Sin el fichero de autenticación correspondiente el rescate por BROM no funcionará; "
            "si el bootloader está desbloqueado, prueba por fastboot."
        )


_interprete_cacheado: str | None = None


def _interprete() -> str:
    """El Python con el que lanzar mtk.py.

    Se prefiere aquel que pueda importar pyusb: si esta aplicación corre en un
    entorno virtual sin pyusb pero el Python del sistema sí lo tiene, hay que
    usar el del sistema o MTKClient ni arrancará.

    El resultado se guarda: averiguarlo cuesta hasta tres subprocesos, y esto
    se llama en cada orden que se le manda a MTKClient.
    """
    global _interprete_cacheado
    if _interprete_cacheado is not None:
        return _interprete_cacheado

    candidatos = [sys.executable, shutil.which("python3"), shutil.which("python")]
    for candidato in candidatos:
        if not candidato:
            continue
        try:
            comprobacion = subprocess.run(
                [candidato, "-c", "import usb.core"],
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if comprobacion.returncode == 0:
            _interprete_cacheado = candidato
            return candidato
    _interprete_cacheado = sys.executable
    return _interprete_cacheado


def ruta_mtk() -> str:
    ruta = binarios.buscar_mtkclient()
    if ruta is None:
        raise MTKClientNoEncontrado(
            "No se encuentra MTKClient. Clónalo con:\n"
            "  git clone https://github.com/bkerler/mtkclient ~/mtkclient\n"
            "o define la variable de entorno MTKCLIENT_PATH con su carpeta."
        )
    return ruta


def disponible() -> bool:
    return binarios.buscar_mtkclient() is not None


def _comando(*argumentos: str) -> list[str]:
    ruta = ruta_mtk()
    if ruta.endswith(".py"):
        return [_interprete(), ruta, *argumentos]
    return [ruta, *argumentos]  # instalado como ejecutable «mtk»


def _cwd_mtk() -> str | None:
    """MTKClient espera ejecutarse desde su propia carpeta (busca Loader/, payloads/)."""
    try:
        return str(Path(ruta_mtk()).parent)
    except MTKClientNoEncontrado:
        return None


# ─────────────────────────── consultas rápidas ───────────────────────────


_PATRONES_CONFIG = {
    "sbc": re.compile(r"\bSBC\b\s*[:=]?\s*(\w+)", re.I),
    "daa": re.compile(r"\bDAA\b\s*[:=]?\s*(\w+)", re.I),
    "sla": re.compile(r"\bSLA\b\s*[:=]?\s*(\w+)", re.I),
}
_PATRON_HWCODE = re.compile(r"HW code\s*[:=]?\s*(0x[0-9a-f]+|\w+)", re.I)


def _a_booleano(texto: str) -> bool | None:
    texto = texto.strip().lower()
    if texto in ("true", "enabled", "1", "yes"):
        return True
    if texto in ("false", "disabled", "0", "no"):
        return False
    return None


def leer_configuracion(timeout: int = 90) -> ConfiguracionObjetivo:
    """Ejecuta `mtk gettargetconfig` y saca el estado de las protecciones.

    Requiere que el móvil esté conectado en BROM/preloader. Si no responde,
    devuelve una configuración vacía con el texto crudo dentro.
    """
    resultado = binarios.ejecutar(_comando("gettargetconfig"), timeout=timeout)
    texto = resultado.texto
    config = ConfiguracionObjetivo(crudo=texto)
    for campo, patron in _PATRONES_CONFIG.items():
        coincidencia = patron.search(texto)
        if coincidencia:
            setattr(config, campo, _a_booleano(coincidencia.group(1)))
    coincidencia = _PATRON_HWCODE.search(texto)
    if coincidencia:
        config.hwcode = coincidencia.group(1)
    return config


def listar_particiones(timeout: int = 120) -> list[str]:
    """Nombres de las particiones reales del móvil, según su tabla GPT."""
    resultado = binarios.ejecutar(_comando("printgpt"), timeout=timeout)
    particiones = []
    for linea in resultado.texto.splitlines():
        # El formato es del estilo: "boot                 Sector 0x...  ..."
        coincidencia = re.match(r"^([A-Za-z0-9_\-.]+)\s+Sector\s", linea.strip())
        if coincidencia:
            particiones.append(coincidencia.group(1))
    return particiones


# ─────────────────────────── operaciones largas ───────────────────────────


# Así dibuja MTKClient la barra: "Done |███-----| 45.5% boot (0x1/0x4),2 MB/s".
# Los caracteres de bloque y las barras verticales son lo que la distingue de
# un mensaje de verdad que casualmente lleve un porcentaje.
_ES_BARRA_DE_PROGRESO = re.compile(r"[█▓▒░]|\|\s*-+\s*\||^Done\s*\|")


@dataclass
class SeguimientoFlash:
    """Estado que la UI va leyendo mientras el flasheo avanza."""

    proceso: binarios.ProcesoEnVivo | None = None
    porcentaje: float = 0.0
    particion_actual: str = ""
    lineas: list[str] = field(default_factory=list)

    def cancelar(self) -> None:
        if self.proceso:
            self.proceso.cancelar()


def _envolver_callbacks(
    seguimiento: SeguimientoFlash,
    al_recibir_linea: Callable[[str], None],
    al_progresar: Callable[[float], None] | None,
) -> Callable[[str], None]:
    """Traduce cada línea, extrae el progreso y se lo pasa a la UI."""

    def manejar(linea_cruda: str) -> None:
        seguimiento.lineas.append(linea_cruda)

        porcentaje = errores.extraer_porcentaje(linea_cruda)
        if porcentaje is not None:
            seguimiento.porcentaje = porcentaje
            if al_progresar:
                al_progresar(porcentaje)
            # La barra de progreso se redibuja cientos de veces por partición.
            # Mueve la barra, pero no se escribe en el registro: si no, el
            # usuario no vería más que una catarata de líneas iguales.
            if _ES_BARRA_DE_PROGRESO.search(linea_cruda):
                return

        particion = re.search(r"(?:Writing|Wrote|Reading)\s+(?:partition\s+)?([\w.\-]+)", linea_cruda, re.I)
        if particion:
            seguimiento.particion_actual = particion.group(1)

        legible = errores.resumir_para_log(linea_cruda)
        if legible:
            al_recibir_linea(legible)

    return manejar


def lanzar_payload(
    al_recibir_linea: Callable[[str], None],
    al_terminar: Callable[[int], None] | None = None,
) -> SeguimientoFlash:
    """Envía el exploit al bootrom para abrir la sesión de escritura."""
    seguimiento = SeguimientoFlash()
    seguimiento.proceso = binarios.ejecutar_en_vivo(
        _comando("payload"),
        _envolver_callbacks(seguimiento, al_recibir_linea, None),
        al_terminar,
        cwd=_cwd_mtk(),
    )
    return seguimiento


def flashear_carpeta(
    ruta_firmware: str | Path,
    al_recibir_linea: Callable[[str], None],
    al_progresar: Callable[[float], None] | None = None,
    al_terminar: Callable[[int], None] | None = None,
) -> SeguimientoFlash:
    """Escribe en el móvil todas las imágenes de una carpeta (`mtk wl`).

    IMPORTANTE: `mtk wl` recorre la carpeta entera y trata *cada fichero* como
    una partición, usando el nombre del archivo sin extensión. Pasarle la
    carpeta del firmware tal cual haría que intentase escribir cosas como
    `flash_all.sh` o `android-info.txt`. Por eso se prepara antes una carpeta
    limpia con solo las imágenes de verdad (ver `preparar_carpeta_de_flasheo`).
    """
    seguimiento = SeguimientoFlash()
    seguimiento.proceso = binarios.ejecutar_en_vivo(
        _comando("wl", str(ruta_firmware)),
        _envolver_callbacks(seguimiento, al_recibir_linea, al_progresar),
        al_terminar,
        cwd=_cwd_mtk(),
    )
    return seguimiento


def escribir_particiones(
    particiones: dict[str, Path],
    al_recibir_linea: Callable[[str], None],
    al_progresar: Callable[[float], None] | None = None,
    al_terminar: Callable[[int], None] | None = None,
) -> SeguimientoFlash:
    """Escribe un conjunto concreto de particiones (`mtk w`)."""
    seguimiento = SeguimientoFlash()
    nombres = ",".join(particiones.keys())
    ficheros = ",".join(str(ruta) for ruta in particiones.values())
    seguimiento.proceso = binarios.ejecutar_en_vivo(
        _comando("w", nombres, ficheros),
        _envolver_callbacks(seguimiento, al_recibir_linea, al_progresar),
        al_terminar,
        cwd=_cwd_mtk(),
    )
    return seguimiento


def leer_particiones(
    particiones: list[str],
    carpeta: str | Path,
    al_recibir_linea: Callable[[str], None],
    al_progresar: Callable[[float], None] | None = None,
    al_terminar: Callable[[int], None] | None = None,
) -> SeguimientoFlash:
    """Vuelca particiones del móvil a disco (`mtk r`). Se usa para el backup.

    Cada partición se guarda como `<carpeta>/<nombre>.bin`, que es el mismo
    nombre que espera luego `escribir_particiones` para restaurarlas.
    """
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    nombres = ",".join(particiones)
    ficheros = ",".join(str(carpeta / f"{p}.bin") for p in particiones)
    seguimiento = SeguimientoFlash()
    seguimiento.proceso = binarios.ejecutar_en_vivo(
        _comando("r", nombres, ficheros),
        _envolver_callbacks(seguimiento, al_recibir_linea, al_progresar),
        al_terminar,
        cwd=_cwd_mtk(),
    )
    return seguimiento


def borrar_particiones(
    particiones: list[str],
    al_recibir_linea: Callable[[str], None],
    al_terminar: Callable[[int], None] | None = None,
) -> SeguimientoFlash:
    """Borra particiones enteras (`mtk e`). Se usa para quitar el bloqueo.

    Borrar `userdata` (y `metadata` en móviles con cifrado por archivo) es lo
    que quita un patrón o PIN olvidado: equivale a un reset de fábrica.
    """
    nombres = ",".join(particiones)
    seguimiento = SeguimientoFlash()
    seguimiento.proceso = binarios.ejecutar_en_vivo(
        _comando("e", nombres),
        _envolver_callbacks(seguimiento, al_recibir_linea, None),
        al_terminar,
        cwd=_cwd_mtk(),
    )
    return seguimiento


def reiniciar(al_recibir_linea: Callable[[str], None] | None = None) -> binarios.Resultado:
    resultado = binarios.ejecutar(_comando("reset"), timeout=60)
    if al_recibir_linea:
        al_recibir_linea(errores.resumir_para_log(resultado.texto) or resultado.texto)
    return resultado


def preparar_carpeta_de_flasheo(
    imagenes: dict[str, Path], destino: str | Path | None = None
) -> Path:
    """Crea una carpeta con solo las imágenes a escribir, ya renombradas.

    Se usan enlaces duros cuando se puede (mismo sistema de ficheros, coste
    cero) y copias cuando no. El nombre del enlace es `<particion>.bin` porque
    es de ahí de donde `mtk wl` deduce a qué partición va cada archivo.
    """
    carpeta = Path(destino) if destino else Path(tempfile.mkdtemp(prefix="rescatemtk-flash-"))
    carpeta.mkdir(parents=True, exist_ok=True)
    for particion, origen in imagenes.items():
        enlace = carpeta / f"{particion}.bin"
        if enlace.exists():
            enlace.unlink()
        try:
            os.link(origen, enlace)
        except OSError:
            shutil.copy2(origen, enlace)
    return carpeta
