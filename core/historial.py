"""Historial de rescates: qué se flasheó, cuándo y cómo acabó.

Se guarda un JSON append-only en la carpeta de datos del usuario. Sirve para
dos cosas muy prácticas: recordar qué firmware se le puso a un móvil la última
vez, y tener a mano los datos cuando hay que pedir ayuda en un foro.

Nada de esto es crítico: si el archivo se corrompe o no se puede escribir, se
empieza de cero sin molestar. Registrar en el historial NUNCA debe hacer
fracasar un rescate que sí salió bien.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path

# Se recorta a esto para que el archivo no crezca sin límite.
MAXIMO = 200

RESULTADO_OK = "correcto"
RESULTADO_CANCELADO = "cancelado"
RESULTADO_ERROR = "error"


@dataclass
class Entrada:
    fecha: str = ""
    modelo: str = ""
    codename: str = ""
    modo: str = ""
    firmware: str = ""
    resultado: str = ""
    backup: str = ""

    @classmethod
    def ahora(cls, **campos) -> "Entrada":
        campos.setdefault("fecha", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        return cls(**campos)

    def linea(self) -> str:
        icono = {
            RESULTADO_OK: "✔",
            RESULTADO_CANCELADO: "⚠",
            RESULTADO_ERROR: "✘",
        }.get(self.resultado, "·")
        modelo = self.modelo or self.codename or "móvil desconocido"
        partes = [f"{icono} {self.fecha}", modelo]
        if self.firmware:
            partes.append(self.firmware)
        partes.append(self.resultado or "?")
        return "   ".join(partes)


def ruta_historial() -> Path:
    base = Path(
        os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
    )
    return base / "rescatemtk" / "historial.json"


def leer(ruta: Path | None = None) -> list[dict]:
    ruta = ruta or ruta_historial()
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return []
    # Un archivo manipulado a mano podría no ser una lista.
    return datos if isinstance(datos, list) else []


def entradas(ruta: Path | None = None) -> list[Entrada]:
    """El historial como objetos, de la más reciente a la más antigua."""
    validos = {f.name for f in fields(Entrada)}
    resultado = []
    for registro in leer(ruta):
        if isinstance(registro, dict):
            resultado.append(Entrada(**{k: v for k, v in registro.items() if k in validos}))
    resultado.reverse()
    return resultado


def registrar(entrada: Entrada, ruta: Path | None = None) -> bool:
    """Añade una entrada al historial. Devuelve False si no se pudo, sin lanzar.

    El que devuelva False en vez de propagar la excepción es a propósito: quien
    llama está en mitad de un flasheo y un fallo aquí no puede tumbar nada.
    """
    ruta = ruta or ruta_historial()
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        datos = leer(ruta)
        datos.append(asdict(entrada))
        datos = datos[-MAXIMO:]
        ruta.write_text(
            json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True
    except (OSError, TypeError, ValueError):
        return False


def texto_completo(ruta: Path | None = None) -> str:
    lista = entradas(ruta)
    if not lista:
        return "Todavía no hay ningún rescate en el historial."
    return "\n".join(e.linea() for e in lista)
