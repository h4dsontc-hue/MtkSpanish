"""Tests del historial de rescates."""

from __future__ import annotations

from core import historial
from core.historial import Entrada


class TestRegistrarYLeer:
    def test_ida_y_vuelta(self, tmp_path):
        ruta = tmp_path / "historial.json"
        historial.registrar(
            Entrada.ahora(modelo="Redmi 9", codename="lancelot", resultado="correcto"),
            ruta,
        )
        entradas = historial.entradas(ruta)
        assert len(entradas) == 1
        assert entradas[0].modelo == "Redmi 9"
        assert entradas[0].fecha  # se rellena sola

    def test_las_mas_recientes_primero(self, tmp_path):
        ruta = tmp_path / "historial.json"
        historial.registrar(Entrada(modelo="uno", fecha="2020-01-01"), ruta)
        historial.registrar(Entrada(modelo="dos", fecha="2020-01-02"), ruta)
        modelos = [e.modelo for e in historial.entradas(ruta)]
        assert modelos == ["dos", "uno"]

    def test_crea_la_carpeta_si_no_existe(self, tmp_path):
        ruta = tmp_path / "sub" / "carpeta" / "historial.json"
        assert historial.registrar(Entrada(modelo="x"), ruta) is True
        assert ruta.is_file()

    def test_se_recorta_al_maximo(self, tmp_path, monkeypatch):
        monkeypatch.setattr(historial, "MAXIMO", 3)
        ruta = tmp_path / "historial.json"
        for i in range(6):
            historial.registrar(Entrada(modelo=str(i)), ruta)
        entradas = historial.entradas(ruta)
        assert len(entradas) == 3
        # Se conservan las últimas.
        assert [e.modelo for e in entradas] == ["5", "4", "3"]


class TestRobustez:
    def test_archivo_inexistente_da_lista_vacia(self, tmp_path):
        assert historial.entradas(tmp_path / "no-existe.json") == []

    def test_json_corrupto_no_revienta(self, tmp_path):
        ruta = tmp_path / "historial.json"
        ruta.write_text("esto no es JSON {{{")
        assert historial.entradas(ruta) == []
        # Y se puede volver a registrar encima sin problema.
        assert historial.registrar(Entrada(modelo="nuevo"), ruta) is True
        assert [e.modelo for e in historial.entradas(ruta)] == ["nuevo"]

    def test_json_que_no_es_lista(self, tmp_path):
        ruta = tmp_path / "historial.json"
        ruta.write_text('{"clave": "valor"}')
        assert historial.entradas(ruta) == []

    def test_campos_desconocidos_se_ignoran(self, tmp_path):
        ruta = tmp_path / "historial.json"
        ruta.write_text('[{"modelo": "X", "campo_raro": 123}]')
        entradas = historial.entradas(ruta)
        assert entradas[0].modelo == "X"

    def test_registrar_en_ruta_imposible_devuelve_false(self, tmp_path):
        # Un archivo donde debería ir una carpeta: mkdir fallará.
        obstaculo = tmp_path / "obstaculo"
        obstaculo.write_text("soy un archivo")
        ruta = obstaculo / "historial.json"
        assert historial.registrar(Entrada(modelo="x"), ruta) is False


class TestFormato:
    def test_linea_con_icono(self):
        entrada = Entrada(
            fecha="2026-07-28 10:00:00", modelo="Redmi 9", firmware="V12.5",
            resultado=historial.RESULTADO_OK,
        )
        texto = entrada.linea()
        assert "Redmi 9" in texto and "V12.5" in texto and "correcto" in texto

    def test_texto_completo_vacio(self, tmp_path):
        assert "Todavía no hay" in historial.texto_completo(tmp_path / "no.json")

    def test_ruta_respeta_xdg(self, monkeypatch, tmp_path):
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        assert historial.ruta_historial() == tmp_path / "rescatemtk" / "historial.json"
