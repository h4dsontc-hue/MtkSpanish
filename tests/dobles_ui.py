"""Dobles de customtkinter y tkinter para poder probar la interfaz sin pantalla.

No pretenden dibujar nada: implementan la superficie de la API que usa el
wizard (pack, configure, after, variables, pestañas...) para que los pasos se
puedan construir y recorrer en un test. Sirven para cazar lo que de verdad se
rompe sin un monitor delante: nombres de atributo mal escritos, widgets usados
antes de crearlos y llamadas con argumentos que no existen.
"""

from __future__ import annotations

import sys
import types


class WidgetFalso:
    def __init__(self, master=None, **kwargs):
        self.master = master
        self.opciones = dict(kwargs)
        self.hijos: list[WidgetFalso] = []
        self.empaquetado = False
        self.destruido = False
        if isinstance(master, WidgetFalso):
            master.hijos.append(self)

    # --- geometría ---
    def pack(self, **kwargs):
        self.empaquetado = True

    def pack_forget(self):
        self.empaquetado = False

    def grid(self, **kwargs):
        self.empaquetado = True

    def place(self, **kwargs):
        self.empaquetado = True

    # --- opciones ---
    def configure(self, **kwargs):
        self.opciones.update(kwargs)

    def cget(self, clave):
        return self.opciones.get(clave)

    def destroy(self):
        self.destruido = True
        if isinstance(self.master, WidgetFalso) and self in self.master.hijos:
            self.master.hijos.remove(self)

    # --- texto (CTkTextbox) ---
    def insert(self, indice, texto):
        self.opciones.setdefault("_texto", "")
        self.opciones["_texto"] += texto

    def delete(self, desde, hasta=None):
        self.opciones["_texto"] = ""

    def get(self, desde=None, hasta=None):
        return self.opciones.get("_texto", "")

    def see(self, indice):
        pass

    # --- barra de progreso ---
    def set(self, valor):
        self.opciones["_valor"] = valor

    # --- ventana raíz ---
    def title(self, texto=None):
        self.opciones["title"] = texto

    def geometry(self, valor=None):
        self.opciones["geometry"] = valor

    def minsize(self, ancho, alto):
        pass

    def protocol(self, nombre, funcion):
        self.opciones[nombre] = funcion

    def mainloop(self):
        raise AssertionError("mainloop no debe llamarse en los tests")

    def after(self, retraso, funcion=None, *args):
        # No se programa nada: los tests vacían la cola a mano.
        return f"tarea-{retraso}"

    def after_cancel(self, identificador):
        pass

    def winfo_exists(self):
        return not self.destruido


class EntradaFalsa(WidgetFalso):
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self._contenido = ""

    def insert(self, indice, texto):
        self._contenido += texto

    def delete(self, desde, hasta=None):
        self._contenido = ""

    def get(self, desde=None, hasta=None):
        return self._contenido


class VistaPestanasFalsa(WidgetFalso):
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self.pestanas: dict[str, WidgetFalso] = {}

    def add(self, nombre):
        marco = WidgetFalso(self)
        self.pestanas[nombre] = marco
        return marco

    def tab(self, nombre):
        return self.pestanas[nombre]

    def set(self, nombre):
        self.opciones["_activa"] = nombre


class VariableFalsa:
    def __init__(self, master=None, value=None, **kwargs):
        self._valor = value

    def get(self):
        return self._valor

    def set(self, valor):
        self._valor = valor


class FuenteFalsa:
    def __init__(self, **kwargs):
        self.opciones = kwargs


class DialogosFalsos:
    """Registra qué diálogos se han abierto y responde lo que le digan."""

    def __init__(self):
        self.llamadas: list[tuple[str, str, str]] = []
        self.respuesta_si_no = True
        self.ruta_a_devolver = ""

    def askyesno(self, titulo, mensaje, **kwargs):
        self.llamadas.append(("askyesno", titulo, mensaje))
        return self.respuesta_si_no

    def showerror(self, titulo, mensaje, **kwargs):
        self.llamadas.append(("showerror", titulo, mensaje))

    def showinfo(self, titulo, mensaje, **kwargs):
        self.llamadas.append(("showinfo", titulo, mensaje))

    def showwarning(self, titulo, mensaje, **kwargs):
        self.llamadas.append(("showwarning", titulo, mensaje))

    def askdirectory(self, **kwargs):
        self.llamadas.append(("askdirectory", "", ""))
        return self.ruta_a_devolver

    def asksaveasfilename(self, **kwargs):
        self.llamadas.append(("asksaveasfilename", "", ""))
        return self.ruta_a_devolver


DIALOGOS = DialogosFalsos()


def instalar() -> DialogosFalsos:
    """Mete los dobles en sys.modules. Hay que llamarlo antes de importar la UI."""
    ctk = types.ModuleType("customtkinter")

    for nombre in (
        "CTk", "CTkToplevel", "CTkFrame", "CTkLabel", "CTkButton",
        "CTkProgressBar", "CTkTextbox", "CTkScrollableFrame", "CTkCheckBox",
        "CTkRadioButton", "CTkOptionMenu", "CTkSegmentedButton", "CTkSlider",
        "CTkSwitch", "CTkComboBox",
    ):
        setattr(ctk, nombre, type(nombre, (WidgetFalso,), {}))

    ctk.CTkEntry = type("CTkEntry", (EntradaFalsa,), {})
    ctk.CTkTabview = type("CTkTabview", (VistaPestanasFalsa,), {})
    ctk.CTkFont = FuenteFalsa
    ctk.StringVar = type("StringVar", (VariableFalsa,), {})
    ctk.IntVar = type("IntVar", (VariableFalsa,), {})
    ctk.DoubleVar = type("DoubleVar", (VariableFalsa,), {})
    ctk.BooleanVar = type("BooleanVar", (VariableFalsa,), {})
    ctk.set_appearance_mode = lambda modo: None
    ctk.set_default_color_theme = lambda tema: None

    tk = types.ModuleType("tkinter")
    tk.Variable = VariableFalsa
    tk.StringVar = ctk.StringVar
    tk.IntVar = ctk.IntVar
    tk.BooleanVar = ctk.BooleanVar
    tk.DoubleVar = ctk.DoubleVar
    tk.TclError = type("TclError", (Exception,), {})

    messagebox = types.ModuleType("tkinter.messagebox")
    filedialog = types.ModuleType("tkinter.filedialog")
    for nombre in ("askyesno", "showerror", "showinfo", "showwarning"):
        setattr(messagebox, nombre, getattr(DIALOGOS, nombre))
    for nombre in ("askdirectory", "asksaveasfilename"):
        setattr(filedialog, nombre, getattr(DIALOGOS, nombre))

    tk.messagebox = messagebox
    tk.filedialog = filedialog

    sys.modules["customtkinter"] = ctk
    sys.modules["tkinter"] = tk
    sys.modules["tkinter.messagebox"] = messagebox
    sys.modules["tkinter.filedialog"] = filedialog

    return DIALOGOS
