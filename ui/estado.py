"""Estado compartido entre los pasos del wizard.

Cada paso lee lo que dejó el anterior y escribe lo que necesitará el siguiente.
Tener un único objeto con todo evita que los pasos tengan que conocerse entre sí.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.detector import Dispositivo
from core.mtk import ConfiguracionObjetivo
from utils.validar import Firmware


@dataclass
class Estado:
    sistema_preparado: bool = False
    dispositivo: Dispositivo | None = None
    configuracion_objetivo: ConfiguracionObjetivo | None = None
    firmware: Firmware | None = None
    carpeta_descargas: Path = field(
        default_factory=lambda: Path.home() / "Descargas" / "RescateMTK"
    )

    # Resultado del flasheo, que lee el último paso.
    flash_correcto: bool = False
    flash_cancelado: bool = False
    registro_flash: list[str] = field(default_factory=list)
    mensaje_error: str = ""
    ruta_backup: str = ""

    def reiniciar_flasheo(self) -> None:
        self.flash_correcto = False
        self.flash_cancelado = False
        self.registro_flash = []
        self.mensaje_error = ""
        self.ruta_backup = ""

    @property
    def codename(self) -> str:
        return self.dispositivo.codename if self.dispositivo else ""

    @property
    def modo(self) -> str:
        return self.dispositivo.modo if self.dispositivo else ""
