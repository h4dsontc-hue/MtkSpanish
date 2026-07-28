#!/usr/bin/env python3
"""RescateMTK — punto de entrada.

    python3 main.py

Antes de abrir la ventana se comprueba que las dependencias están: si falta
algo, un mensaje en la terminal explicando cómo instalarlo es mucho más útil
que un traceback de Python.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Para que `python3 /ruta/larga/main.py` funcione desde cualquier directorio y
# no solo estando dentro de la carpeta del proyecto.
sys.path.insert(0, str(Path(__file__).resolve().parent))

MINIMO_PYTHON = (3, 10)

AYUDA_TKINTER = """\
Falta tkinter, la librería gráfica de Python.

  Debian / Ubuntu / Pop!_OS :  sudo apt install python3-tk
  Fedora                    :  sudo dnf install python3-tkinter
  Arch / Manjaro            :  sudo pacman -S tk
  openSUSE                  :  sudo zypper install python3-tk
"""

AYUDA_DEPENDENCIAS = """\
Faltan dependencias de Python. Instálalas con:

  pip install -r requirements.txt
"""


def comprobar_entorno() -> list[str]:
    """Devuelve la lista de problemas que impiden arrancar."""
    problemas: list[str] = []

    if sys.version_info < MINIMO_PYTHON:
        problemas.append(
            f"Hace falta Python {MINIMO_PYTHON[0]}.{MINIMO_PYTHON[1]} o superior. "
            f"Tienes {sys.version_info.major}.{sys.version_info.minor}."
        )

    try:
        import tkinter  # noqa: F401
    except ImportError:
        problemas.append(AYUDA_TKINTER)

    faltan = []
    for modulo, paquete in (
        ("customtkinter", "customtkinter"),
        ("requests", "requests"),
        ("bs4", "beautifulsoup4"),
    ):
        try:
            __import__(modulo)
        except ImportError:
            faltan.append(paquete)
    if faltan:
        problemas.append(AYUDA_DEPENDENCIAS + "\nFaltan: " + ", ".join(faltan))

    return problemas


def main() -> int:
    problemas = comprobar_entorno()
    if problemas:
        print("No se puede arrancar RescateMTK:\n", file=sys.stderr)
        for problema in problemas:
            print(problema, file=sys.stderr)
            print(file=sys.stderr)
        return 1

    from ui.wizard import lanzar

    try:
        lanzar()
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
