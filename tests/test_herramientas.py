"""Tests de core/herramientas: backup, restauración y borrado de bloqueo."""

from __future__ import annotations

from pathlib import Path

import pytest

from core import herramientas
from core.detector import MODO_ADB, MODO_BROM, MODO_FASTBOOT, MODO_PRELOADER


class TestQueSePuedeHacerSegunElModo:
    def test_el_backup_solo_por_brom(self):
        assert herramientas.modo_permite_backup(MODO_BROM)
        assert herramientas.modo_permite_backup(MODO_PRELOADER)
        # fastboot no tiene orden para leer particiones.
        assert not herramientas.modo_permite_backup(MODO_FASTBOOT)
        assert not herramientas.modo_permite_backup(MODO_ADB)


class TestParticionesARespaldar:
    def test_solo_las_criticas_que_existen(self):
        gpt = ["boot", "nvram", "nvdata", "system", "persist", "super"]
        elegidas = herramientas.particiones_a_respaldar(gpt)
        assert elegidas == ["nvram", "nvdata", "persist"]

    def test_respeta_el_orden_canonico(self):
        # Aunque el GPT las liste al revés, salen en orden fijo.
        gpt = ["persist", "nvdata", "proinfo", "nvram"]
        assert herramientas.particiones_a_respaldar(gpt) == [
            "proinfo", "nvram", "nvdata", "persist"
        ]

    def test_movil_sin_criticas(self):
        assert herramientas.particiones_a_respaldar(["boot", "system"]) == []

    def test_consulta_al_movil_si_no_se_le_pasa_lista(self, monkeypatch):
        from core import mtk

        monkeypatch.setattr(mtk, "listar_particiones", lambda: ["nvram", "boot"])
        assert herramientas.particiones_a_respaldar() == ["nvram"]


class TestBackupsEnCarpeta:
    def test_reconoce_los_bin_criticos(self, tmp_path):
        (tmp_path / "nvram.bin").write_bytes(b"\x00")
        (tmp_path / "nvdata.bin").write_bytes(b"\x00")
        (tmp_path / "boot.bin").write_bytes(b"\x00")  # no es crítica
        (tmp_path / "notas.txt").write_text("x")

        encontrados = herramientas.backups_en(tmp_path)
        assert set(encontrados) == {"nvram", "nvdata"}
        assert encontrados["nvram"].name == "nvram.bin"

    def test_carpeta_inexistente(self, tmp_path):
        assert herramientas.backups_en(tmp_path / "no-existe") == {}

    def test_carpeta_sin_backups(self, tmp_path):
        (tmp_path / "cualquier.cosa").write_text("x")
        assert herramientas.backups_en(tmp_path) == {}


class TestRespaldar:
    def test_llama_a_mtk_con_las_particiones(self, tmp_path, monkeypatch):
        from core import mtk

        capturado = {}

        def falso(particiones, carpeta, **kwargs):
            capturado["particiones"] = particiones
            capturado["carpeta"] = carpeta
            return "seguimiento"

        monkeypatch.setattr(mtk, "leer_particiones", falso)
        resultado = herramientas.respaldar(
            tmp_path, ["nvram", "nvdata"], al_recibir_linea=lambda l: None
        )
        assert resultado == "seguimiento"
        assert capturado["particiones"] == ["nvram", "nvdata"]


class TestRestaurar:
    def test_sin_backups_devuelve_none(self, tmp_path):
        assert herramientas.restaurar(tmp_path, al_recibir_linea=lambda l: None) is None

    def test_escribe_los_bin_encontrados(self, tmp_path, monkeypatch):
        from core import mtk

        (tmp_path / "nvram.bin").write_bytes(b"\x00")
        (tmp_path / "nvdata.bin").write_bytes(b"\x00")

        capturado = {}
        monkeypatch.setattr(
            mtk,
            "escribir_particiones",
            lambda imagenes, **k: capturado.update(imagenes=imagenes) or "ok",
        )
        resultado = herramientas.restaurar(tmp_path, al_recibir_linea=lambda l: None)
        assert resultado == "ok"
        assert set(capturado["imagenes"]) == {"nvram", "nvdata"}


class TestBorrarBloqueo:
    def test_por_brom_borra_userdata_y_metadata(self, monkeypatch):
        from core import mtk

        capturado = {}
        monkeypatch.setattr(
            mtk,
            "borrar_particiones",
            lambda particiones, **k: capturado.update(p=particiones) or "seg",
        )
        resultado = herramientas.borrar_bloqueo_pantalla(
            MODO_BROM, al_recibir_linea=lambda l: None
        )
        assert resultado == "seg"
        assert capturado["p"] == ["userdata", "metadata"]

    def test_por_adb_no_hace_nada_y_avisa(self):
        avisos = []
        resultado = herramientas.borrar_bloqueo_pantalla(
            MODO_ADB, al_recibir_linea=avisos.append
        )
        assert resultado is None
        assert any("reiniciar" in a.lower() for a in avisos)

    def test_fastboot_con_bootloader_bloqueado_se_niega(self, monkeypatch):
        from core import fastboot

        monkeypatch.setattr(fastboot, "bootloader_desbloqueado", lambda: False)
        avisos = []
        codigos = []
        handle = herramientas.borrar_bloqueo_pantalla(
            MODO_FASTBOOT, al_recibir_linea=avisos.append, al_terminar=codigos.append
        )
        handle.esperar(10)
        assert any("bloqueado" in a.lower() for a in avisos)
        assert codigos == [1]

    def test_fastboot_desbloqueado_borra_las_dos(self, monkeypatch):
        from core import binarios, fastboot

        monkeypatch.setattr(fastboot, "bootloader_desbloqueado", lambda: True)
        borradas = []
        monkeypatch.setattr(
            binarios,
            "ejecutar",
            lambda cmd, **k: borradas.append(cmd[2]) or binarios.Resultado(True),
        )
        avisos = []
        codigos = []
        handle = herramientas.borrar_bloqueo_pantalla(
            MODO_FASTBOOT, al_recibir_linea=avisos.append, al_terminar=codigos.append
        )
        handle.esperar(10)
        assert borradas == ["userdata", "metadata"]
        assert codigos == [0]

    def test_fastboot_sin_metadata_no_es_error(self, monkeypatch):
        from core import binarios, fastboot

        monkeypatch.setattr(fastboot, "bootloader_desbloqueado", lambda: True)

        def ejecutar(cmd, **k):
            # userdata bien, metadata no existe.
            if cmd[2] == "metadata":
                return binarios.Resultado(False, error="partition not found")
            return binarios.Resultado(True)

        monkeypatch.setattr(binarios, "ejecutar", ejecutar)
        codigos = []
        handle = herramientas.borrar_bloqueo_pantalla(
            MODO_FASTBOOT, al_recibir_linea=lambda l: None, al_terminar=codigos.append
        )
        handle.esperar(10)
        assert codigos == [0]  # metadata ausente no cuenta como fallo


class TestGuias:
    def test_existen_y_no_prometen_bypass(self):
        # La guía de cuentas tiene que dejar claro qué NO se hace.
        assert "NO la retira" in herramientas.GUIA_CUENTAS
        assert "factura" in herramientas.GUIA_CUENTAS.lower()
        assert "Mi Unlock" in herramientas.GUIA_DESBLOQUEO_BOOTLOADER


class TestMtkNuevas:
    def test_leer_particiones_construye_el_comando(self, tmp_path, monkeypatch):
        from core import binarios, mtk

        monkeypatch.setattr(mtk, "ruta_mtk", lambda: "/x/mtk.py")
        monkeypatch.setattr(mtk, "_interprete", lambda: "python3")
        monkeypatch.setattr(mtk, "_cwd_mtk", lambda: None)

        capturado = {}

        def falso(cmd, *a, **k):
            capturado["cmd"] = cmd
            return binarios.ProcesoEnVivo()

        monkeypatch.setattr(binarios, "ejecutar_en_vivo", falso)
        mtk.leer_particiones(["nvram", "nvdata"], tmp_path, al_recibir_linea=lambda l: None)
        cmd = capturado["cmd"]
        assert cmd[2] == "r"
        assert cmd[3] == "nvram,nvdata"
        assert cmd[4] == f"{tmp_path / 'nvram.bin'},{tmp_path / 'nvdata.bin'}"

    def test_borrar_particiones_construye_el_comando(self, monkeypatch):
        from core import binarios, mtk

        monkeypatch.setattr(mtk, "ruta_mtk", lambda: "/x/mtk.py")
        monkeypatch.setattr(mtk, "_interprete", lambda: "python3")
        monkeypatch.setattr(mtk, "_cwd_mtk", lambda: None)

        capturado = {}
        monkeypatch.setattr(
            binarios,
            "ejecutar_en_vivo",
            lambda cmd, *a, **k: capturado.update(cmd=cmd) or binarios.ProcesoEnVivo(),
        )
        mtk.borrar_particiones(["userdata", "metadata"], al_recibir_linea=lambda l: None)
        assert capturado["cmd"][2] == "e"
        assert capturado["cmd"][3] == "userdata,metadata"
