"""Sistema de actualizaciones para la app y para MTKClient.

Se comprueban dos cosas por separado, porque se desfasan a ritmos distintos:

  * RescateMTK (esta app) — repo h4dsontc-hue/MtkSpanish.
  * MTKClient — repo bkerler/mtkclient. Es el que más importa mantener al día:
    cada versión añade soporte de chipsets nuevos, y una copia vieja hace que
    un rescate falle sin motivo aparente.

La comprobación es de solo lectura contra la API pública de GitHub (sin token).
La actualización, cuando la copia es un clon de git, es un `git pull --ff-only`:
si el usuario tiene cambios propios, se aborta sin tocar nada en vez de pisarlos.

Nada de esto bloquea el arranque: si no hay internet, se dice y punto.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from core import binarios

VERSION = "1.0.0"

REPO_APP = "h4dsontc-hue/MtkSpanish"
RAMA_APP = "main"
REPO_MTKCLIENT = "bkerler/mtkclient"
RAMA_MTKCLIENT = "main"

API = "https://api.github.com"
CABECERAS = {"Accept": "application/vnd.github+json", "User-Agent": "RescateMTK"}
TIMEOUT = 12

COMP_APP = "app"
COMP_MTKCLIENT = "mtkclient"

NOMBRES = {COMP_APP: "RescateMTK", COMP_MTKCLIENT: "MTKClient"}


@dataclass
class EstadoActualizacion:
    componente: str
    version_local: str = ""
    hay_actualizacion: bool = False
    se_puede_actualizar: bool = False  # es un clon de git sobre el que hacer pull
    detalle: str = ""
    error: str = ""
    commits_por_detras: int = 0
    ruta: Path | None = None

    @property
    def nombre(self) -> str:
        return NOMBRES.get(self.componente, self.componente)

    def resumen(self) -> str:
        if self.error:
            return f"{self.nombre}: {self.error}"
        if self.hay_actualizacion:
            cuantos = (
                f" ({self.commits_por_detras} cambios por detrás)"
                if self.commits_por_detras
                else ""
            )
            return f"{self.nombre}: hay una versión más nueva{cuantos}."
        return f"{self.nombre}: al día."


# ─────────────────────────── utilidades de git ───────────────────────────


def _dir_app() -> Path:
    """La carpeta raíz del proyecto (la que contiene main.py)."""
    return Path(__file__).resolve().parent.parent


def _es_clon_git(carpeta: Path) -> bool:
    return (carpeta / ".git").exists()


def _sha_local(carpeta: Path) -> str | None:
    resultado = binarios.ejecutar(
        ["git", "-C", str(carpeta), "rev-parse", "HEAD"], timeout=10
    )
    return resultado.salida.strip() if resultado.ok else None


def _sha_remota(repo: str, rama: str) -> str | None:
    """El SHA del último commit de una rama, vía API de GitHub."""
    try:
        respuesta = requests.get(
            f"{API}/repos/{repo}/commits/{rama}", headers=CABECERAS, timeout=TIMEOUT
        )
        if respuesta.status_code != 200:
            return None
        return respuesta.json().get("sha")
    except (requests.RequestException, ValueError):
        return None


def _comparar(repo: str, rama: str, sha_local: str) -> tuple[str, int] | None:
    """Compara el commit local con la punta de la rama remota.

    Devuelve (estado, commits_por_detras) donde estado es el de la API de
    GitHub: "identical", "behind", "ahead" o "diverged". None si no se pudo
    consultar (por ejemplo, si el commit local no está en GitHub).
    """
    try:
        respuesta = requests.get(
            f"{API}/repos/{repo}/compare/{sha_local}...{rama}",
            headers=CABECERAS,
            timeout=TIMEOUT,
        )
        if respuesta.status_code != 200:
            return None
        datos = respuesta.json()
        return datos.get("status", ""), int(datos.get("behind_by", 0))
    except (requests.RequestException, ValueError):
        return None


def _comprobar(componente: str, carpeta: Path | None, repo: str, rama: str) -> EstadoActualizacion:
    estado = EstadoActualizacion(componente=componente, ruta=carpeta)

    if carpeta is None or not carpeta.exists():
        estado.error = "no encontrado en el sistema."
        return estado

    if not _es_clon_git(carpeta):
        estado.error = (
            "no es un clon de git, así que no se puede actualizar solo. "
            "Descárgalo de nuevo si quieres la última versión."
        )
        return estado

    sha_local = _sha_local(carpeta)
    if not sha_local:
        estado.error = "no se pudo leer la versión instalada."
        return estado
    estado.version_local = sha_local[:7]
    estado.se_puede_actualizar = True

    comparacion = _comparar(repo, rama, sha_local)
    if comparacion is None:
        # Plan B: comparar SHAs a pelo. Menos fino (no sabe cuántos commits),
        # pero al menos distingue «igual» de «distinto».
        sha_remota = _sha_remota(repo, rama)
        if sha_remota is None:
            estado.error = "no se pudo consultar GitHub (¿sin internet?)."
            return estado
        estado.hay_actualizacion = sha_remota != sha_local
        estado.detalle = "comparación aproximada."
        return estado

    situacion, por_detras = comparacion
    estado.commits_por_detras = por_detras
    estado.hay_actualizacion = situacion in ("behind", "diverged") and por_detras > 0
    estado.detalle = situacion
    return estado


# ─────────────────────────── API pública ───────────────────────────


def comprobar_app() -> EstadoActualizacion:
    return _comprobar(COMP_APP, _dir_app(), REPO_APP, RAMA_APP)


def comprobar_mtkclient() -> EstadoActualizacion:
    ruta_mtk = binarios.buscar_mtkclient()
    carpeta = Path(ruta_mtk).parent if ruta_mtk and ruta_mtk.endswith(".py") else None
    return _comprobar(COMP_MTKCLIENT, carpeta, REPO_MTKCLIENT, RAMA_MTKCLIENT)


def comprobar_todo() -> list[EstadoActualizacion]:
    return [comprobar_app(), comprobar_mtkclient()]


def actualizar(
    carpeta: Path,
    al_recibir_linea: Callable[[str], None],
    al_terminar: Callable[[int], None] | None = None,
) -> binarios.ProcesoEnVivo:
    """Actualiza un clon de git con `git pull --ff-only`.

    `--ff-only` es la parte importante: solo avanza si no hay conflicto. Si el
    usuario tiene commits o cambios propios, git aborta y avisa en vez de
    sobrescribir su trabajo.
    """
    return binarios.ejecutar_en_vivo(
        ["git", "-C", str(carpeta), "pull", "--ff-only"],
        al_recibir_linea,
        al_terminar,
    )
