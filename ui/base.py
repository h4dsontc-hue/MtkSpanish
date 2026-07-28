"""Piezas comunes a todos los pasos del wizard: colores, tipografías y el marco base."""

from __future__ import annotations

import customtkinter as ctk

# Paleta. Cada color es (claro, oscuro) para que funcione con los dos temas.
VERDE = ("#1a7f37", "#2ea043")
ROJO = ("#b42318", "#f85149")
AMBAR = ("#b25e09", "#d29922")
AZUL = ("#0969da", "#4493f8")
GRIS = ("#57606a", "#8b949e")
FONDO_TARJETA = ("#f6f8fa", "#161b22")

ICONO_OK = "✔"
ICONO_MAL = "✘"
ICONO_AVISO = "⚠"
ICONO_ESPERA = "…"


def fuente_titulo() -> ctk.CTkFont:
    return ctk.CTkFont(size=24, weight="bold")


def fuente_subtitulo() -> ctk.CTkFont:
    return ctk.CTkFont(size=15)


def fuente_normal() -> ctk.CTkFont:
    return ctk.CTkFont(size=13)


def fuente_mono() -> ctk.CTkFont:
    return ctk.CTkFont(family="monospace", size=12)


class PasoBase(ctk.CTkFrame):
    """Un paso del wizard.

    El ciclo de vida es: se construye una vez, y `al_entrar` / `al_salir` se
    llaman cada vez que el usuario pasa por él. Construir una sola vez permite
    que un paso conserve su estado si el usuario retrocede y vuelve.
    """

    titulo = ""
    subtitulo = ""

    def __init__(self, contenedor, wizard):
        super().__init__(contenedor, fg_color="transparent")
        self.wizard = wizard
        self.estado = wizard.estado
        self._construir_cabecera()
        self.cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        self.cuerpo.pack(fill="both", expand=True, padx=30, pady=(0, 10))
        self.construir(self.cuerpo)

    def _construir_cabecera(self) -> None:
        cabecera = ctk.CTkFrame(self, fg_color="transparent")
        cabecera.pack(fill="x", padx=30, pady=(20, 10))
        ctk.CTkLabel(
            cabecera, text=self.titulo, font=fuente_titulo(), anchor="w"
        ).pack(fill="x")
        if self.subtitulo:
            ctk.CTkLabel(
                cabecera,
                text=self.subtitulo,
                font=fuente_subtitulo(),
                text_color=GRIS,
                anchor="w",
                justify="left",
                wraplength=800,
            ).pack(fill="x", pady=(4, 0))

    # ---- para que las sobreescriban los pasos concretos ----

    def construir(self, cuerpo) -> None:
        """Crea los widgets del paso. Se llama una sola vez."""

    def al_entrar(self) -> None:
        """Se llama cada vez que el paso se muestra."""

    def al_salir(self) -> bool:
        """Se llama al pulsar «Siguiente». Devolver False cancela el avance."""
        return True

    # ---- atajos que usan casi todos los pasos ----

    def permitir_avance(self, permitido: bool, texto: str | None = None) -> None:
        self.wizard.permitir_avance(permitido, texto)

    def en_segundo_plano(self, trabajo, al_acabar=None) -> None:
        self.wizard.en_segundo_plano(trabajo, al_acabar)

    def en_ui(self, funcion, *argumentos) -> None:
        self.wizard.en_ui(funcion, *argumentos)


class Tarjeta(ctk.CTkFrame):
    """Un bloque con fondo propio, para agrupar información."""

    def __init__(self, contenedor, **kwargs):
        kwargs.setdefault("fg_color", FONDO_TARJETA)
        kwargs.setdefault("corner_radius", 8)
        super().__init__(contenedor, **kwargs)


class LineaDeEstado(ctk.CTkFrame):
    """Una línea con icono y texto, para las listas de comprobaciones."""

    def __init__(self, contenedor, texto: str, consejo: str = ""):
        super().__init__(contenedor, fg_color="transparent")
        self.consejo = consejo

        self.icono = ctk.CTkLabel(self, text=ICONO_ESPERA, width=24, font=fuente_normal())
        self.icono.pack(side="left")

        self.texto = ctk.CTkLabel(
            self, text=texto, anchor="w", justify="left", font=fuente_normal()
        )
        self.texto.pack(side="left", fill="x", expand=True)

        self.detalle = ctk.CTkLabel(
            self, text="", anchor="e", font=fuente_normal(), text_color=GRIS
        )
        self.detalle.pack(side="right")

    def marcar(self, correcto: bool, detalle: str = "") -> None:
        self.icono.configure(
            text=ICONO_OK if correcto else ICONO_MAL,
            text_color=VERDE if correcto else ROJO,
        )
        if not correcto and not detalle and self.consejo:
            detalle = self.consejo
        self.detalle.configure(text=detalle)

    def marcar_aviso(self, detalle: str = "") -> None:
        self.icono.configure(text=ICONO_AVISO, text_color=AMBAR)
        self.detalle.configure(text=detalle)


class Registro(ctk.CTkTextbox):
    """Caja de texto de solo lectura donde se van escribiendo los mensajes."""

    def __init__(self, contenedor, **kwargs):
        kwargs.setdefault("font", fuente_mono())
        kwargs.setdefault("wrap", "word")
        super().__init__(contenedor, **kwargs)
        self.configure(state="disabled")

    def escribir(self, linea: str, error: bool = False) -> None:
        self.configure(state="normal")
        marca = "!! " if error else "   "
        self.insert("end", f"{marca}{linea}\n")
        self.see("end")
        self.configure(state="disabled")

    def limpiar(self) -> None:
        self.configure(state="normal")
        self.delete("1.0", "end")
        self.configure(state="disabled")

    def volcar(self) -> str:
        return self.get("1.0", "end")
