#!/usr/bin/env python3
"""Genera capturas de pantalla del wizard para el README.

Ejecútalo en TU máquina (donde la app ya funciona), no hace falta móvil:

    .venv/bin/python3 capturar.py

Recorre las 5 pantallas del asistente y la ventana de Herramientas rellenando
el estado con datos de ejemplo, y guarda un PNG de cada una en assets/capturas/.

Para la captura usa la primera herramienta que encuentre: grim (Wayland),
maim/scrot/import (X11), gnome-screenshot o spectacle. En Wayland lo más fiable
es grim:  sudo apt install grim
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

DESTINO = RAIZ / "assets" / "capturas"


def elegir_backend() -> str | None:
    for herramienta in ("grim", "maim", "scrot", "import", "gnome-screenshot", "spectacle"):
        if shutil.which(herramienta):
            return herramienta
    return None


def capturar(ventana, ruta: Path, backend: str) -> bool:
    ventana.update_idletasks()
    ventana.lift()
    try:
        ventana.attributes("-topmost", True)
    except Exception:
        pass
    ventana.focus_force()
    # Un par de vueltas de bucle + espera para que el compositor lo dibuje.
    for _ in range(5):
        ventana.update()
        time.sleep(0.15)
    time.sleep(0.4)

    x, y = ventana.winfo_rootx(), ventana.winfo_rooty()
    w, h = ventana.winfo_width(), ventana.winfo_height()

    comandos = {
        "grim": ["grim", "-g", f"{x},{y} {w}x{h}", str(ruta)],
        "maim": ["maim", "-g", f"{w}x{h}+{x}+{y}", str(ruta)],
        "scrot": ["scrot", "-a", f"{x},{y},{w},{h}", str(ruta)],
        "import": ["import", "-window", "root", "-crop", f"{w}x{h}+{x}+{y}", str(ruta)],
        "gnome-screenshot": ["gnome-screenshot", "-w", "-f", str(ruta)],
        "spectacle": ["spectacle", "-b", "-n", "-a", "-o", str(ruta)],
    }
    try:
        subprocess.run(comandos[backend], check=True, timeout=30)
    except Exception as exc:  # noqa: BLE001
        print(f"   ✘ fallo capturando {ruta.name} con {backend}: {exc}")
        return False
    try:
        ventana.attributes("-topmost", False)
    except Exception:
        pass
    print(f"   ✔ {ruta.name}")
    return True


def _firmware_de_ejemplo():
    from utils import validar

    carpeta = Path(tempfile.mkdtemp(prefix="capturas-fw-")) / "lancelot_global_images_V12.5.1.0"
    (carpeta / "images").mkdir(parents=True)
    for nombre, tam in [
        ("boot.img", 64 * 1024 * 1024),
        ("super.img", 2 * 1024 * 1024 * 1024),
        ("vbmeta.img", 64 * 1024),
        ("lk.img", 1024 * 1024),
        ("system.img", 1024 * 1024 * 1024),
    ]:
        # Archivos "dispersos" (sparse en disco): ocupan casi nada pero declaran
        # el tamaño, para que el resumen enseñe cifras realistas.
        with open(carpeta / "images" / nombre, "wb") as f:
            f.seek(tam - 1)
            f.write(b"\0")
    (carpeta / "images" / "android-info.txt").write_text("require board=lancelot\n")
    return validar.analizar(carpeta)


def _preparar_resultado(wizard):
    def hacer():
        wizard.estado.flash_correcto = True
        wizard.estado.ruta_backup = str(
            Path.home() / "Descargas/RescateMTK/backup-lancelot"
        )
    return hacer


def main() -> int:
    backend = elegir_backend()
    if backend is None:
        print(
            "No hay ninguna herramienta de captura instalada.\n"
            "En Wayland (Pop!_OS/GNOME):  sudo apt install grim\n"
            "En X11:                      sudo apt install maim   (o scrot)"
        )
        return 1

    DESTINO.mkdir(parents=True, exist_ok=True)
    print(f"Capturando con «{backend}» en {DESTINO}")

    import customtkinter as ctk

    from core.detector import MODO_BROM, Dispositivo
    from ui.wizard import Wizard

    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")

    dispositivo = Dispositivo(
        modo=MODO_BROM, modelo="Redmi 9", codename="lancelot",
        chipset="mt6768", android="11", serie="ABC123",
    )
    firmware = _firmware_de_ejemplo()

    wizard = Wizard()
    wizard.geometry("940x700+80+40")
    wizard.estado.dispositivo = dispositivo
    wizard.pasos[1].variable_auto.set(False)

    def sin_op():
        pass

    # (nombre, índice, antes de mostrar, después de mostrar). Algunas pantallas
    # se rellenan por callback (detectar, firmware) y hay que hacerlo DESPUÉS de
    # mostrarlas; otras leen el estado en al_entrar y hay que prepararlo ANTES.
    pasos = [
        ("1-bienvenida", 0, sin_op, sin_op),
        ("2-detectar", 1, sin_op, lambda: wizard.pasos[1]._al_detectar(dispositivo)),
        ("3-firmware", 2, sin_op, lambda: wizard.pasos[2]._al_analizar(firmware)),
        ("4-flashear", 3, lambda: setattr(wizard.estado, "firmware", firmware), sin_op),
        ("5-resultado", 4, _preparar_resultado(wizard), sin_op),
    ]

    for nombre, indice, antes, despues in pasos:
        antes()
        wizard.mostrar_paso(indice)
        despues()
        capturar(wizard, DESTINO / f"{nombre}.png", backend)

    # La ventana de herramientas, aparte.
    from ui.herramientas import VentanaHerramientas

    wizard.estado.dispositivo = dispositivo
    herramientas = VentanaHerramientas(wizard)
    herramientas.geometry("760x620+120+70")
    capturar(herramientas, DESTINO / "6-herramientas.png", backend)
    herramientas.destroy()

    wizard.destroy()
    print("\nListo. Revisa assets/capturas/. Si alguna salió mal, instala grim y repite.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
