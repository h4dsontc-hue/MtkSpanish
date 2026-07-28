"""Tests de la lógica que no depende de la interfaz.

    python3 -m pytest tests/ -q

Ninguno toca la red ni necesita un móvil conectado.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core import binarios, errores
from utils import validar


# ─────────────────────────── core/errores ───────────────────────────


class TestTraduccion:
    def test_falta_de_dispositivo(self):
        explicacion = errores.traducir("Error: No device detected, please reconnect")
        assert "No se detecta el móvil" in explicacion.titulo
        assert "VOLUMEN ABAJO" in explicacion.solucion

    def test_protecciones_del_fabricante(self):
        explicacion = errores.traducir("Target config: SBC is enabled, DAA is enabled")
        assert "protección del fabricante" in explicacion.titulo

    def test_particion_inexistente(self):
        explicacion = errores.traducir("Error: Couldn't detect partition: system")
        assert "no encaja con este móvil" in explicacion.titulo

    def test_bootloader_bloqueado(self):
        explicacion = errores.traducir("FAILED (remote: 'Flashing is not allowed')")
        assert "bootloader está bloqueado" in explicacion.titulo

    def test_lo_desconocido_no_revienta(self):
        assert errores.traducir("blah blah") is errores.DESCONOCIDO
        assert errores.traducir("") is errores.DESCONOCIDO

    def test_lo_concreto_gana_a_lo_generico(self):
        # Menciona "failed", que también casa con la regla genérica de escritura,
        # pero lo importante es que está sin autorizar.
        explicacion = errores.traducir("error: device unauthorized. failed")
        assert "no ha autorizado" in explicacion.titulo


class TestPorcentaje:
    @pytest.mark.parametrize(
        "linea,esperado",
        [
            ("Done |████------| 45.5% boot (0x12/0x40),2.10 MB/s", 45.5),
            ("Progress: 100 %", 100.0),
            ("Progress: 0.0%", 0.0),
            ("sin porcentaje aquí", None),
            ("valor imposible 250%", None),
        ],
    )
    def test_extraccion(self, linea, esperado):
        assert errores.extraer_porcentaje(linea) == esperado

    def test_coma_decimal(self):
        assert errores.extraer_porcentaje("Progreso 12,5 %") == 12.5


class TestResumenParaLog:
    def test_traduce_escritura(self):
        assert errores.resumir_para_log("Writing partition boot") == "Escribiendo la partición boot"

    def test_quita_el_prefijo_de_modulo(self):
        assert errores.resumir_para_log("Preloader - Device detected") == "Dispositivo detectado"

    def test_linea_vacia(self):
        assert errores.resumir_para_log("   ") is None

    def test_detecta_errores(self):
        assert errores.es_linea_de_error("Failed to write boot")
        assert not errores.es_linea_de_error("Escribiendo la partición boot")


# ─────────────────────────── core/binarios ───────────────────────────


class TestBinarios:
    def test_binario_inexistente_no_lanza(self):
        resultado = binarios.ejecutar(["no-existe-este-programa-12345"])
        assert resultado.ok is False
        assert "No se encuentra" in resultado.error

    def test_comando_correcto(self):
        resultado = binarios.ejecutar(["echo", "hola"])
        assert resultado.ok is True
        assert resultado.salida == "hola"

    def test_codigo_de_salida_distinto_de_cero(self):
        resultado = binarios.ejecutar(["sh", "-c", "exit 3"])
        assert resultado.ok is False
        assert resultado.codigo == 3

    def test_texto_junta_las_dos_salidas(self):
        resultado = binarios.ejecutar(["sh", "-c", "echo fuera; echo dentro >&2"])
        assert "fuera" in resultado.texto and "dentro" in resultado.texto

    def test_timeout(self):
        resultado = binarios.ejecutar(["sleep", "5"], timeout=1)
        assert resultado.ok is False
        assert "tardó demasiado" in resultado.error


class TestEjecucionEnVivo:
    def test_recibe_las_lineas_en_orden(self):
        lineas: list[str] = []
        terminado: list[int] = []
        proceso = binarios.ejecutar_en_vivo(
            ["sh", "-c", "echo uno; echo dos; echo tres"],
            lineas.append,
            terminado.append,
        )
        proceso.esperar(10)
        assert lineas == ["uno", "dos", "tres"]
        assert terminado == [0]

    def test_parte_tambien_por_retorno_de_carro(self):
        # Así es como MTKClient dibuja la barra de progreso.
        lineas: list[str] = []
        proceso = binarios.ejecutar_en_vivo(
            ["printf", "10%%\\r50%%\\r100%%\\n"], lineas.append
        )
        proceso.esperar(10)
        assert lineas == ["10%", "50%", "100%"]

    def test_cancelar_corta_el_proceso(self):
        lineas: list[str] = []
        codigos: list[int] = []
        proceso = binarios.ejecutar_en_vivo(
            ["sh", "-c", "echo empieza; sleep 30; echo nunca"],
            lineas.append,
            codigos.append,
        )
        # Espera activa mínima a que arranque antes de matarlo.
        for _ in range(100):
            if lineas:
                break
            import time

            time.sleep(0.05)
        proceso.cancelar()
        proceso.esperar(10)
        assert "nunca" not in lineas
        assert codigos == [-1]

    def test_binario_inexistente_avisa_por_el_callback(self):
        lineas: list[str] = []
        codigos: list[int] = []
        binarios.ejecutar_en_vivo(["no-existe-12345"], lineas.append, codigos.append)
        assert any("no se encuentra" in linea.lower() for linea in lineas)
        assert codigos == [127]


# ─────────────────────────── utils/validar ───────────────────────────


def crear_rom_fastboot(raiz: Path, codename: str = "lancelot") -> Path:
    carpeta = raiz / f"{codename}_global_images_V12.5.1.0.QJCMIXM_20210101.0000.00_11.0_global"
    imagenes = carpeta / "images"
    imagenes.mkdir(parents=True)
    for nombre in ("boot.img", "super.img", "vbmeta.img", "lk.img", "system.img"):
        (imagenes / nombre).write_bytes(b"\x00" * 1024)
    (imagenes / "android-info.txt").write_text(f"require board={codename}\n")
    (carpeta / "flash_all.sh").write_text("#!/bin/sh\n")
    (carpeta / "md5sum.txt").write_text("abc\n")
    return carpeta


class TestAnalisisDeFirmware:
    def test_rom_de_fastboot(self, tmp_path):
        carpeta = crear_rom_fastboot(tmp_path)
        firmware = validar.analizar(carpeta)
        assert firmware.tipo == validar.TIPO_FASTBOOT
        assert firmware.valido
        assert set(firmware.imagenes) == {"boot", "super", "vbmeta", "lk", "system"}
        assert firmware.codename == "lancelot"

    def test_ignora_lo_que_no_son_particiones(self, tmp_path):
        carpeta = crear_rom_fastboot(tmp_path)
        firmware = validar.analizar(carpeta)
        # Sin este filtro, `mtk wl` intentaría escribir estos archivos.
        assert "android-info" not in firmware.imagenes
        assert "flash_all" not in firmware.imagenes
        assert "md5sum" not in firmware.imagenes

    def test_rom_con_scatter(self, tmp_path):
        carpeta = tmp_path / "rom"
        carpeta.mkdir()
        (carpeta / "MT6768_Android_scatter.txt").write_text("- partition_index: SYS0\n")
        (carpeta / "boot.img").write_bytes(b"\x00" * 512)
        firmware = validar.analizar(carpeta)
        assert firmware.tipo == validar.TIPO_SCATTER
        assert firmware.scatter is not None

    def test_carpeta_vacia(self, tmp_path):
        firmware = validar.analizar(tmp_path)
        assert not firmware.valido
        assert any("no se ha encontrado" in p.lower() for p in firmware.problemas)

    def test_carpeta_inexistente(self, tmp_path):
        firmware = validar.analizar(tmp_path / "no-existe")
        assert not firmware.valido
        assert "no existe" in firmware.problemas[0]

    def test_un_zip_no_vale(self, tmp_path):
        zip_falso = tmp_path / "firmware.zip"
        zip_falso.write_bytes(b"PK")
        firmware = validar.analizar(zip_falso)
        assert not firmware.valido
        assert "ZIP" in firmware.problemas[0]

    def test_falta_boot_es_un_problema(self, tmp_path):
        carpeta = tmp_path / "rom"
        carpeta.mkdir()
        (carpeta / "system.img").write_bytes(b"\x00" * 512)
        firmware = validar.analizar(carpeta)
        assert not firmware.valido
        assert any("arranque" in p for p in firmware.problemas)

    def test_las_particiones_peligrosas_se_avisan_y_se_excluyen(self, tmp_path):
        carpeta = tmp_path / "rom"
        carpeta.mkdir()
        (carpeta / "boot.img").write_bytes(b"\x00" * 512)
        (carpeta / "nvram.img").write_bytes(b"\x00" * 512)
        (carpeta / "persist.img").write_bytes(b"\x00" * 512)
        firmware = validar.analizar(carpeta)
        assert "nvram" in firmware.imagenes
        assert "nvram" not in firmware.imagenes_seguras()
        assert "persist" not in firmware.imagenes_seguras()
        assert any("IMEI" in aviso for aviso in firmware.avisos)

    def test_los_preloader_se_normalizan(self, tmp_path):
        carpeta = tmp_path / "rom"
        carpeta.mkdir()
        (carpeta / "boot.img").write_bytes(b"\x00" * 512)
        (carpeta / "preloader_k62v1_64.bin").write_bytes(b"\x00" * 512)
        firmware = validar.analizar(carpeta)
        assert "preloader" in firmware.imagenes

    def test_las_imagenes_partidas_se_avisan(self, tmp_path):
        carpeta = tmp_path / "rom"
        carpeta.mkdir()
        (carpeta / "boot.img").write_bytes(b"\x00" * 512)
        (carpeta / "super.img.0").write_bytes(b"\x00" * 512)
        (carpeta / "super.img.1").write_bytes(b"\x00" * 512)
        firmware = validar.analizar(carpeta)
        assert "super" not in firmware.imagenes
        assert any("partidos" in aviso for aviso in firmware.avisos)


class TestCompatibilidad:
    def test_coinciden(self, tmp_path):
        firmware = validar.analizar(crear_rom_fastboot(tmp_path, "lancelot"))
        compatible, mensaje = validar.comprobar_compatibilidad(firmware, "lancelot")
        assert compatible
        assert "coincide" in mensaje

    def test_no_coinciden(self, tmp_path):
        firmware = validar.analizar(crear_rom_fastboot(tmp_path, "lancelot"))
        compatible, mensaje = validar.comprobar_compatibilidad(firmware, "merlin")
        assert not compatible
        assert "merlin" in mensaje and "lancelot" in mensaje

    def test_sin_codename_del_movil_no_se_bloquea(self, tmp_path):
        # Un móvil en BROM no puede decir su modelo: bloquearlo aquí impediría
        # justo el caso para el que existe la herramienta.
        firmware = validar.analizar(crear_rom_fastboot(tmp_path, "lancelot"))
        compatible, mensaje = validar.comprobar_compatibilidad(firmware, "")
        assert compatible
        assert "BROM" in mensaje

    def test_mayusculas_no_importan(self, tmp_path):
        firmware = validar.analizar(crear_rom_fastboot(tmp_path, "lancelot"))
        compatible, _ = validar.comprobar_compatibilidad(firmware, "LANCELOT")
        assert compatible


class TestDescompresion:
    def test_no_escapa_de_la_carpeta(self, tmp_path):
        import zipfile

        ruta_zip = tmp_path / "malicioso.zip"
        with zipfile.ZipFile(ruta_zip, "w") as archivo:
            archivo.writestr("bueno.img", "contenido")
            archivo.writestr("../fuera.txt", "no debería salir")

        destino = tmp_path / "salida"
        validar.descomprimir(ruta_zip, destino)
        assert (destino / "bueno.img").exists()
        assert not (tmp_path / "fuera.txt").exists()

    def test_informa_del_progreso(self, tmp_path):
        import zipfile

        ruta_zip = tmp_path / "firmware.zip"
        with zipfile.ZipFile(ruta_zip, "w") as archivo:
            for numero in range(4):
                archivo.writestr(f"parte{numero}.img", "x" * 1000)

        avances: list[float] = []
        validar.descomprimir(ruta_zip, tmp_path / "salida", al_progresar=avances.append)
        assert avances and avances[-1] == pytest.approx(100.0)
        assert avances == sorted(avances)


class TestFormatoDeTamano:
    @pytest.mark.parametrize(
        "bytes_,esperado",
        [(0, "0 B"), (1023, "1023 B"), (1024, "1 KB"), (1536, "1.5 KB"),
         (1024 ** 3, "1 GB")],
    )
    def test_formatos(self, bytes_, esperado):
        assert validar.formatear_tamano(bytes_) == esperado


# ─────────────────────────── core/mtk ───────────────────────────


class TestPreparacionDeCarpeta:
    def test_renombra_a_nombre_de_particion(self, tmp_path):
        from core import mtk

        origen = tmp_path / "origen"
        origen.mkdir()
        (origen / "boot.img").write_bytes(b"BOOT")
        (origen / "super.img").write_bytes(b"SUPER")

        destino = mtk.preparar_carpeta_de_flasheo(
            {"boot": origen / "boot.img", "super": origen / "super.img"},
            tmp_path / "listo",
        )
        assert sorted(p.name for p in destino.iterdir()) == ["boot.bin", "super.bin"]
        assert (destino / "boot.bin").read_bytes() == b"BOOT"

    def test_no_duplica_el_contenido(self, tmp_path):
        from core import mtk

        origen = tmp_path / "boot.img"
        origen.write_bytes(b"\x00" * 4096)
        destino = mtk.preparar_carpeta_de_flasheo({"boot": origen}, tmp_path / "listo")
        # Un enlace duro, no una copia: los firmwares pesan gigas.
        assert os.stat(destino / "boot.bin").st_ino == os.stat(origen).st_ino

    def test_se_puede_repetir(self, tmp_path):
        from core import mtk

        origen = tmp_path / "boot.img"
        origen.write_bytes(b"A")
        carpeta = tmp_path / "listo"
        mtk.preparar_carpeta_de_flasheo({"boot": origen}, carpeta)
        mtk.preparar_carpeta_de_flasheo({"boot": origen}, carpeta)
        assert (carpeta / "boot.bin").read_bytes() == b"A"


class TestFiltradoDeProgreso:
    """La barra debe moverse sin inundar el registro."""

    def _envolver(self):
        from core import mtk

        seguimiento = mtk.SeguimientoFlash()
        registradas: list[str] = []
        avances: list[float] = []
        manejar = mtk._envolver_callbacks(seguimiento, registradas.append, avances.append)
        return manejar, registradas, avances, seguimiento

    def test_la_barra_mueve_pero_no_se_registra(self):
        manejar, registradas, avances, _ = self._envolver()
        manejar("Done |█████-----| 50.0% boot (0x2/0x4),2.10 MB/s")
        assert avances == [50.0]
        assert registradas == []

    def test_un_mensaje_con_porcentaje_sí_se_registra(self):
        manejar, registradas, avances, _ = self._envolver()
        manejar("Erasing userdata, 100% done")
        assert avances == [100.0]
        assert registradas  # este sí es información para el usuario

    def test_se_recuerda_la_particion_en_curso(self):
        manejar, _, _, seguimiento = self._envolver()
        manejar("Writing partition system")
        assert seguimiento.particion_actual == "system"

    def test_las_lineas_normales_llegan_traducidas(self):
        manejar, registradas, _, _ = self._envolver()
        manejar("Wrote boot.bin to sector 1024 with sector count 8.")
        assert registradas == ["Escrita la partición boot.bin"]

    def test_todo_lo_crudo_queda_guardado(self):
        # Aunque no se enseñe, hace falta para traducir el error al final.
        manejar, _, _, seguimiento = self._envolver()
        manejar("Done |███-------| 30.0% boot")
        assert seguimiento.lineas == ["Done |███-------| 30.0% boot"]


class TestConfiguracionObjetivo:
    def test_sin_protecciones(self):
        from core.mtk import ConfiguracionObjetivo

        config = ConfiguracionObjetivo(sbc=False, daa=False, sla=False)
        assert not config.protegido
        assert "sin problemas" in config.explicacion()

    def test_con_protecciones(self):
        from core.mtk import ConfiguracionObjetivo

        config = ConfiguracionObjetivo(sbc=True, daa=False, sla=None)
        assert config.protegido
        assert "SBC" in config.explicacion()


# ─────────────────────────── core/detector ───────────────────────────


class TestDetector:
    def test_reconoce_el_pid_de_brom(self, monkeypatch):
        from core import detector

        monkeypatch.setattr(detector, "dispositivos_mediatek", lambda: [("0003", "/sys/x")])
        assert detector.detectar_modo() == detector.MODO_BROM

    def test_reconoce_el_pid_de_preloader(self, monkeypatch):
        from core import detector

        monkeypatch.setattr(detector, "dispositivos_mediatek", lambda: [("2000", "/sys/x")])
        assert detector.detectar_modo() == detector.MODO_PRELOADER

    def test_brom_gana_a_fastboot(self, monkeypatch):
        # Un adb o fastboot fantasma de otra sesión no debe tapar el BROM real.
        from core import detector

        monkeypatch.setattr(detector, "dispositivos_mediatek", lambda: [("0003", "")])
        monkeypatch.setattr(detector, "_dispositivos_fastboot", lambda: ["abc"])
        assert detector.detectar_modo() == detector.MODO_BROM

    def test_mediatek_desconocido_sigue_siendo_rescatable(self, monkeypatch):
        from core import detector

        monkeypatch.setattr(detector, "dispositivos_mediatek", lambda: [("ffff", "")])
        monkeypatch.setattr(detector, "_dispositivos_fastboot", lambda: [])
        monkeypatch.setattr(detector, "_dispositivos_adb", lambda: [])
        assert detector.detectar_modo() == detector.MODO_BROM

    def test_sin_nada_conectado(self, monkeypatch):
        from core import detector

        monkeypatch.setattr(detector, "dispositivos_mediatek", lambda: [])
        monkeypatch.setattr(detector, "_dispositivos_fastboot", lambda: [])
        monkeypatch.setattr(detector, "_dispositivos_adb", lambda: [])
        assert detector.detectar_modo() is None

    def test_dispositivo_en_brom_es_flasheable(self):
        from core.detector import MODO_BROM, Dispositivo

        assert Dispositivo(modo=MODO_BROM).se_puede_flashear


class TestParseoAdb:
    def test_getprop_completo(self, monkeypatch):
        from core import adb, binarios

        salida = (
            "[ro.product.model]: [Redmi 9]\n"
            "[ro.product.device]: [lancelot]\n"
            "[ro.build.version.release]: [11]\n"
            "[ro.board.platform]: [mt6768]\n"
        )
        monkeypatch.setattr(
            binarios, "ejecutar", lambda *a, **k: binarios.Resultado(True, salida)
        )
        dispositivo = adb.describir_dispositivo()
        assert dispositivo.modelo == "Redmi 9"
        assert dispositivo.codename == "lancelot"
        assert dispositivo.chipset == "mt6768"

    def test_adb_que_falla_no_revienta(self, monkeypatch):
        from core import adb, binarios

        monkeypatch.setattr(
            binarios, "ejecutar", lambda *a, **k: binarios.Resultado(False, error="x")
        )
        assert adb.describir_dispositivo().modelo == "desconocido"


class TestParseoFastboot:
    def test_getvar_lee_de_stderr(self, monkeypatch):
        from core import binarios, fastboot

        # fastboot escribe getvar en stderr: si solo se mirase stdout, esto
        # devolvería vacío y el móvil aparecería como «desconocido».
        monkeypatch.setattr(
            binarios,
            "ejecutar",
            lambda cmd, **k: binarios.Resultado(
                True, "", f"{cmd[2]}: valor-de-{cmd[2]}\nFinished."
            ),
        )
        assert fastboot._getvar("product") == "valor-de-product"

    def test_estado_del_bootloader(self, monkeypatch):
        from core import fastboot

        monkeypatch.setattr(fastboot, "_getvar", lambda nombre: "yes")
        assert fastboot.bootloader_desbloqueado() is True
        monkeypatch.setattr(fastboot, "_getvar", lambda nombre: "no")
        assert fastboot.bootloader_desbloqueado() is False
        monkeypatch.setattr(fastboot, "_getvar", lambda nombre: "")
        assert fastboot.bootloader_desbloqueado() is None


class TestLoteFastboot:
    def test_se_salta_las_particiones_criticas(self, tmp_path, monkeypatch):
        from core import binarios, fastboot

        escritas: list[str] = []
        monkeypatch.setattr(
            fastboot,
            "flashear_particion",
            lambda particion, ruta: escritas.append(particion) or binarios.Resultado(True),
        )

        imagen = tmp_path / "x.img"
        imagen.write_bytes(b"\x00")
        lineas: list[str] = []
        codigos: list[int] = []
        proceso = fastboot.flashear_lote(
            [("boot", imagen), ("nvram", imagen), ("system", imagen)],
            lineas.append,
            codigos.append,
        )
        proceso.esperar(10)
        assert escritas == ["boot", "system"]
        assert codigos == [0]
        assert any("nvram" in linea and "salta" in linea for linea in lineas)


# ─────────────────────────── scraper/mifirm ───────────────────────────


HTML_LISTADO = """
<html><body>
  <h3>Redmi 9 Fastboot Stable Global</h3>
  <table>
    <thead><tr><th>MIUI version</th><th>Android version</th><th>File size</th>
      <th>Update at</th><th>Downloaded</th><th>Download</th></tr></thead>
    <tbody>
      <tr><td>V12.5.1.0.QJCMIXM</td><td>11.0</td><td>3.9 GB</td>
          <td>2021-05-01 10:00:00</td><td>1234</td>
          <td><a href=" https://mifirm.net/download/9999">Download</a></td></tr>
    </tbody>
  </table>
  <h3>Redmi 9 ZIP Developer China</h3>
  <table>
    <thead><tr><th>MIUI version</th><th>Android version</th><th>File size</th>
      <th>Update at</th><th>Downloaded</th><th>Download</th></tr></thead>
    <tbody>
      <tr><td>V12.0.1.0.RJCCNXM</td><td>10.0</td><td>2.1 GB</td>
          <td>2021-01-01 10:00:00</td><td>42</td>
          <td><a href="/downloadzip/8888">Download</a></td></tr>
    </tbody>
  </table>
</body></html>
"""


class RespuestaFalsa:
    def __init__(self, texto="", codigo=200):
        self.text = texto
        self.status_code = codigo

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"{self.status_code}")


class TestScraper:
    def test_parseo_del_listado(self, monkeypatch):
        from scraper import mifirm

        monkeypatch.setattr(
            mifirm.requests, "get", lambda *a, **k: RespuestaFalsa(HTML_LISTADO)
        )
        resultados = mifirm.buscar_firmwares("lancelot")
        assert len(resultados) == 2

        fastboot_rom = resultados[0]
        assert fastboot_rom.tipo == mifirm.TIPO_FASTBOOT
        assert fastboot_rom.version == "V12.5.1.0.QJCMIXM"
        assert fastboot_rom.android == "11.0"
        assert fastboot_rom.region == "Global"
        assert fastboot_rom.canal == "Estable"
        # El href real viene con un espacio delante.
        assert fastboot_rom.url == "https://mifirm.net/download/9999"

        zip_rom = resultados[1]
        assert zip_rom.tipo == mifirm.TIPO_ZIP
        assert zip_rom.canal == "Beta"
        assert zip_rom.region == "China"
        assert zip_rom.url == "https://mifirm.net/downloadzip/8888"

    def test_filtro_de_utiles_descarta_los_zip(self, monkeypatch):
        from scraper import mifirm

        monkeypatch.setattr(
            mifirm.requests, "get", lambda *a, **k: RespuestaFalsa(HTML_LISTADO)
        )
        resultados = mifirm.buscar_firmwares("lancelot", solo_utiles=True)
        assert [f.tipo for f in resultados] == [mifirm.TIPO_FASTBOOT]

    def test_404_explica_el_problema(self, monkeypatch):
        from scraper import mifirm

        monkeypatch.setattr(
            mifirm.requests, "get", lambda *a, **k: RespuestaFalsa("", 404)
        )
        with pytest.raises(mifirm.ErrorDeRed, match="no tiene ninguna página"):
            mifirm.buscar_firmwares("noexiste")

    def test_sin_conexion(self, monkeypatch):
        import requests

        from scraper import mifirm

        def fallar(*a, **k):
            raise requests.ConnectionError("sin red")

        monkeypatch.setattr(mifirm.requests, "get", fallar)
        with pytest.raises(mifirm.ErrorDeRed, match="conexión a internet"):
            mifirm.buscar_firmwares("lancelot")

    def test_codename_vacio(self):
        from scraper import mifirm

        assert mifirm.buscar_firmwares("") == []

    def test_los_zip_no_sirven_si_el_movil_no_arranca(self):
        from scraper import mifirm

        assert not mifirm.FirmwareRemoto(tipo=mifirm.TIPO_ZIP).recomendado_para_brom
        assert mifirm.FirmwareRemoto(tipo=mifirm.TIPO_FASTBOOT).recomendado_para_brom


# ─────────────────────────── utils/sistema ───────────────────────────


class TestSistema:
    def test_el_script_no_se_corta_con_las_reglas(self):
        from utils import sistema

        script = sistema._script_de_preparacion()
        # Las reglas van dentro de un heredoc: si el delimitador apareciese en
        # las reglas, el script se rompería a mitad.
        assert "FIN_DE_REGLAS" not in sistema.REGLAS_UDEV
        assert script.count("FIN_DE_REGLAS") == 2
        assert "0e8d" in script

    def test_el_script_incluye_todos_los_pasos(self):
        from utils import sistema

        script = sistema._script_de_preparacion()
        for paso in sistema.PASOS:
            assert f"PASO:{paso}" in script

    def test_revisar_entorno_devuelve_tuplas_completas(self):
        from utils import sistema

        for revision in sistema.revisar_entorno():
            descripcion, correcto, consejo = revision
            assert isinstance(descripcion, str) and descripcion
            assert isinstance(correcto, bool)
            assert isinstance(consejo, str)
