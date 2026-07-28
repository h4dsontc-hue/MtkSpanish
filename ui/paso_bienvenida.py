"""Paso 0 — Bienvenida y preparación del sistema."""

from __future__ import annotations

import customtkinter as ctk

from ui import base
from ui.base import LineaDeEstado, PasoBase, Tarjeta
from utils import sistema

EXPLICACION = (
    "Esta herramienta sirve para recuperar móviles con procesador MediaTek que "
    "no arrancan, se quedan en el logo o se reinician solos.\n\n"
    "Antes de empezar, Linux necesita unos ajustes para poder hablar con el móvil. "
    "Se hacen una sola vez y se pedirá la contraseña de administrador."
)

AVISO = (
    "Reinstalar el firmware BORRA TODOS LOS DATOS del móvil: fotos, mensajes, "
    "aplicaciones y cuentas. No hay forma de recuperarlos después."
)


class PasoBienvenida(PasoBase):
    titulo = "Bienvenido a RescateMTK"
    subtitulo = "Vamos a revivir tu móvil paso a paso. No hace falta que sepas nada técnico."

    def construir(self, cuerpo) -> None:
        ctk.CTkLabel(
            cuerpo,
            text=EXPLICACION,
            font=base.fuente_normal(),
            justify="left",
            anchor="w",
            wraplength=840,
        ).pack(fill="x", pady=(0, 14))

        aviso = Tarjeta(cuerpo, fg_color=("#fff4e5", "#3d2b0f"))
        aviso.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(
            aviso,
            text=f"{base.ICONO_AVISO}  {AVISO}",
            font=base.fuente_normal(),
            text_color=base.AMBAR,
            justify="left",
            anchor="w",
            wraplength=800,
        ).pack(fill="x", padx=14, pady=12)

        tarjeta = Tarjeta(cuerpo)
        tarjeta.pack(fill="both", expand=True)

        ctk.CTkLabel(
            tarjeta,
            text="Estado del sistema",
            font=base.fuente_subtitulo(),
            anchor="w",
        ).pack(fill="x", padx=16, pady=(12, 8))

        self.contenedor_revisiones = ctk.CTkFrame(tarjeta, fg_color="transparent")
        self.contenedor_revisiones.pack(fill="x", padx=16)
        self.lineas: list[LineaDeEstado] = []

        self.barra = ctk.CTkProgressBar(tarjeta)
        self.barra.set(0)

        self.etiqueta_progreso = ctk.CTkLabel(
            tarjeta, text="", font=base.fuente_normal(), text_color=base.GRIS
        )

        self.botones = ctk.CTkFrame(tarjeta, fg_color="transparent")
        self.botones.pack(fill="x", padx=16, pady=14)
        botones = self.botones

        self.boton_preparar = ctk.CTkButton(
            botones, text="Preparar sistema", width=180, command=self._preparar
        )
        self.boton_preparar.pack(side="left")

        ctk.CTkButton(
            botones,
            text="Volver a comprobar",
            width=160,
            fg_color=base.GRIS,
            command=self._revisar,
        ).pack(side="left", padx=10)

        self._construir_actualizaciones(cuerpo)

    def _construir_actualizaciones(self, cuerpo) -> None:
        tarjeta = Tarjeta(cuerpo)
        tarjeta.pack(fill="x", pady=(12, 0))

        fila = ctk.CTkFrame(tarjeta, fg_color="transparent")
        fila.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(
            fila, text="Actualizaciones", font=base.fuente_subtitulo(), anchor="w"
        ).pack(side="left")

        self.boton_actualizaciones = ctk.CTkButton(
            fila, text="Buscar actualizaciones", width=180, command=self._buscar_actualizaciones
        )
        self.boton_actualizaciones.pack(side="right")

        self.contenedor_actualizaciones = ctk.CTkFrame(tarjeta, fg_color="transparent")
        self.contenedor_actualizaciones.pack(fill="x", padx=16, pady=(0, 12))
        self.filas_actualizacion: list = []

    # ───────────────────────────── lógica ─────────────────────────────

    def al_entrar(self) -> None:
        self._revisar()
        # Comprobación silenciosa en segundo plano: si no hay internet, no pasa
        # nada; el usuario siempre puede pulsar el botón a mano.
        if not self.filas_actualizacion:
            self._buscar_actualizaciones(silencioso=True)

    def _revisar(self) -> None:
        revisiones = sistema.revisar_entorno()

        # Se recrean las líneas en cada revisión: son pocas y así no hay que
        # llevar la cuenta de cuáles cambiaron.
        for linea in self.lineas:
            linea.destroy()
        self.lineas = []

        for descripcion, correcto, consejo in revisiones:
            linea = LineaDeEstado(self.contenedor_revisiones, descripcion, consejo)
            linea.pack(fill="x", pady=3)
            linea.marcar(correcto)
            self.lineas.append(linea)

        preparado = sistema.sistema_ya_preparado()
        self.estado.sistema_preparado = preparado

        # MTKClient es imprescindible; adb y fastboot solo hacen falta si el
        # móvil llega a arrancar, así que no bloquean el paso.
        falta_lo_critico = not any(
            descripcion.startswith("MTKClient") and correcto
            for descripcion, correcto, _ in revisiones
        )

        if falta_lo_critico:
            self.permitir_avance(False)
            self.wizard.decir(
                "Falta MTKClient: sin él no se puede rescatar nada.", base.ROJO
            )
        elif not preparado:
            self.permitir_avance(True)
            self.wizard.decir(
                "Puedes continuar, pero se recomienda pulsar «Preparar sistema» primero.",
                base.AMBAR,
            )
        else:
            self.permitir_avance(True)
            self.wizard.decir("Todo listo.", base.VERDE)

        self.boton_preparar.configure(
            text="Volver a preparar" if preparado else "Preparar sistema"
        )

    def _preparar(self) -> None:
        self.boton_preparar.configure(state="disabled", text="Preparando...")
        # `before=` para que la barra salga encima de los botones: pack los
        # coloca en orden de llamada, y estos ya están puestos desde construir().
        self.barra.pack(fill="x", padx=16, pady=(8, 0), before=self.botones)
        self.barra.set(0)
        self.etiqueta_progreso.pack(
            fill="x", padx=16, pady=(4, 0), before=self.botones
        )
        self.wizard.decir("Se te pedirá la contraseña de administrador...", base.AZUL)

        def avanzar(nombre: str, hecho: int, total: int) -> None:
            self.en_ui(self._pintar_progreso, nombre, hecho, total)

        self.en_segundo_plano(
            lambda: sistema.preparar_sistema(al_avanzar=avanzar),
            self._al_terminar_preparacion,
        )

    def _pintar_progreso(self, nombre: str, hecho: int, total: int) -> None:
        self.barra.set(hecho / total)
        self.etiqueta_progreso.configure(text=f"{nombre}...")

    def _al_terminar_preparacion(self, resultado) -> None:
        self.boton_preparar.configure(state="normal")

        if isinstance(resultado, Exception):
            self.wizard.decir(f"Error inesperado: {resultado}", base.ROJO)
            self.etiqueta_progreso.configure(text="")
            self._revisar()
            return

        self.barra.set(1 if resultado.ok else 0)
        self.etiqueta_progreso.configure(
            text=resultado.mensaje,
            text_color=base.VERDE if resultado.ok else base.ROJO,
        )
        if not resultado.ok:
            from tkinter import messagebox

            messagebox.showerror(
                "No se pudo preparar el sistema",
                f"{resultado.mensaje}\n\n{resultado.detalle[:600]}",
            )
        self._revisar()

    # ───────────────────────────── actualizaciones ─────────────────────────

    def _buscar_actualizaciones(self, silencioso: bool = False) -> None:
        from core import actualizaciones

        if not silencioso:
            self.boton_actualizaciones.configure(state="disabled", text="Buscando...")
        self.en_segundo_plano(actualizaciones.comprobar_todo, self._pintar_actualizaciones)

    def _pintar_actualizaciones(self, estados) -> None:
        self.boton_actualizaciones.configure(
            state="normal", text="Buscar actualizaciones"
        )
        for fila in self.filas_actualizacion:
            fila.destroy()
        self.filas_actualizacion = []

        if isinstance(estados, Exception):
            self._fila_actualizacion(
                f"No se pudieron comprobar las actualizaciones: {estados}", None, False
            )
            return

        for estado in estados:
            self._fila_actualizacion(
                estado.resumen(),
                estado,
                estado.hay_actualizacion and estado.se_puede_actualizar,
            )

    def _fila_actualizacion(self, texto, estado, ofrecer_boton) -> None:
        import customtkinter as ctk

        fila = ctk.CTkFrame(self.contenedor_actualizaciones, fg_color="transparent")
        fila.pack(fill="x", pady=2)

        if estado is not None and estado.error:
            color = base.GRIS
        elif estado is not None and estado.hay_actualizacion:
            color = base.AMBAR
        elif estado is not None:
            color = base.VERDE
        else:
            color = base.ROJO

        ctk.CTkLabel(
            fila, text=texto, font=base.fuente_normal(), text_color=color,
            anchor="w", justify="left", wraplength=620,
        ).pack(side="left", fill="x", expand=True)

        if ofrecer_boton:
            ctk.CTkButton(
                fila, text="Actualizar", width=110,
                command=lambda e=estado: self._actualizar(e),
            ).pack(side="right")

        self.filas_actualizacion.append(fila)

    def _actualizar(self, estado) -> None:
        from core import actualizaciones

        if estado.ruta is None:
            return
        self.wizard.decir(f"Actualizando {estado.nombre}...", base.AZUL)
        actualizaciones.actualizar(
            estado.ruta,
            al_recibir_linea=lambda l: self.en_ui(self.wizard.decir, l, base.GRIS),
            al_terminar=lambda c: self.en_ui(self._al_actualizar, estado, c),
        )

    def _al_actualizar(self, estado, codigo) -> None:
        from tkinter import messagebox

        if codigo == 0:
            self.wizard.decir(f"{estado.nombre} actualizado.", base.VERDE)
            messagebox.showinfo(
                "Actualizado",
                f"{estado.nombre} se ha actualizado.\n\n"
                "Cierra y vuelve a abrir la aplicación para usar la versión nueva.",
            )
        else:
            self.wizard.decir(f"No se pudo actualizar {estado.nombre}.", base.ROJO)
            messagebox.showerror(
                "No se pudo actualizar",
                f"La actualización de {estado.nombre} falló.\n\n"
                "Suele ser porque tienes cambios propios en esa carpeta. "
                "Actualízala a mano con «git pull» o vuelve a clonarla.",
            )
        self._buscar_actualizaciones(silencioso=True)
