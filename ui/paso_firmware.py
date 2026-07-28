"""Paso 2 — Elegir el firmware: una carpeta ya descargada o buscarlo en internet."""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from scraper import mifirm
from ui import base
from ui.base import PasoBase, Tarjeta
from utils import validar

AYUDA_CARPETA = (
    "Elige la carpeta del firmware ya descomprimido. Es la que contiene los "
    "archivos .img (boot.img, super.img...) o una subcarpeta «images»."
)

AYUDA_BUSQUEDA = (
    "Se busca en mifirm.net por el nombre en clave del móvil. Esa web solo "
    "tiene dispositivos Xiaomi, Redmi y POCO.\n\n"
    "Los enlaces de descarga los genera la web con JavaScript, así que la "
    "descarga se hace en tu navegador. Cuando termine, descomprime el archivo "
    "y vuelve aquí a la pestaña de al lado para elegir la carpeta."
)


class PasoFirmware(PasoBase):
    titulo = "Elige el firmware"
    subtitulo = "El firmware es el sistema que se va a reinstalar. Tiene que ser el de tu modelo exacto."

    def construir(self, cuerpo) -> None:
        self.resultados: list[mifirm.FirmwareRemoto] = []
        self.seleccion = ctk.IntVar(value=-1)
        self.filas_resultados: list[ctk.CTkFrame] = []

        pestanas = ctk.CTkTabview(cuerpo)
        pestanas.pack(fill="both", expand=True)
        self.pestanas = pestanas

        pestana_local = pestanas.add("Ya lo tengo descargado")
        pestana_buscar = pestanas.add("Buscarlo en internet")

        self._construir_local(pestana_local)
        self._construir_busqueda(pestana_buscar)

    # ─────────────────────── pestaña: carpeta local ───────────────────────

    def _construir_local(self, contenedor) -> None:
        ctk.CTkLabel(
            contenedor,
            text=AYUDA_CARPETA,
            font=base.fuente_normal(),
            justify="left",
            anchor="w",
            wraplength=800,
        ).pack(fill="x", pady=(10, 12))

        fila = ctk.CTkFrame(contenedor, fg_color="transparent")
        fila.pack(fill="x")

        ctk.CTkButton(
            fila, text="Elegir carpeta...", width=170, command=self._elegir_carpeta
        ).pack(side="left")

        self.etiqueta_carpeta = ctk.CTkLabel(
            fila,
            text="Ninguna carpeta elegida",
            font=base.fuente_normal(),
            text_color=base.GRIS,
            anchor="w",
        )
        self.etiqueta_carpeta.pack(side="left", fill="x", expand=True, padx=12)

        self.tarjeta_analisis = Tarjeta(contenedor)
        self.tarjeta_analisis.pack(fill="both", expand=True, pady=12)

        self.etiqueta_analisis = ctk.CTkLabel(
            self.tarjeta_analisis,
            text="Elige una carpeta para comprobar si el firmware sirve.",
            font=base.fuente_normal(),
            justify="left",
            anchor="nw",
            wraplength=800,
        )
        self.etiqueta_analisis.pack(fill="both", expand=True, padx=16, pady=(14, 6))

        self.boton_integridad = ctk.CTkButton(
            self.tarjeta_analisis,
            text="Verificar integridad (opcional)",
            width=240,
            fg_color=base.GRIS,
            command=self._verificar_integridad,
        )
        self.etiqueta_integridad = ctk.CTkLabel(
            self.tarjeta_analisis,
            text="",
            font=base.fuente_normal(),
            justify="left",
            anchor="w",
            wraplength=800,
        )

    def _elegir_carpeta(self) -> None:
        carpeta = filedialog.askdirectory(title="Carpeta del firmware descomprimido")
        if not carpeta:
            return
        self.etiqueta_carpeta.configure(text=carpeta, text_color=base.GRIS)
        self.etiqueta_analisis.configure(
            text="Analizando el contenido de la carpeta...", text_color=base.GRIS
        )
        self.permitir_avance(False)
        self.en_segundo_plano(lambda: validar.analizar(carpeta), self._al_analizar)

    def _al_analizar(self, firmware) -> None:
        if isinstance(firmware, Exception):
            self.etiqueta_analisis.configure(
                text=f"No se pudo analizar la carpeta: {firmware}", text_color=base.ROJO
            )
            self.permitir_avance(False)
            return

        self.boton_integridad.pack_forget()
        self.etiqueta_integridad.pack_forget()

        if firmware.problemas:
            self.estado.firmware = None
            self.etiqueta_analisis.configure(
                text=f"{base.ICONO_MAL}  " + "\n\n".join(firmware.problemas),
                text_color=base.ROJO,
            )
            self.permitir_avance(False)
            self.wizard.decir("Esa carpeta no sirve como firmware.", base.ROJO)
            return

        compatible, explicacion = validar.comprobar_compatibilidad(
            firmware, self.estado.codename
        )

        partes = [f"{base.ICONO_OK}  Firmware reconocido", "", firmware.resumen()]
        if firmware.avisos:
            partes += ["", f"{base.ICONO_AVISO}  " + f"\n{base.ICONO_AVISO}  ".join(firmware.avisos)]
        partes += ["", explicacion]

        self.etiqueta_analisis.configure(
            text="\n".join(partes),
            text_color=base.ROJO if not compatible else base.color_texto_normal(),
        )

        if not compatible:
            self.estado.firmware = None
            self.permitir_avance(False)
            self.wizard.decir("El firmware no es de este móvil.", base.ROJO)
            messagebox.showerror("Firmware equivocado", explicacion)
            return

        self.estado.firmware = firmware
        self.permitir_avance(True)
        self.wizard.decir(
            f"{len(firmware.imagenes_seguras())} particiones listas para escribir.",
            base.VERDE,
        )
        self.boton_integridad.pack(padx=16, pady=(0, 6), anchor="w")

    def _verificar_integridad(self) -> None:
        if self.estado.firmware is None:
            return
        self.boton_integridad.configure(state="disabled", text="Verificando...")
        self.etiqueta_integridad.pack(fill="x", padx=16, pady=(0, 12))
        self.etiqueta_integridad.configure(
            text="Calculando checksums (puede tardar en firmwares grandes)...",
            text_color=base.GRIS,
        )
        firmware = self.estado.firmware
        self.en_segundo_plano(
            lambda: validar.verificar_integridad(firmware),
            self._al_verificar_integridad,
        )

    def _al_verificar_integridad(self, resultado) -> None:
        self.boton_integridad.configure(
            state="normal", text="Verificar integridad (opcional)"
        )
        if isinstance(resultado, Exception):
            self.etiqueta_integridad.configure(
                text=f"No se pudo verificar: {resultado}", text_color=base.ROJO
            )
            return

        if not resultado.hay_hashes:
            color = base.AMBAR
        elif resultado.todo_ok:
            color = base.VERDE
        else:
            color = base.ROJO
        self.etiqueta_integridad.configure(text=resultado.resumen(), text_color=color)

        if resultado.hay_hashes and not resultado.todo_ok:
            # Una imagen corrupta no debe poder flashearse: se bloquea el avance.
            self.permitir_avance(False)
            self.wizard.decir("Firmware corrupto: no se puede continuar.", base.ROJO)
            messagebox.showerror("Firmware corrupto", resultado.resumen())

    # ─────────────────────── pestaña: buscar en la web ───────────────────────

    def _construir_busqueda(self, contenedor) -> None:
        ctk.CTkLabel(
            contenedor,
            text=AYUDA_BUSQUEDA,
            font=base.fuente_normal(),
            justify="left",
            anchor="w",
            wraplength=800,
        ).pack(fill="x", pady=(10, 12))

        fila = ctk.CTkFrame(contenedor, fg_color="transparent")
        fila.pack(fill="x")

        ctk.CTkLabel(
            fila, text="Nombre en clave:", font=base.fuente_normal()
        ).pack(side="left")

        self.entrada_codename = ctk.CTkEntry(
            fila, width=200, placeholder_text="por ejemplo: lancelot"
        )
        self.entrada_codename.pack(side="left", padx=10)

        self.boton_buscar = ctk.CTkButton(
            fila, text="Buscar", width=120, command=self._buscar
        )
        self.boton_buscar.pack(side="left")

        self.variable_solo_utiles = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            fila,
            text="Solo los que sirven si el móvil no arranca",
            variable=self.variable_solo_utiles,
            font=base.fuente_normal(),
        ).pack(side="left", padx=14)

        self.lista = ctk.CTkScrollableFrame(contenedor, label_text="Resultados")
        self.lista.pack(fill="both", expand=True, pady=12)

        self.etiqueta_busqueda = ctk.CTkLabel(
            self.lista,
            text="Escribe el nombre en clave y pulsa «Buscar».",
            font=base.fuente_normal(),
            text_color=base.GRIS,
            justify="left",
            anchor="w",
            wraplength=760,
        )
        self.etiqueta_busqueda.pack(fill="x", padx=8, pady=8)

        self.boton_abrir = ctk.CTkButton(
            contenedor,
            text="Abrir la descarga en el navegador",
            width=280,
            command=self._abrir_descarga,
            state="disabled",
        )
        self.boton_abrir.pack(anchor="w")

    def _buscar(self) -> None:
        codename = self.entrada_codename.get().strip()
        if not codename:
            messagebox.showinfo(
                "Falta el nombre en clave",
                "Escribe el nombre en clave del móvil (por ejemplo «lancelot»).\n\n"
                "Si el móvil no arranca y no lo sabes, búscalo en internet junto "
                "al nombre comercial del modelo.",
            )
            return

        self.boton_buscar.configure(state="disabled", text="Buscando...")
        self._limpiar_resultados()
        self.etiqueta_busqueda.configure(text="Consultando mifirm.net...")
        self.etiqueta_busqueda.pack(fill="x", padx=8, pady=8)

        solo_utiles = self.variable_solo_utiles.get()
        self.en_segundo_plano(
            lambda: mifirm.buscar_firmwares(codename, solo_utiles=solo_utiles),
            self._al_buscar,
        )

    def _limpiar_resultados(self) -> None:
        for fila in self.filas_resultados:
            fila.destroy()
        self.filas_resultados = []
        self.resultados = []
        self.seleccion.set(-1)
        self.boton_abrir.configure(state="disabled")

    def _al_buscar(self, resultados) -> None:
        self.boton_buscar.configure(state="normal", text="Buscar")

        if isinstance(resultados, mifirm.ErrorDeRed):
            self.etiqueta_busqueda.configure(text=str(resultados), text_color=base.ROJO)
            return
        if isinstance(resultados, Exception):
            self.etiqueta_busqueda.configure(
                text=f"Error inesperado al buscar: {resultados}", text_color=base.ROJO
            )
            return
        if not resultados:
            self.etiqueta_busqueda.configure(
                text=(
                    "No se ha encontrado ningún firmware para ese nombre en clave.\n"
                    "Comprueba que está bien escrito, o desmarca el filtro de arriba."
                ),
                text_color=base.AMBAR,
            )
            return

        self.etiqueta_busqueda.pack_forget()
        self.resultados = resultados

        for indice, firmware in enumerate(resultados):
            fila = ctk.CTkFrame(self.lista, fg_color="transparent")
            fila.pack(fill="x", padx=4, pady=2)
            ctk.CTkRadioButton(
                fila,
                text=firmware.descripcion(),
                variable=self.seleccion,
                value=indice,
                font=base.fuente_normal(),
                command=self._al_seleccionar,
            ).pack(side="left", anchor="w")
            self.filas_resultados.append(fila)

        self.wizard.decir(f"{len(resultados)} firmwares encontrados.", base.VERDE)

    def _al_seleccionar(self) -> None:
        self.boton_abrir.configure(state="normal")

    def _abrir_descarga(self) -> None:
        indice = self.seleccion.get()
        if not 0 <= indice < len(self.resultados):
            return
        firmware = self.resultados[indice]
        if mifirm.abrir_en_navegador(firmware.url):
            self.wizard.decir(
                "Descarga abierta en el navegador. Cuando acabe, descomprime el "
                "archivo y elígelo en la otra pestaña.",
                base.AZUL,
            )
        else:
            messagebox.showinfo(
                "Copia este enlace",
                "No se ha podido abrir el navegador. Copia esta dirección y ábrela a mano:\n\n"
                f"{firmware.url}",
            )

    # ───────────────────────────── ciclo de vida ─────────────────────────────

    def al_entrar(self) -> None:
        if not self.entrada_codename.get() and self.estado.codename:
            self.entrada_codename.insert(0, self.estado.codename)
        self.permitir_avance(self.estado.firmware is not None)
        if self.estado.firmware is None:
            self.wizard.decir("Elige una carpeta de firmware para continuar.", base.GRIS)

    def al_salir(self) -> bool:
        if self.estado.firmware is None:
            messagebox.showinfo(
                "Falta el firmware",
                "Todavía no has elegido un firmware válido.\n\n"
                "Ve a la pestaña «Ya lo tengo descargado» y elige la carpeta "
                "del firmware descomprimido.",
            )
            return False
        return True
