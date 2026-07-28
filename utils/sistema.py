"""Preparación del sistema Linux para hablar con dispositivos MediaTek.

Hay que hacer tres cosas antes de que MTKClient pueda ver el móvil:

  1. Callar a ModemManager y brltty, que secuestran el puerto en cuanto aparece.
  2. Instalar reglas udev que den permiso al usuario sobre el USB de MediaTek.
  3. Recargar udev para que las reglas se apliquen sin reiniciar.

Todo eso necesita root. En vez de pedir la contraseña siete veces (una por
comando, como haría lanzar cada `sudo` por separado), se genera un único script
y se ejecuta de una sola vez con pkexec, que además muestra un diálogo gráfico
en lugar de pedir la contraseña por una terminal que el usuario no está viendo.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

RUTA_REGLAS = "/etc/udev/rules.d/51-MTK-brom.rules"

# 0e8d = MediaTek (BROM/Preloader), 18d1 = Google (fastboot genérico),
# 2717 = Xiaomi, 0bb4 = HTC/varios, 1004 = LG. Cubre los casos habituales.
REGLAS_UDEV = """\
# Generado por RescateMTK - reglas de acceso para recuperación MediaTek
SUBSYSTEM=="usb", ATTR{idVendor}=="0e8d", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="18d1", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="2717", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="0bb4", MODE="0666", GROUP="plugdev"
KERNEL=="ttyACM*", MODE="0666", GROUP="plugdev"
KERNEL=="ttyUSB*", MODE="0666", GROUP="plugdev"
"""

PASOS = [
    "Deteniendo ModemManager",
    "Deteniendo brltty",
    "Descargando módulos de kernel conflictivos",
    "Instalando reglas de permisos USB",
    "Recargando reglas del sistema",
    "Reinstalando el driver de puerto serie",
]


@dataclass
class ResultadoPreparacion:
    ok: bool
    mensaje: str
    detalle: str = ""


def _script_de_preparacion() -> str:
    """El script que se ejecutará como root, de una sola pasada."""
    return f"""#!/bin/sh
# RescateMTK - preparación del sistema. Los fallos individuales no son fatales:
# en muchos equipos ModemManager ni siquiera está instalado, y eso está bien.

echo "PASO:Deteniendo ModemManager"
systemctl stop ModemManager.service 2>/dev/null
systemctl disable ModemManager.service 2>/dev/null

echo "PASO:Deteniendo brltty"
systemctl stop brltty.service 2>/dev/null
systemctl stop brltty-udev.service 2>/dev/null

echo "PASO:Descargando módulos de kernel conflictivos"
rmmod cdc_acm 2>/dev/null
rmmod option 2>/dev/null

echo "PASO:Instalando reglas de permisos USB"
cat > {RUTA_REGLAS} <<'FIN_DE_REGLAS'
{REGLAS_UDEV}FIN_DE_REGLAS
chmod 644 {RUTA_REGLAS} || exit 20

echo "PASO:Recargando reglas del sistema"
udevadm control --reload-rules || exit 21
udevadm trigger

echo "PASO:Reinstalando el driver de puerto serie"
modprobe cdc_acm 2>/dev/null

echo "LISTO"
exit 0
"""


def somos_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def metodo_de_elevacion() -> str | None:
    """Cómo vamos a conseguir permisos de root: 'root', 'pkexec', 'sudo' o None."""
    if somos_root():
        return "root"
    if shutil.which("pkexec") and os.environ.get("DISPLAY"):
        return "pkexec"
    if shutil.which("sudo"):
        return "sudo"
    return None


def sistema_ya_preparado() -> bool:
    """¿Están ya instaladas las reglas udev de esta herramienta?"""
    return Path(RUTA_REGLAS).is_file()


def preparar_sistema(al_avanzar=None) -> ResultadoPreparacion:
    """Ejecuta la preparación completa.

    `al_avanzar` se llama con (nombre_del_paso, indice, total) según progresa.
    Devuelve un ResultadoPreparacion con un mensaje ya listo para enseñar.
    """
    metodo = metodo_de_elevacion()
    if metodo is None:
        return ResultadoPreparacion(
            ok=False,
            mensaje="No se puede pedir permiso de administrador",
            detalle=(
                "Este sistema no tiene ni pkexec ni sudo disponibles. "
                "Abre una terminal como root y ejecuta el script tú mismo."
            ),
        )

    with tempfile.NamedTemporaryFile(
        "w", suffix=".sh", prefix="rescatemtk-", delete=False
    ) as fichero:
        fichero.write(_script_de_preparacion())
        ruta_script = fichero.name
    os.chmod(ruta_script, 0o755)

    if metodo == "root":
        comando = ["/bin/sh", ruta_script]
    elif metodo == "pkexec":
        comando = ["pkexec", "/bin/sh", ruta_script]
    else:
        # `-n` es imprescindible: sin terminal donde escribir, un sudo que pida
        # contraseña se quedaría esperando para siempre y colgaría la ventana.
        # Así falla al instante y se le puede decir al usuario qué hacer.
        comando = ["sudo", "-n", "/bin/sh", ruta_script]

    try:
        proceso = subprocess.Popen(
            comando,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            errors="replace",
        )
        lineas: list[str] = []
        hecho = 0
        assert proceso.stdout is not None
        for linea in proceso.stdout:
            linea = linea.rstrip()
            lineas.append(linea)
            if linea.startswith("PASO:") and al_avanzar:
                hecho += 1
                al_avanzar(linea[5:], hecho, len(PASOS))
        codigo = proceso.wait(timeout=120)
    except subprocess.TimeoutExpired:
        return ResultadoPreparacion(
            ok=False,
            mensaje="La preparación tardó demasiado",
            detalle="Puede que el diálogo de contraseña se quedara esperando. Inténtalo otra vez.",
        )
    except OSError as exc:
        return ResultadoPreparacion(
            ok=False, mensaje="No se pudo ejecutar la preparación", detalle=str(exc)
        )
    finally:
        try:
            os.unlink(ruta_script)
        except OSError:
            pass

    salida = "\n".join(lineas)

    if codigo == 0:
        return ResultadoPreparacion(
            ok=True,
            mensaje="Sistema preparado correctamente",
            detalle=salida,
        )
    if codigo == 126:  # pkexec: el usuario canceló el diálogo
        return ResultadoPreparacion(
            ok=False,
            mensaje="Cancelaste la petición de contraseña",
            detalle="Sin permisos de administrador no se pueden aplicar las reglas USB.",
        )
    if codigo == 127:
        return ResultadoPreparacion(
            ok=False,
            mensaje="No se encontró el programa para pedir la contraseña",
            detalle=salida,
        )
    if metodo == "sudo" and codigo == 1 and "password" in salida.lower():
        return ResultadoPreparacion(
            ok=False,
            mensaje="Hace falta la contraseña y aquí no se puede pedir",
            detalle=(
                "Este sistema no tiene pkexec, así que no hay forma de mostrarte "
                "el diálogo de contraseña desde la ventana.\n\n"
                "Abre una terminal y ejecuta:\n\n"
                "    sudo -v\n\n"
                "Después vuelve aquí y pulsa «Preparar sistema» otra vez.\n"
                "(O instala policykit-1, que es la solución definitiva.)"
            ),
        )
    return ResultadoPreparacion(
        ok=False,
        mensaje="La preparación falló",
        detalle=salida or f"El script terminó con el código {codigo}.",
    )


def revisar_entorno() -> list[tuple[str, bool, str]]:
    """Comprobaciones para mostrar en la pantalla de bienvenida.

    Devuelve una lista de (descripción, está_bien, consejo_si_no).
    """
    from core import binarios

    revisiones: list[tuple[str, bool, str]] = []

    revisiones.append(
        (
            "Reglas de permisos USB instaladas",
            sistema_ya_preparado(),
            "Pulsa «Preparar sistema» aquí abajo.",
        )
    )
    revisiones.append(
        (
            "MTKClient encontrado",
            binarios.buscar_mtkclient() is not None,
            "Clónalo con: git clone https://github.com/bkerler/mtkclient ~/mtkclient",
        )
    )
    revisiones.append(
        (
            "ADB instalado",
            binarios.hay_binario("adb"),
            "Instálalo con: sudo apt install android-tools-adb  (o el paquete de tu distribución)",
        )
    )
    revisiones.append(
        (
            "Fastboot instalado",
            binarios.hay_binario("fastboot"),
            "Instálalo con: sudo apt install android-tools-fastboot",
        )
    )
    revisiones.append(
        (
            "Se puede pedir permiso de administrador",
            metodo_de_elevacion() is not None,
            "Instala policykit-1 o sudo.",
        )
    )
    return revisiones
