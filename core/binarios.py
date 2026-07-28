"""Localización y ejecución de las herramientas externas (adb, fastboot, mtkclient).

Todo el resto del programa pasa por aquí para hablar con el sistema. El objetivo
es que ningún módulo tenga que preocuparse de si un binario existe o no: las
funciones de este archivo nunca lanzan FileNotFoundError, devuelven un Resultado
con `ok = False` y un mensaje en español.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

# Sitios donde suele acabar platform-tools cuando no viene del gestor de paquetes.
RUTAS_EXTRA = [
    "/usr/bin",
    "/usr/local/bin",
    "/opt/platform-tools",
    "~/platform-tools",
    "~/Android/Sdk/platform-tools",
    "~/.local/share/android-sdk/platform-tools",
]

# Dónde buscar el mtk.py de MTKClient, en orden de preferencia.
RUTAS_MTKCLIENT = [
    "$MTKCLIENT_PATH",
    "~/mtkclient",
    "~/Documentos/mtkclient",
    "~/Documents/mtkclient",
    "./mtkclient",
    "/opt/mtkclient",
]

TIMEOUT_POR_DEFECTO = 20


@dataclass
class Resultado:
    """Resultado de un comando ya terminado."""

    ok: bool
    salida: str = ""
    error: str = ""
    codigo: int | None = None

    @property
    def texto(self) -> str:
        """Salida estándar y de error juntas (fastboot escribe en stderr)."""
        return "\n".join(p for p in (self.salida, self.error) if p).strip()


def _candidatos(nombre: str) -> Iterable[Path]:
    for base in RUTAS_EXTRA:
        ruta = Path(os.path.expandvars(base)).expanduser() / nombre
        yield ruta


def buscar_binario(nombre: str) -> str | None:
    """Devuelve la ruta absoluta de un binario, o None si no está instalado."""
    encontrado = shutil.which(nombre)
    if encontrado:
        return encontrado
    for ruta in _candidatos(nombre):
        if ruta.is_file() and os.access(ruta, os.X_OK):
            return str(ruta)
    return None


def hay_binario(nombre: str) -> bool:
    return buscar_binario(nombre) is not None


def buscar_mtkclient() -> str | None:
    """Devuelve la ruta al mtk.py de MTKClient, o None si no se encuentra."""
    for base in RUTAS_MTKCLIENT:
        expandida = os.path.expandvars(base)
        if expandida.startswith("$"):  # variable de entorno no definida
            continue
        carpeta = Path(expandida).expanduser()
        candidato = carpeta / "mtk.py"
        if candidato.is_file():
            return str(candidato)
        if carpeta.name == "mtk.py" and carpeta.is_file():
            return str(carpeta)
    en_path = shutil.which("mtk")
    return en_path


def ejecutar(
    cmd: Sequence[str],
    timeout: int = TIMEOUT_POR_DEFECTO,
    entrada: str | None = None,
) -> Resultado:
    """Ejecuta un comando y espera a que termine. Nunca lanza excepciones."""
    programa = buscar_binario(cmd[0]) if not os.path.isabs(cmd[0]) else cmd[0]
    if programa is None:
        return Resultado(
            ok=False,
            error=f"No se encuentra «{cmd[0]}» en el sistema.",
            codigo=None,
        )
    try:
        proceso = subprocess.run(
            [programa, *cmd[1:]],
            capture_output=True,
            text=True,
            timeout=timeout,
            input=entrada,
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return Resultado(
            ok=False,
            error=f"El comando «{cmd[0]}» tardó demasiado y se canceló.",
            codigo=None,
        )
    except OSError as exc:  # permisos, binario corrupto, etc.
        return Resultado(ok=False, error=f"No se pudo ejecutar «{cmd[0]}»: {exc}")
    return Resultado(
        ok=proceso.returncode == 0,
        salida=(proceso.stdout or "").strip(),
        error=(proceso.stderr or "").strip(),
        codigo=proceso.returncode,
    )


@dataclass
class ProcesoEnVivo:
    """Un proceso lanzado en segundo plano cuya salida se lee línea a línea."""

    proceso: subprocess.Popen | None = None
    hilo: threading.Thread | None = None
    cancelado: bool = field(default=False)

    def cancelar(self) -> None:
        """Corta el proceso. Se usa para el botón «Cancelar» del wizard."""
        self.cancelado = True
        if self.proceso is None or self.proceso.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(self.proceso.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                self.proceso.terminate()
            except OSError:
                pass

    def esperar(self, timeout: float | None = None) -> None:
        if self.hilo is not None:
            self.hilo.join(timeout)

    @property
    def activo(self) -> bool:
        return self.proceso is not None and self.proceso.poll() is None


def ejecutar_en_vivo(
    cmd: Sequence[str],
    al_recibir_linea: Callable[[str], None],
    al_terminar: Callable[[int], None] | None = None,
    cwd: str | None = None,
    env_extra: dict[str, str] | None = None,
) -> ProcesoEnVivo:
    """Lanza un comando en un hilo y llama a `al_recibir_linea` con cada línea.

    Devuelve un ProcesoEnVivo que permite cancelarlo. Las llamadas a los
    callbacks ocurren en el hilo de trabajo: la UI debe encolarlas, no tocar
    widgets de Tk directamente desde ahí.
    """
    handle = ProcesoEnVivo()

    programa = buscar_binario(cmd[0]) if not os.path.isabs(cmd[0]) else cmd[0]
    if programa is None:
        al_recibir_linea(f"ERROR: no se encuentra «{cmd[0]}» en el sistema.")
        if al_terminar:
            al_terminar(127)
        return handle

    entorno = os.environ.copy()
    # Sin buffering, si no la barra de progreso se mueve a saltos de 8 KB.
    entorno["PYTHONUNBUFFERED"] = "1"
    if env_extra:
        entorno.update(env_extra)

    def trabajar() -> None:
        try:
            # En binario, no en modo texto: hace falta leer con read1() para
            # ver la barra de progreso según sale, y eso solo lo ofrece el
            # buffer de bytes. La decodificación se hace aquí abajo.
            handle.proceso = subprocess.Popen(
                [programa, *cmd[1:]],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=cwd,
                env=entorno,
                start_new_session=True,  # para poder matar todo el grupo
            )
        except OSError as exc:
            al_recibir_linea(f"ERROR: no se pudo arrancar «{cmd[0]}»: {exc}")
            if al_terminar:
                al_terminar(127)
            return

        assert handle.proceso.stdout is not None
        for linea in _lineas(handle.proceso.stdout):
            if handle.cancelado:
                break
            if linea:
                al_recibir_linea(linea)

        codigo = handle.proceso.wait()
        if al_terminar:
            al_terminar(-1 if handle.cancelado else codigo)

    handle.hilo = threading.Thread(target=trabajar, daemon=True)
    handle.hilo.start()
    return handle


def _lineas(flujo) -> Iterable[str]:
    """Parte la salida en líneas tratando \\r como salto, además de \\n.

    MTKClient dibuja la barra de progreso reescribiendo la misma línea con \\r;
    si solo separásemos por \\n el progreso llegaría de golpe al final.

    Se lee con `read1`, que devuelve lo que haya disponible sin esperar a
    llenar el buffer. Con un `read(n)` normal la barra avanzaría a saltos de n
    bytes, y con `read(1)` habría una vuelta de bucle por carácter.
    """
    resto = b""
    separadores = re.compile(rb"[\r\n]")
    while True:
        try:
            trozo = flujo.read1(8192)
        except (ValueError, OSError):  # el flujo se cerró al cancelar
            break
        if not trozo:
            break
        resto += trozo
        partes = separadores.split(resto)
        resto = partes.pop()  # lo que va después del último salto: incompleto
        for parte in partes:
            yield parte.decode("utf-8", errors="replace").strip()
    if resto.strip():
        yield resto.decode("utf-8", errors="replace").strip()


def diagnostico() -> dict[str, str | None]:
    """Estado de las dependencias externas, para mostrarlo en la bienvenida."""
    return {
        "adb": buscar_binario("adb"),
        "fastboot": buscar_binario("fastboot"),
        "mtkclient": buscar_mtkclient(),
        "python": sys.executable,
    }
