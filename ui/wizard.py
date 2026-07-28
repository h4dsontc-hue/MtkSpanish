"""Ventana principal: contiene los pasos y los va enseñando de uno en uno.

Sobre los hilos
---------------
Tkinter solo se puede tocar desde el hilo que creó la ventana. Todo lo que
tarda (detectar el móvil, descargar, flashear) corre en hilos aparte, así que
esos hilos NO llaman a los widgets: dejan la función en una cola y el hilo de
la interfaz la ejecuta desde `_vaciar_cola`. Es lo que evita los cuelgues
aleatorios típicos de mezclar hilos con Tk.
"""

from __future__ import annotations

import queue
import threading
import traceback
from typing import Callable

import customtkinter as ctk

from ui import base
from ui.estado import Estado

ANCHO = 940
ALTO = 700


class Wizard(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("RescateMTK — rescate de móviles MediaTek")
        self.geometry(f"{ANCHO}x{ALTO}")
        self.minsize(820, 620)

        self.estado = Estado()
        self.cola: queue.Queue[Callable[[], None]] = queue.Queue()
        self.indice = 0
        self.pasos: list[base.PasoBase] = []

        self._construir_estructura()
        self._crear_pasos()
        self._vaciar_cola()
        self.protocol("WM_DELETE_WINDOW", self._al_cerrar)

        self.mostrar_paso(0)

    # ───────────────────────────── estructura ─────────────────────────────

    def _construir_estructura(self) -> None:
        self.barra_pasos = ctk.CTkFrame(self, fg_color="transparent", height=44)
        self.barra_pasos.pack(fill="x", padx=30, pady=(14, 0))
        self.etiquetas_pasos: list[ctk.CTkLabel] = []

        self.contenedor = ctk.CTkFrame(self, fg_color="transparent")
        self.contenedor.pack(fill="both", expand=True)

        pie = ctk.CTkFrame(self, height=64)
        pie.pack(fill="x", side="bottom")

        self.boton_atras = ctk.CTkButton(
            pie, text="◀  Atrás", width=110, command=self.atras, fg_color=base.GRIS
        )
        self.boton_atras.pack(side="left", padx=(30, 10), pady=14)

        self.etiqueta_estado = ctk.CTkLabel(
            pie, text="", font=base.fuente_normal(), text_color=base.GRIS, anchor="w"
        )
        self.etiqueta_estado.pack(side="left", fill="x", expand=True, padx=10)

        self.boton_siguiente = ctk.CTkButton(
            pie, text="Siguiente  ▶", width=150, command=self.siguiente
        )
        self.boton_siguiente.pack(side="right", padx=(10, 30), pady=14)

    def _crear_pasos(self) -> None:
        # Se importan aquí y no arriba para no crear un ciclo de importación:
        # cada paso necesita el wizard, y el wizard necesita los pasos.
        from ui.paso_bienvenida import PasoBienvenida
        from ui.paso_detectar import PasoDetectar
        from ui.paso_firmware import PasoFirmware
        from ui.paso_flash import PasoFlash
        from ui.paso_resultado import PasoResultado

        clases = [PasoBienvenida, PasoDetectar, PasoFirmware, PasoFlash, PasoResultado]
        for clase in clases:
            self.pasos.append(clase(self.contenedor, self))

        nombres = ["Bienvenida", "Detectar", "Firmware", "Flashear", "Resultado"]
        for numero, nombre in enumerate(nombres):
            etiqueta = ctk.CTkLabel(
                self.barra_pasos,
                text=f"{numero + 1}. {nombre}",
                font=base.fuente_normal(),
                fg_color="transparent",
                corner_radius=6,
                width=140,
                height=30,
            )
            etiqueta.pack(side="left", padx=(0, 6))
            self.etiquetas_pasos.append(etiqueta)

    # ───────────────────────────── navegación ─────────────────────────────

    def mostrar_paso(self, indice: int) -> None:
        indice = max(0, min(indice, len(self.pasos) - 1))
        for paso in self.pasos:
            paso.pack_forget()
        self.indice = indice
        paso = self.pasos[indice]
        paso.pack(fill="both", expand=True)

        for numero, etiqueta in enumerate(self.etiquetas_pasos):
            if numero == indice:
                etiqueta.configure(fg_color=base.AZUL, text_color="white")
            elif numero < indice:
                etiqueta.configure(fg_color="transparent", text_color=base.VERDE)
            else:
                etiqueta.configure(fg_color="transparent", text_color=base.GRIS)

        self.boton_atras.configure(state="normal" if indice > 0 else "disabled")
        es_ultimo = indice == len(self.pasos) - 1
        self.boton_siguiente.configure(text="Cerrar" if es_ultimo else "Siguiente  ▶")
        self.permitir_avance(True)
        self.decir("")
        paso.al_entrar()

    def siguiente(self) -> None:
        if self.indice == len(self.pasos) - 1:
            self._al_cerrar()
            return
        if not self.pasos[self.indice].al_salir():
            return
        self.mostrar_paso(self.indice + 1)

    def atras(self) -> None:
        self.mostrar_paso(self.indice - 1)

    def ir_a(self, indice: int) -> None:
        """Salto directo, sin pasar por `al_salir`. Lo usa el paso de resultado."""
        self.mostrar_paso(indice)

    def permitir_avance(self, permitido: bool, texto: str | None = None) -> None:
        self.boton_siguiente.configure(state="normal" if permitido else "disabled")
        if texto is not None:
            self.boton_siguiente.configure(text=texto)

    def decir(self, mensaje: str, color=None) -> None:
        """Mensaje breve en el pie de la ventana."""
        self.etiqueta_estado.configure(text=mensaje, text_color=color or base.GRIS)

    def bloquear_navegacion(self, bloqueada: bool) -> None:
        """Durante el flasheo no se puede ir ni adelante ni atrás."""
        estado = "disabled" if bloqueada else "normal"
        self.boton_siguiente.configure(state=estado)
        if self.indice > 0:
            self.boton_atras.configure(state=estado)

    # ───────────────────────────── hilos y cola ─────────────────────────────

    def en_ui(self, funcion: Callable, *argumentos) -> None:
        """Ejecuta `funcion` en el hilo de la interfaz. Seguro desde cualquier hilo."""
        self.cola.put(lambda: funcion(*argumentos))

    def _vaciar_cola(self) -> None:
        while True:
            try:
                tarea = self.cola.get_nowait()
            except queue.Empty:
                break
            try:
                tarea()
            except Exception:
                # Un fallo pintando algo no debe tumbar la ventana entera.
                traceback.print_exc()
        self.after(50, self._vaciar_cola)

    def en_segundo_plano(self, trabajo: Callable, al_acabar: Callable | None = None) -> None:
        """Lanza `trabajo()` en un hilo y llama a `al_acabar(resultado)` en la UI.

        Si `trabajo` lanza una excepción, `al_acabar` la recibe como argumento
        en vez del resultado: así cada paso decide cómo enseñar el fallo.
        """

        def envoltorio() -> None:
            try:
                resultado = trabajo()
            except Exception as exc:  # noqa: BLE001 - se le entrega al paso tal cual
                resultado = exc
            if al_acabar is not None:
                self.en_ui(al_acabar, resultado)

        threading.Thread(target=envoltorio, daemon=True).start()

    # ───────────────────────────── cierre ─────────────────────────────

    def _al_cerrar(self) -> None:
        paso = self.pasos[self.indice]
        if getattr(paso, "operacion_en_curso", False):
            from tkinter import messagebox

            seguir = messagebox.askyesno(
                "Hay una operación en curso",
                "Se está escribiendo en la memoria del móvil.\n\n"
                "Si cierras ahora el móvil puede quedar inservible.\n\n"
                "¿Seguro que quieres cerrar?",
                icon="warning",
            )
            if not seguir:
                return
        self.destroy()


def lanzar() -> None:
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
    Wizard().mainloop()
