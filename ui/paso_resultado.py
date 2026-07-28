"""Paso 4 — Qué ha pasado y qué hacer ahora."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ui import base
from ui.base import PasoBase, Tarjeta

EXITO = (
    "El firmware se ha reinstalado correctamente.\n\n"
    "Qué hacer ahora:\n\n"
    "  1.  Desconecta el cable USB.\n"
    "  2.  Mantén pulsado el botón de encendido unos 10 segundos.\n"
    "  3.  El primer arranque tarda mucho más de lo normal: entre 5 y 15 minutos. "
    "Es normal que se quede en el logo un buen rato, no lo desconectes ni lo apagues.\n"
    "  4.  Cuando arranque, tendrás que configurarlo de cero como si fuera nuevo.\n\n"
    "Si tras 20 minutos sigue sin arrancar, vuelve a empezar: puede que falte "
    "alguna partición que el firmware no traía."
)

CANCELADO = (
    "Has cancelado la reinstalación a mitad.\n\n"
    "El móvil se ha quedado con el firmware a medio escribir y lo más probable "
    "es que no arranque. No es un desastre: se arregla repitiendo el proceso "
    "entero desde el principio.\n\n"
    "Vuelve al paso 1, pon el móvil otra vez en modo BROM y déjalo terminar."
)


class PasoResultado(PasoBase):
    titulo = "Resultado"
    subtitulo = ""

    def construir(self, cuerpo) -> None:
        self.tarjeta = Tarjeta(cuerpo)
        self.tarjeta.pack(fill="both", expand=True)

        self.icono = ctk.CTkLabel(self.tarjeta, text="", font=ctk.CTkFont(size=48))
        self.icono.pack(pady=(24, 8))

        self.titulo_resultado = ctk.CTkLabel(
            self.tarjeta, text="", font=base.fuente_titulo()
        )
        self.titulo_resultado.pack(pady=(0, 12))

        self.texto = ctk.CTkLabel(
            self.tarjeta,
            text="",
            font=base.fuente_normal(),
            justify="left",
            anchor="nw",
            wraplength=780,
        )
        self.texto.pack(fill="both", expand=True, padx=24, pady=(0, 16))

        botones = ctk.CTkFrame(cuerpo, fg_color="transparent")
        botones.pack(fill="x", pady=12)

        ctk.CTkButton(
            botones,
            text="Guardar el registro en un archivo",
            width=240,
            fg_color=base.GRIS,
            command=self._guardar_registro,
        ).pack(side="left")

        ctk.CTkButton(
            botones,
            text="Empezar de nuevo",
            width=180,
            command=self._empezar_de_nuevo,
        ).pack(side="left", padx=12)

    def al_entrar(self) -> None:
        if self.estado.flash_cancelado:
            self._pintar(base.ICONO_AVISO, "Cancelado a mitad", CANCELADO, base.AMBAR)
            self.wizard.decir("Repite el proceso desde el paso 1.", base.AMBAR)
        elif self.estado.flash_correcto:
            texto = EXITO
            if self.estado.ruta_backup:
                texto += (
                    "\n\nGuardaste una copia del IMEI antes de flashear en:\n"
                    f"  {self.estado.ruta_backup}\n"
                    "Consérvala: es lo que te devuelve el IMEI si algún día hace falta."
                )
            self._pintar(base.ICONO_OK, "¡Listo!", texto, base.VERDE)
            self.wizard.decir("Rescate completado.", base.VERDE)
        else:
            mensaje = self.estado.mensaje_error or (
                "La reinstalación no llegó a completarse. Revisa el registro del paso anterior."
            )
            self._pintar(base.ICONO_MAL, "No ha salido bien", mensaje, base.ROJO)
            self.wizard.decir("Consulta la explicación de arriba.", base.ROJO)

    def _pintar(self, icono: str, titulo: str, texto: str, color) -> None:
        self.icono.configure(text=icono, text_color=color)
        self.titulo_resultado.configure(text=titulo, text_color=color)
        self.texto.configure(text=texto)

    def _guardar_registro(self) -> None:
        if not self.estado.registro_flash:
            messagebox.showinfo("Sin registro", "No hay ningún registro que guardar todavía.")
            return

        marca = datetime.now().strftime("%Y%m%d-%H%M%S")
        destino = filedialog.asksaveasfilename(
            title="Guardar el registro",
            defaultextension=".txt",
            initialfile=f"rescatemtk-{marca}.txt",
            filetypes=[("Archivos de texto", "*.txt"), ("Todos", "*.*")],
        )
        if not destino:
            return

        dispositivo = self.estado.dispositivo
        firmware = self.estado.firmware
        cabecera = [
            f"RescateMTK — registro del {datetime.now():%d/%m/%Y %H:%M}",
            f"Móvil: {dispositivo.modelo if dispositivo else '?'} "
            f"({dispositivo.codename if dispositivo else '?'})",
            f"Modo: {dispositivo.descripcion_modo if dispositivo else '?'}",
            f"Firmware: {firmware.ruta if firmware else '?'}",
            f"Resultado: {'correcto' if self.estado.flash_correcto else 'con errores'}",
            "-" * 70,
        ]
        try:
            Path(destino).write_text(
                "\n".join(cabecera + self.estado.registro_flash), encoding="utf-8"
            )
        except OSError as exc:
            messagebox.showerror("No se pudo guardar", str(exc))
            return
        self.wizard.decir(f"Registro guardado en {destino}", base.VERDE)

    def _empezar_de_nuevo(self) -> None:
        self.estado.reiniciar_flasheo()
        self.estado.dispositivo = None
        self.wizard.ir_a(1)
