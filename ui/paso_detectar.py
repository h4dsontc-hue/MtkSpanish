"""Paso 1 — Detectar el móvil conectado y en qué estado está."""

from __future__ import annotations

import customtkinter as ctk

from core import detector, mtk
from core.detector import MODO_ADB, MODO_BROM, MODO_FASTBOOT, MODO_PRELOADER
from ui import base
from ui.base import PasoBase, Tarjeta

INSTRUCCIONES_BROM = (
    "Si el móvil NO enciende, para que lo detecte:\n\n"
    "  1.  Desconecta el cable del todo.\n"
    "  2.  Mantén pulsado Encendido + Volumen abajo unos 10 segundos para apagarlo.\n"
    "  3.  Pulsa «Buscar móvil» aquí abajo.\n"
    "  4.  Conecta el cable manteniendo pulsado VOLUMEN ABAJO.\n\n"
    "Usa un cable de datos enchufado directamente al ordenador, sin hubs."
)

# Cada modo lleva a una estrategia distinta y conviene decírselo al usuario ya.
CONSEJO_POR_MODO = {
    MODO_ADB: (
        "El móvil arranca y responde. Si solo quieres reinstalar el sistema, "
        "se reiniciará al modo fastboot en el siguiente paso."
    ),
    MODO_FASTBOOT: (
        "El bootloader responde. Se puede reinstalar el firmware sin necesidad "
        "de recurrir al modo BROM."
    ),
    MODO_BROM: (
        "El móvil está en modo BROM: es el modo de rescate más profundo. "
        "Desde aquí se puede reinstalar todo aunque el móvil no encienda."
    ),
    MODO_PRELOADER: (
        "El móvil está en modo preloader. Se puede rescatar, aunque es menos "
        "estable que BROM: si falla, prueba a entrar en BROM apagándolo del todo."
    ),
}


class PasoDetectar(PasoBase):
    titulo = "Conecta tu móvil"
    subtitulo = "Vamos a ver en qué estado está y qué se puede hacer con él."

    def construir(self, cuerpo) -> None:
        self.instrucciones = ctk.CTkLabel(
            cuerpo,
            text=INSTRUCCIONES_BROM,
            font=base.fuente_normal(),
            justify="left",
            anchor="w",
            wraplength=840,
        )
        self.instrucciones.pack(fill="x", pady=(0, 12))

        botones = ctk.CTkFrame(cuerpo, fg_color="transparent")
        botones.pack(fill="x", pady=(0, 12))

        self.boton_buscar = ctk.CTkButton(
            botones, text="Buscar móvil", width=170, command=self._detectar
        )
        self.boton_buscar.pack(side="left")

        self.variable_auto = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            botones,
            text="Seguir buscando automáticamente",
            variable=self.variable_auto,
            font=base.fuente_normal(),
            command=self._cambiar_auto,
        ).pack(side="left", padx=14)

        self.tarjeta = Tarjeta(cuerpo)
        self.tarjeta.pack(fill="both", expand=True)

        self.etiqueta_resultado = ctk.CTkLabel(
            self.tarjeta,
            text="Todavía no se ha buscado ningún dispositivo.",
            font=base.fuente_subtitulo(),
            justify="left",
            anchor="w",
            wraplength=800,
        )
        self.etiqueta_resultado.pack(fill="x", padx=16, pady=(14, 6))

        self.etiqueta_detalle = ctk.CTkLabel(
            self.tarjeta,
            text="",
            font=base.fuente_normal(),
            text_color=base.GRIS,
            justify="left",
            anchor="w",
            wraplength=800,
        )
        self.etiqueta_detalle.pack(fill="x", padx=16, pady=(0, 6))

        self.etiqueta_protecciones = ctk.CTkLabel(
            self.tarjeta,
            text="",
            font=base.fuente_normal(),
            justify="left",
            anchor="w",
            wraplength=800,
        )
        self.etiqueta_protecciones.pack(fill="x", padx=16, pady=(0, 14))

        self.boton_protecciones = ctk.CTkButton(
            self.tarjeta,
            text="Comprobar protecciones del fabricante",
            width=280,
            fg_color=base.GRIS,
            command=self._leer_protecciones,
        )

        self._tarea_auto = None
        self.buscando = False

    # ───────────────────────────── lógica ─────────────────────────────

    def al_entrar(self) -> None:
        self.permitir_avance(self.estado.dispositivo is not None)
        if self.estado.dispositivo is None:
            self._detectar()
        if self.variable_auto.get():
            self._programar_auto()

    def al_salir(self) -> bool:
        self._parar_auto()
        return self.estado.dispositivo is not None

    def _cambiar_auto(self) -> None:
        if self.variable_auto.get():
            self._programar_auto()
        else:
            self._parar_auto()

    def _programar_auto(self) -> None:
        self._parar_auto()
        # Cada 3 segundos: suficiente para que parezca instantáneo al conectar
        # el cable, sin machacar el USB con consultas.
        self._tarea_auto = self.wizard.after(3000, self._latido)

    def _parar_auto(self) -> None:
        if self._tarea_auto is not None:
            try:
                self.wizard.after_cancel(self._tarea_auto)
            except Exception:
                pass
            self._tarea_auto = None

    def _latido(self) -> None:
        """Reintento automático mientras no haya nada detectado."""
        self._tarea_auto = None
        if self.wizard.indice != 1 or not self.variable_auto.get():
            return
        if self.estado.dispositivo is None and not self.buscando:
            self._detectar(silencioso=True)
        self._programar_auto()

    def _detectar(self, silencioso: bool = False) -> None:
        if self.buscando:
            return
        self.buscando = True
        if not silencioso:
            self.boton_buscar.configure(state="disabled", text="Buscando...")
            self.wizard.decir("Buscando dispositivos conectados...", base.AZUL)
        self.en_segundo_plano(detector.detectar, self._al_detectar)

    def _al_detectar(self, dispositivo) -> None:
        self.buscando = False
        self.boton_buscar.configure(state="normal", text="Buscar móvil")

        if isinstance(dispositivo, Exception):
            self.etiqueta_resultado.configure(
                text="Error al buscar el dispositivo", text_color=base.ROJO
            )
            self.etiqueta_detalle.configure(text=str(dispositivo))
            self.permitir_avance(False)
            return

        if dispositivo is None:
            self.estado.dispositivo = None
            self.etiqueta_resultado.configure(
                text=f"{base.ICONO_ESPERA}  No se detecta ningún móvil",
                text_color=base.GRIS,
            )
            self.etiqueta_detalle.configure(text=detector.diagnostico_sin_dispositivo())
            self.etiqueta_protecciones.configure(text="")
            self.boton_protecciones.pack_forget()
            self.permitir_avance(False)
            self.wizard.decir("Esperando a que conectes el móvil...", base.GRIS)
            return

        self.estado.dispositivo = dispositivo
        self.etiqueta_resultado.configure(
            text=f"{base.ICONO_OK}  Móvil detectado", text_color=base.VERDE
        )
        detalle = dispositivo.resumen()
        consejo = CONSEJO_POR_MODO.get(dispositivo.modo, "")
        self.etiqueta_detalle.configure(text=f"{detalle}\n\n{consejo}")

        # Solo en BROM/preloader tiene sentido preguntar por SBC/DAA, y solo
        # ahí decide si el rescate va a poder funcionar.
        if dispositivo.modo in (MODO_BROM, MODO_PRELOADER) and mtk.disponible():
            self.boton_protecciones.pack(padx=16, pady=(0, 14), anchor="w")
        else:
            self.boton_protecciones.pack_forget()

        self.permitir_avance(dispositivo.se_puede_flashear or dispositivo.modo == MODO_ADB)
        self.wizard.decir(dispositivo.descripcion_modo, base.VERDE)
        self._parar_auto()

    def _leer_protecciones(self) -> None:
        self.boton_protecciones.configure(state="disabled", text="Consultando el móvil...")
        self.etiqueta_protecciones.configure(
            text="Hablando con el bootrom, esto tarda unos segundos...",
            text_color=base.GRIS,
        )
        self.en_segundo_plano(mtk.leer_configuracion, self._al_leer_protecciones)

    def _al_leer_protecciones(self, configuracion) -> None:
        self.boton_protecciones.configure(
            state="normal", text="Comprobar protecciones del fabricante"
        )

        if isinstance(configuracion, Exception):
            self.etiqueta_protecciones.configure(
                text=f"No se pudo consultar: {configuracion}", text_color=base.ROJO
            )
            return

        self.estado.configuracion_objetivo = configuracion
        if configuracion.sbc is None and configuracion.daa is None:
            self.etiqueta_protecciones.configure(
                text=(
                    "El móvil no ha contestado a la consulta de protecciones. "
                    "Puede que se haya desconectado: vuelve a ponerlo en modo BROM."
                ),
                text_color=base.AMBAR,
            )
            return

        self.etiqueta_protecciones.configure(
            text=configuracion.explicacion(),
            text_color=base.AMBAR if configuracion.protegido else base.VERDE,
        )
