"""Tests del sistema de actualizaciones. Nada toca la red de verdad."""

from __future__ import annotations

from pathlib import Path

import pytest

from core import actualizaciones


class RespuestaFalsa:
    def __init__(self, codigo=200, datos=None):
        self.status_code = codigo
        self._datos = datos or {}

    def json(self):
        return self._datos


def _carpeta_git(tmp_path):
    (tmp_path / ".git").mkdir()
    return tmp_path


class TestComprobar:
    def test_no_es_clon_de_git(self, tmp_path):
        estado = actualizaciones._comprobar("app", tmp_path, "x/y", "main")
        assert not estado.se_puede_actualizar
        assert "no es un clon" in estado.error

    def test_carpeta_inexistente(self, tmp_path):
        estado = actualizaciones._comprobar("app", tmp_path / "no", "x/y", "main")
        assert "no encontrado" in estado.error

    def test_carpeta_none(self):
        estado = actualizaciones._comprobar("mtkclient", None, "x/y", "main")
        assert "no encontrado" in estado.error

    def test_al_dia(self, tmp_path, monkeypatch):
        carpeta = _carpeta_git(tmp_path)
        monkeypatch.setattr(actualizaciones, "_sha_local", lambda c: "a" * 40)
        monkeypatch.setattr(
            actualizaciones.requests,
            "get",
            lambda *a, **k: RespuestaFalsa(200, {"status": "identical", "behind_by": 0}),
        )
        estado = actualizaciones._comprobar("app", carpeta, "x/y", "main")
        assert estado.se_puede_actualizar
        assert not estado.hay_actualizacion
        assert "al día" in estado.resumen()

    def test_hay_actualizacion(self, tmp_path, monkeypatch):
        carpeta = _carpeta_git(tmp_path)
        monkeypatch.setattr(actualizaciones, "_sha_local", lambda c: "a" * 40)
        monkeypatch.setattr(
            actualizaciones.requests,
            "get",
            lambda *a, **k: RespuestaFalsa(200, {"status": "behind", "behind_by": 4}),
        )
        estado = actualizaciones._comprobar("app", carpeta, "x/y", "main")
        assert estado.hay_actualizacion
        assert estado.commits_por_detras == 4
        assert "4 cambios" in estado.resumen()

    def test_diverged_tambien_ofrece_actualizar(self, tmp_path, monkeypatch):
        carpeta = _carpeta_git(tmp_path)
        monkeypatch.setattr(actualizaciones, "_sha_local", lambda c: "a" * 40)
        monkeypatch.setattr(
            actualizaciones.requests,
            "get",
            lambda *a, **k: RespuestaFalsa(200, {"status": "diverged", "behind_by": 2}),
        )
        estado = actualizaciones._comprobar("app", carpeta, "x/y", "main")
        assert estado.hay_actualizacion

    def test_por_delante_no_es_actualizacion(self, tmp_path, monkeypatch):
        carpeta = _carpeta_git(tmp_path)
        monkeypatch.setattr(actualizaciones, "_sha_local", lambda c: "a" * 40)
        monkeypatch.setattr(
            actualizaciones.requests,
            "get",
            lambda *a, **k: RespuestaFalsa(200, {"status": "ahead", "behind_by": 0}),
        )
        estado = actualizaciones._comprobar("app", carpeta, "x/y", "main")
        assert not estado.hay_actualizacion

    def test_sin_leer_sha_local(self, tmp_path, monkeypatch):
        carpeta = _carpeta_git(tmp_path)
        monkeypatch.setattr(actualizaciones, "_sha_local", lambda c: None)
        estado = actualizaciones._comprobar("app", carpeta, "x/y", "main")
        assert "no se pudo leer" in estado.error

    def test_plan_b_cuando_compare_falla(self, tmp_path, monkeypatch):
        # compare devuelve 404, pero el endpoint de commits sí responde.
        carpeta = _carpeta_git(tmp_path)
        monkeypatch.setattr(actualizaciones, "_sha_local", lambda c: "a" * 40)

        def get(url, **k):
            if "/compare/" in url:
                return RespuestaFalsa(404)
            return RespuestaFalsa(200, {"sha": "b" * 40})  # distinto -> hay update

        monkeypatch.setattr(actualizaciones.requests, "get", get)
        estado = actualizaciones._comprobar("app", carpeta, "x/y", "main")
        assert estado.hay_actualizacion
        assert "aproximada" in estado.detalle

    def test_sin_internet(self, tmp_path, monkeypatch):
        carpeta = _carpeta_git(tmp_path)
        monkeypatch.setattr(actualizaciones, "_sha_local", lambda c: "a" * 40)

        def fallar(*a, **k):
            raise actualizaciones.requests.ConnectionError("sin red")

        monkeypatch.setattr(actualizaciones.requests, "get", fallar)
        estado = actualizaciones._comprobar("app", carpeta, "x/y", "main")
        assert "GitHub" in estado.error


class TestComprobarComponentes:
    def test_comprobar_app_usa_su_repo(self, monkeypatch):
        capturado = {}

        def falso(componente, carpeta, repo, rama):
            capturado["repo"] = repo
            return actualizaciones.EstadoActualizacion(componente=componente)

        monkeypatch.setattr(actualizaciones, "_comprobar", falso)
        actualizaciones.comprobar_app()
        assert capturado["repo"] == actualizaciones.REPO_APP

    def test_comprobar_mtkclient_localiza_la_carpeta(self, monkeypatch):
        from core import binarios

        monkeypatch.setattr(binarios, "buscar_mtkclient", lambda: "/home/x/mtkclient/mtk.py")
        capturado = {}

        def falso(componente, carpeta, repo, rama):
            capturado["carpeta"] = carpeta
            capturado["repo"] = repo
            return actualizaciones.EstadoActualizacion(componente=componente)

        monkeypatch.setattr(actualizaciones, "_comprobar", falso)
        actualizaciones.comprobar_mtkclient()
        assert capturado["carpeta"] == Path("/home/x/mtkclient")
        assert capturado["repo"] == actualizaciones.REPO_MTKCLIENT

    def test_comprobar_mtkclient_sin_mtkclient(self, monkeypatch):
        from core import binarios

        monkeypatch.setattr(binarios, "buscar_mtkclient", lambda: None)
        estado = actualizaciones.comprobar_mtkclient()
        assert "no encontrado" in estado.error

    def test_comprobar_todo_devuelve_los_dos(self, monkeypatch):
        monkeypatch.setattr(
            actualizaciones,
            "comprobar_app",
            lambda: actualizaciones.EstadoActualizacion(componente="app"),
        )
        monkeypatch.setattr(
            actualizaciones,
            "comprobar_mtkclient",
            lambda: actualizaciones.EstadoActualizacion(componente="mtkclient"),
        )
        estados = actualizaciones.comprobar_todo()
        assert [e.componente for e in estados] == ["app", "mtkclient"]


class TestActualizar:
    def test_hace_git_pull_ff_only(self, tmp_path, monkeypatch):
        from core import binarios

        capturado = {}
        monkeypatch.setattr(
            binarios,
            "ejecutar_en_vivo",
            lambda cmd, *a, **k: capturado.update(cmd=cmd) or binarios.ProcesoEnVivo(),
        )
        actualizaciones.actualizar(tmp_path, al_recibir_linea=lambda l: None)
        assert capturado["cmd"] == ["git", "-C", str(tmp_path), "pull", "--ff-only"]


def test_hay_version():
    assert actualizaciones.VERSION
    # Formato x.y.z
    partes = actualizaciones.VERSION.split(".")
    assert len(partes) == 3 and all(p.isdigit() for p in partes)
