"""Configuración común a todos los tests.

Lo más importante aquí: aislar el historial. Varios tests recorren el flasheo
hasta el final, que ahora escribe en el historial del usuario. Sin este
aislamiento, correr los tests ensuciaría —o borraría— el historial real de
quien esté desarrollando.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _historial_aislado(tmp_path, monkeypatch):
    """Redirige el historial a una carpeta temporal por test.

    core.historial usa XDG_DATA_HOME para decidir dónde escribir; apuntándolo a
    un tmp_path, ningún test toca la carpeta de datos real.
    """
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
