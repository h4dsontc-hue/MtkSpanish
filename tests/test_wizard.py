"""Tests del wizard con customtkinter sustituido por dobles.

No comprueban que la ventana se vea bien —eso hay que mirarlo con los ojos—
sino que el código de la interfaz no se rompa: que todos los pasos se
construyan, que se pueda navegar entre ellos, que los callbacks encuentren los
widgets que esperan y que nada toque Tk desde un hilo que no sea el suyo.
"""

from __future__ import annotations

import sys

import pytest

from tests import dobles_ui

DIALOGOS = dobles_ui.instalar()

# Se importan después de instalar los dobles: al importarse, estos módulos
# hacen `import customtkinter`.
from core.detector import MODO_ADB, MODO_BROM, MODO_FASTBOOT, Dispositivo  # noqa: E402
from ui.wizard import Wizard  # noqa: E402
from utils import validar  # noqa: E402


@pytest.fixture
def wizard(monkeypatch):
    # El paso 1 lanza una detección nada más entrar; en los tests se anula
    # para que no salga a tocar el USB de verdad.
    from core import detector

    monkeypatch.setattr(detector, "detectar", lambda: None)
    monkeypatch.setattr(detector, "detectar_modo", lambda: None)

    ventana = Wizard()
    ventana.vaciar = ventana._vaciar_cola
    yield ventana


@pytest.fixture(autouse=True)
def dialogos_limpios():
    DIALOGOS.llamadas.clear()
    DIALOGOS.respuesta_si_no = True
    DIALOGOS.ruta_a_devolver = ""
    yield


def rom_de_prueba(tmp_path, codename="lancelot"):
    carpeta = tmp_path / f"{codename}_global_images_V12.5.1.0"
    (carpeta / "images").mkdir(parents=True, exist_ok=True)
    for nombre in ("boot.img", "super.img", "vbmeta.img", "lk.img", "system.img"):
        (carpeta / "images" / nombre).write_bytes(b"\x00" * 2048)
    (carpeta / "images" / "android-info.txt").write_text(f"require board={codename}\n")
    return carpeta


class TestConstruccion:
    def test_se_crean_los_cinco_pasos(self, wizard):
        assert len(wizard.pasos) == 5
        assert len(wizard.etiquetas_pasos) == 5

    def test_empieza_en_el_primero(self, wizard):
        assert wizard.indice == 0
        assert wizard.pasos[0].empaquetado
        assert not wizard.pasos[1].empaquetado

    def test_atras_deshabilitado_al_principio(self, wizard):
        assert wizard.boton_atras.cget("state") == "disabled"


class TestNavegacion:
    def test_avanzar_y_retroceder(self, wizard):
        wizard.mostrar_paso(1)
        assert wizard.indice == 1
        assert wizard.pasos[1].empaquetado
        assert not wizard.pasos[0].empaquetado

        wizard.atras()
        assert wizard.indice == 0

    def test_no_se_sale_por_los_extremos(self, wizard):
        wizard.mostrar_paso(-5)
        assert wizard.indice == 0
        wizard.mostrar_paso(99)
        assert wizard.indice == 4

    def test_el_ultimo_paso_dice_cerrar(self, wizard):
        wizard.mostrar_paso(4)
        assert wizard.boton_siguiente.cget("text") == "Cerrar"

    def test_al_salir_puede_bloquear_el_avance(self, wizard):
        # El paso 1 no deja pasar si no hay dispositivo detectado.
        wizard.mostrar_paso(1)
        wizard.estado.dispositivo = None
        wizard.siguiente()
        assert wizard.indice == 1

    def test_cada_paso_se_construye_una_sola_vez(self, wizard):
        paso = wizard.pasos[1]
        wizard.mostrar_paso(1)
        wizard.mostrar_paso(0)
        wizard.mostrar_paso(1)
        assert wizard.pasos[1] is paso


class TestColaDeHilos:
    def test_las_tareas_se_ejecutan_al_vaciar(self, wizard):
        recibido = []
        wizard.en_ui(recibido.append, "hola")
        assert recibido == []  # todavía no
        wizard._vaciar_cola()
        assert recibido == ["hola"]

    def test_una_tarea_que_falla_no_para_las_demas(self, wizard):
        recibido = []

        def explotar():
            raise RuntimeError("fallo al pintar")

        wizard.en_ui(explotar)
        wizard.en_ui(recibido.append, "sigo vivo")
        wizard._vaciar_cola()
        assert recibido == ["sigo vivo"]

    def test_el_trabajo_en_segundo_plano_devuelve_el_resultado(self, wizard):
        import time

        recibido = []
        wizard.en_segundo_plano(lambda: 21 * 2, recibido.append)
        for _ in range(100):
            wizard._vaciar_cola()
            if recibido:
                break
            time.sleep(0.02)
        assert recibido == [42]

    def test_las_excepciones_llegan_al_callback(self, wizard):
        import time

        recibido = []

        def explotar():
            raise ValueError("algo pasó")

        wizard.en_segundo_plano(explotar, recibido.append)
        for _ in range(100):
            wizard._vaciar_cola()
            if recibido:
                break
            time.sleep(0.02)
        assert isinstance(recibido[0], ValueError)


class TestPasoBienvenida:
    def test_pinta_las_revisiones(self, wizard):
        paso = wizard.pasos[0]
        paso.al_entrar()
        assert len(paso.lineas) >= 4

    def test_sin_mtkclient_no_deja_avanzar(self, wizard, monkeypatch):
        from utils import sistema

        monkeypatch.setattr(
            sistema,
            "revisar_entorno",
            lambda: [
                ("Reglas de permisos USB instaladas", True, ""),
                ("MTKClient encontrado", False, "clónalo"),
            ],
        )
        wizard.pasos[0].al_entrar()
        assert wizard.boton_siguiente.cget("state") == "disabled"

    def test_con_mtkclient_deja_avanzar(self, wizard, monkeypatch):
        from utils import sistema

        monkeypatch.setattr(
            sistema,
            "revisar_entorno",
            lambda: [("MTKClient encontrado", True, "")],
        )
        monkeypatch.setattr(sistema, "sistema_ya_preparado", lambda: True)
        wizard.pasos[0].al_entrar()
        assert wizard.boton_siguiente.cget("state") == "normal"

    def test_pinta_el_resultado_de_actualizaciones(self, wizard):
        from core import actualizaciones as act

        paso = wizard.pasos[0]
        estados = [
            act.EstadoActualizacion(
                componente="app", hay_actualizacion=True, se_puede_actualizar=True,
                commits_por_detras=3, ruta=None,
            ),
            act.EstadoActualizacion(componente="mtkclient", error="al día."),
        ]
        paso._pintar_actualizaciones(estados)
        # Una fila por componente.
        assert len(paso.filas_actualizacion) == 2

    def test_un_fallo_de_red_no_rompe_la_bienvenida(self, wizard):
        paso = wizard.pasos[0]
        paso._pintar_actualizaciones(RuntimeError("sin internet"))
        assert len(paso.filas_actualizacion) == 1


class TestPasoDetectar:
    def test_sin_dispositivo_no_deja_avanzar(self, wizard):
        paso = wizard.pasos[1]
        paso._al_detectar(None)
        assert wizard.boton_siguiente.cget("state") == "disabled"
        assert "No se detecta" in paso.etiqueta_resultado.cget("text")

    def test_con_dispositivo_en_brom(self, wizard, monkeypatch):
        from core import mtk

        monkeypatch.setattr(mtk, "disponible", lambda: True)
        paso = wizard.pasos[1]
        paso._al_detectar(Dispositivo(modo=MODO_BROM, modelo="Redmi 9"))

        assert wizard.estado.dispositivo is not None
        assert wizard.boton_siguiente.cget("state") == "normal"
        # En BROM sí se ofrece consultar las protecciones.
        assert paso.boton_protecciones.empaquetado

    def test_en_fastboot_no_se_pregunta_por_protecciones(self, wizard):
        paso = wizard.pasos[1]
        paso.boton_protecciones.pack()
        paso._al_detectar(Dispositivo(modo=MODO_FASTBOOT, modelo="Redmi 9"))
        assert not paso.boton_protecciones.empaquetado

    def test_un_error_al_detectar_se_enseña(self, wizard):
        paso = wizard.pasos[1]
        paso._al_detectar(RuntimeError("USB roto"))
        assert "Error" in paso.etiqueta_resultado.cget("text")
        assert wizard.boton_siguiente.cget("state") == "disabled"

    def test_las_protecciones_se_guardan(self, wizard):
        from core.mtk import ConfiguracionObjetivo

        paso = wizard.pasos[1]
        paso._al_leer_protecciones(ConfiguracionObjetivo(sbc=True, daa=False))
        assert wizard.estado.configuracion_objetivo.sbc is True
        assert "SBC" in paso.etiqueta_protecciones.cget("text")


class TestPasoFirmware:
    def test_una_rom_valida_deja_avanzar(self, wizard, tmp_path):
        wizard.estado.dispositivo = Dispositivo(modo=MODO_BROM, codename="lancelot")
        paso = wizard.pasos[2]
        paso._al_analizar(validar.analizar(rom_de_prueba(tmp_path, "lancelot")))

        assert wizard.estado.firmware is not None
        assert wizard.boton_siguiente.cget("state") == "normal"

    def test_una_rom_de_otro_modelo_se_rechaza(self, wizard, tmp_path):
        wizard.estado.dispositivo = Dispositivo(modo=MODO_BROM, codename="merlin")
        paso = wizard.pasos[2]
        paso._al_analizar(validar.analizar(rom_de_prueba(tmp_path, "lancelot")))

        assert wizard.estado.firmware is None
        assert wizard.boton_siguiente.cget("state") == "disabled"
        assert any(llamada[0] == "showerror" for llamada in DIALOGOS.llamadas)

    def test_una_carpeta_vacia_se_rechaza(self, wizard, tmp_path):
        wizard.pasos[2]._al_analizar(validar.analizar(tmp_path))
        assert wizard.estado.firmware is None
        assert wizard.boton_siguiente.cget("state") == "disabled"

    def test_sin_firmware_no_se_puede_salir(self, wizard):
        wizard.estado.firmware = None
        assert wizard.pasos[2].al_salir() is False
        assert any(llamada[0] == "showinfo" for llamada in DIALOGOS.llamadas)

    def test_el_codename_se_rellena_solo(self, wizard):
        wizard.estado.dispositivo = Dispositivo(modo=MODO_ADB, codename="lancelot")
        paso = wizard.pasos[2]
        paso.al_entrar()
        assert paso.entrada_codename.get() == "lancelot"

    def test_pinta_los_resultados_de_la_busqueda(self, wizard):
        from scraper import mifirm

        paso = wizard.pasos[2]
        paso._al_buscar(
            [
                mifirm.FirmwareRemoto(version="V12.5", tipo=mifirm.TIPO_FASTBOOT),
                mifirm.FirmwareRemoto(version="V12.0", tipo=mifirm.TIPO_FASTBOOT),
            ]
        )
        assert len(paso.filas_resultados) == 2

    def test_un_error_de_red_se_enseña_sin_romper(self, wizard):
        from scraper import mifirm

        paso = wizard.pasos[2]
        paso._al_buscar(mifirm.ErrorDeRed("sin internet"))
        assert "sin internet" in paso.etiqueta_busqueda.cget("text")

    def test_una_busqueda_vacia_avisa(self, wizard):
        paso = wizard.pasos[2]
        paso._al_buscar([])
        assert "No se ha encontrado" in paso.etiqueta_busqueda.cget("text")


class TestPasoFlash:
    def _preparar(self, wizard, tmp_path, modo=MODO_BROM, codename="lancelot"):
        wizard.estado.dispositivo = Dispositivo(modo=modo, codename=codename)
        wizard.estado.firmware = validar.analizar(rom_de_prueba(tmp_path, codename))
        paso = wizard.pasos[3]
        paso.al_entrar()
        return paso

    def test_el_resumen_lista_las_particiones(self, wizard, tmp_path):
        paso = self._preparar(wizard, tmp_path)
        resumen = paso.etiqueta_resumen.cget("text")
        assert "boot" in resumen and "super" in resumen
        assert "MTKClient" in resumen

    def test_backup_activado_por_defecto_en_brom(self, wizard, tmp_path):
        paso = self._preparar(wizard, tmp_path, MODO_BROM)
        assert paso.variable_backup.get() is True
        assert paso.check_backup.cget("state") == "normal"

    def test_backup_no_disponible_en_fastboot(self, wizard, tmp_path):
        paso = self._preparar(wizard, tmp_path, MODO_FASTBOOT)
        assert paso.variable_backup.get() is False
        assert paso.check_backup.cget("state") == "disabled"

    def test_con_backup_respalda_antes_de_flashear(self, wizard, tmp_path, monkeypatch):
        import time

        from core import herramientas

        orden = []
        monkeypatch.setattr(herramientas, "particiones_a_respaldar", lambda: ["nvram"])

        def respaldar_falso(destino, particiones, al_terminar=None, **k):
            orden.append("backup")
            # Simula que la copia termina bien.
            if al_terminar:
                al_terminar(0)
            from core import mtk

            return mtk.SeguimientoFlash()

        monkeypatch.setattr(herramientas, "respaldar", respaldar_falso)
        monkeypatch.setattr(
            wizard.pasos[3], "_flashear_por_brom",
            lambda: orden.append("flash"),
        )

        DIALOGOS.respuesta_si_no = True
        paso = self._preparar(wizard, tmp_path, MODO_BROM)
        paso.variable_backup.set(True)
        paso._empezar()

        for _ in range(200):
            wizard._vaciar_cola()
            if "flash" in orden:
                break
            time.sleep(0.01)

        # El backup ocurre antes que el flasheo.
        assert orden == ["backup", "flash"]

    def test_sin_backup_va_directo_al_flasheo(self, wizard, tmp_path, monkeypatch):
        orden = []
        monkeypatch.setattr(
            wizard.pasos[3], "_flashear_por_brom", lambda: orden.append("flash")
        )
        DIALOGOS.respuesta_si_no = True
        paso = self._preparar(wizard, tmp_path, MODO_BROM)
        paso.variable_backup.set(False)
        paso._empezar()
        assert orden == ["flash"]

    def test_si_el_backup_falla_pregunta_antes_de_seguir(self, wizard, tmp_path, monkeypatch):
        from core import herramientas

        orden = []
        monkeypatch.setattr(
            herramientas, "particiones_a_respaldar", lambda: []  # nada que respaldar
        )
        monkeypatch.setattr(
            wizard.pasos[3], "_flashear_por_brom", lambda: orden.append("flash")
        )
        # El usuario dice «no, no sigas sin copia».
        DIALOGOS.respuesta_si_no = False

        paso = self._preparar(wizard, tmp_path, MODO_BROM)
        paso.variable_backup.set(True)
        paso.operacion_en_curso = True
        paso._preguntar_seguir_sin_copia()

        assert orden == []  # no se flasheó
        assert wizard.estado.flash_cancelado is True

    def test_el_resumen_avisa_de_las_particiones_saltadas(self, wizard, tmp_path):
        carpeta = rom_de_prueba(tmp_path, "lancelot")
        (carpeta / "images" / "nvram.img").write_bytes(b"\x00" * 512)
        wizard.estado.dispositivo = Dispositivo(modo=MODO_BROM, codename="lancelot")
        wizard.estado.firmware = validar.analizar(carpeta)
        paso = wizard.pasos[3]
        paso.al_entrar()
        assert "Se saltan" in paso.etiqueta_resumen.cget("text")
        assert "nvram" in paso.etiqueta_resumen.cget("text")

    def test_no_se_puede_avanzar_antes_de_flashear(self, wizard, tmp_path):
        self._preparar(wizard, tmp_path)
        assert wizard.boton_siguiente.cget("state") == "disabled"

    def test_el_metodo_depende_del_modo(self, wizard, tmp_path):
        assert "MTKClient" in self._preparar(wizard, tmp_path, MODO_BROM)._nombre_metodo()
        assert "fastboot" in self._preparar(wizard, tmp_path, MODO_FASTBOOT)._nombre_metodo()
        assert "fastboot" in self._preparar(wizard, tmp_path, MODO_ADB)._nombre_metodo()

    def test_si_se_dice_que_no_no_se_flashea(self, wizard, tmp_path):
        paso = self._preparar(wizard, tmp_path)
        DIALOGOS.respuesta_si_no = False
        paso._empezar()
        assert paso.operacion_en_curso is False

    def test_un_final_correcto_desbloquea_el_avance(self, wizard, tmp_path):
        paso = self._preparar(wizard, tmp_path)
        paso.operacion_en_curso = True
        paso._al_terminar(0)
        assert wizard.estado.flash_correcto is True
        assert wizard.boton_siguiente.cget("state") == "normal"

    def test_una_linea_de_error_marca_el_flasheo_como_fallido(self, wizard, tmp_path):
        paso = self._preparar(wizard, tmp_path)
        paso.operacion_en_curso = True
        paso._escribir("Failed to write boot to sector 0")
        paso._al_terminar(0)  # mtkclient sale con 0 aunque haya fallado
        assert wizard.estado.flash_correcto is False
        assert wizard.estado.mensaje_error

    def test_la_cancelacion_se_registra(self, wizard, tmp_path):
        paso = self._preparar(wizard, tmp_path)
        paso.operacion_en_curso = True
        paso._al_terminar(-1)
        assert wizard.estado.flash_cancelado is True
        assert wizard.estado.flash_correcto is False

    def test_la_barra_sigue_el_progreso(self, wizard, tmp_path):
        paso = self._preparar(wizard, tmp_path)
        paso._progreso(45.0)
        assert paso.barra.cget("_valor") == pytest.approx(0.45)
        paso._progreso(150.0)  # se recorta, no se sale
        assert paso.barra.cget("_valor") == 1.0

    def test_el_progreso_de_fastboot_llega_al_final_con_saltos(self, wizard, tmp_path):
        # Una partición saltada emite una línea y una escrita dos: si el
        # progreso contase llamadas en vez de leer la marca [i/total], la
        # barra se quedaría corta.
        import time

        carpeta = rom_de_prueba(tmp_path, "lancelot")
        (carpeta / "images" / "nvram.img").write_bytes(b"\x00" * 512)
        wizard.estado.dispositivo = Dispositivo(modo=MODO_FASTBOOT, codename="lancelot")
        wizard.estado.firmware = validar.analizar(carpeta)

        from core import binarios, fastboot

        monkeypatched = fastboot.flashear_particion
        fastboot.flashear_particion = lambda p, r: binarios.Resultado(True)
        try:
            paso = wizard.pasos[3]
            paso.al_entrar()
            paso._flashear_por_fastboot()
            for _ in range(200):
                wizard._vaciar_cola()
                if paso.barra.cget("_valor") == 1.0:
                    break
                time.sleep(0.01)
        finally:
            fastboot.flashear_particion = monkeypatched

        assert paso.barra.cget("_valor") == pytest.approx(1.0)

    def test_reintentar_tras_cancelar_no_arrastra_el_estado(self, wizard, tmp_path):
        # Un segundo intento que sale bien no puede reportarse como cancelado
        # solo porque el primero lo fuera.
        paso = self._preparar(wizard, tmp_path)
        paso.operacion_en_curso = True
        paso._al_terminar(-1)
        assert wizard.estado.flash_cancelado is True

        DIALOGOS.respuesta_si_no = True
        wizard.estado.dispositivo = Dispositivo(modo="MODO_INVENTADO", codename="x")
        paso._empezar()  # cae en la rama «no sé flashear en este modo»
        assert wizard.estado.flash_cancelado is False

    def test_cancelar_mientras_prepara_no_llega_a_escribir(self, wizard, tmp_path, monkeypatch):
        # El botón Cancelar está activo desde el primer segundo, pero preparar
        # las imágenes tarda. Cancelar ahí debe abortar, no escribir igual.
        import time

        from core import mtk

        escrituras = []
        monkeypatch.setattr(
            mtk, "flashear_carpeta", lambda *a, **k: escrituras.append(a) or None
        )

        paso = self._preparar(wizard, tmp_path)
        paso.operacion_en_curso = True
        paso._flashear_por_brom()
        wizard.estado.flash_cancelado = True  # el usuario pulsa Cancelar

        for _ in range(200):
            wizard._vaciar_cola()
            if not paso.operacion_en_curso:
                break
            time.sleep(0.01)

        assert escrituras == []
        assert wizard.estado.flash_cancelado is True

    def test_no_se_puede_salir_mientras_escribe(self, wizard, tmp_path):
        paso = self._preparar(wizard, tmp_path)
        paso.operacion_en_curso = True
        assert paso.al_salir() is False

    def test_al_entrar_se_limpia_lo_anterior(self, wizard, tmp_path):
        paso = self._preparar(wizard, tmp_path)
        paso._escribir("basura del intento anterior")
        wizard.estado.flash_correcto = True
        paso.al_entrar()
        assert wizard.estado.flash_correcto is False
        assert wizard.estado.registro_flash == []


class TestHerramientas:
    def test_el_boton_aparece_solo_con_movil(self, wizard):
        paso = wizard.pasos[1]
        paso._al_detectar(None)
        assert not paso.boton_herramientas.empaquetado
        paso._al_detectar(Dispositivo(modo=MODO_BROM, modelo="Redmi 9"))
        assert paso.boton_herramientas.empaquetado

    def test_la_ventana_se_construye(self, wizard):
        from ui.herramientas import VentanaHerramientas

        wizard.estado.dispositivo = Dispositivo(modo=MODO_BROM, modelo="Redmi 9")
        ventana = VentanaHerramientas(wizard)
        # Sin reventar, con su registro listo.
        assert ventana.registro is not None

    def test_la_ventana_aguanta_sin_dispositivo(self, wizard):
        from ui.herramientas import VentanaHerramientas

        wizard.estado.dispositivo = None
        ventana = VentanaHerramientas(wizard)
        assert ventana is not None

    def test_el_boton_de_secure_boot_lanza_el_payload(self, wizard, monkeypatch):
        from core import mtk
        from ui.herramientas import VentanaHerramientas

        wizard.estado.dispositivo = Dispositivo(modo=MODO_BROM, modelo="Redmi 9")
        ventana = VentanaHerramientas(wizard)

        llamado = {}
        monkeypatch.setattr(
            mtk,
            "lanzar_payload",
            lambda **k: llamado.setdefault("si", True) or "seg",
        )
        ventana._preparar_brom()
        assert llamado.get("si") is True


class TestPasoResultado:
    def test_exito(self, wizard):
        wizard.estado.flash_correcto = True
        paso = wizard.pasos[4]
        paso.al_entrar()
        assert "Listo" in paso.titulo_resultado.cget("text")
        assert "10 segundos" in paso.texto.cget("text")

    def test_cancelado(self, wizard):
        wizard.estado.flash_cancelado = True
        paso = wizard.pasos[4]
        paso.al_entrar()
        assert "Cancelado" in paso.titulo_resultado.cget("text")

    def test_fallo_enseña_la_explicacion(self, wizard):
        wizard.estado.flash_correcto = False
        wizard.estado.mensaje_error = "Explicación traducida del error"
        paso = wizard.pasos[4]
        paso.al_entrar()
        assert "Explicación traducida" in paso.texto.cget("text")

    def test_empezar_de_nuevo_vuelve_a_detectar(self, wizard):
        wizard.estado.dispositivo = Dispositivo(modo=MODO_BROM)
        wizard.pasos[4]._empezar_de_nuevo()
        assert wizard.indice == 1
        assert wizard.estado.dispositivo is None

    def test_guardar_el_registro(self, wizard, tmp_path):
        wizard.estado.registro_flash = ["línea uno", "línea dos"]
        wizard.estado.dispositivo = Dispositivo(modo=MODO_BROM, modelo="Redmi 9")
        destino = tmp_path / "registro.txt"
        DIALOGOS.ruta_a_devolver = str(destino)

        wizard.pasos[4]._guardar_registro()
        contenido = destino.read_text(encoding="utf-8")
        assert "línea uno" in contenido
        assert "Redmi 9" in contenido

    def test_sin_registro_avisa(self, wizard):
        wizard.estado.registro_flash = []
        wizard.pasos[4]._guardar_registro()
        assert any(llamada[0] == "showinfo" for llamada in DIALOGOS.llamadas)
