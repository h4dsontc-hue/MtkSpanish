"""Ventana de herramientas avanzadas.

Se abre desde el paso de detección, una vez hay un móvil conectado. Reúne las
operaciones de mantenimiento que no son el rescate en sí: copia y restauración
del IMEI/NVRAM, borrado de bloqueo de pantalla y las guías del bootloader y de
las cuentas Google/Mi.

Como toda la app, el trabajo pesado va en hilos y los callbacks vuelven a la UI
por la cola del wizard, nunca tocando widgets desde el hilo de trabajo.
"""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core import errores, herramientas, mtk
from core.detector import MODO_ADB
from ui import base
from ui.base import Registro


class VentanaHerramientas(ctk.CTkToplevel):
    def __init__(self, wizard):
        super().__init__(wizard)
        self.wizard = wizard
        self.estado = wizard.estado
        self.operacion = None

        self.title("Herramientas avanzadas")
        self.geometry("760x620")

        dispositivo = self.estado.dispositivo
        modo = dispositivo.modo if dispositivo else ""

        cabecera = ctk.CTkLabel(
            self,
            text="Herramientas avanzadas",
            font=base.fuente_titulo(),
            anchor="w",
        )
        cabecera.pack(fill="x", padx=20, pady=(18, 2))

        subtitulo = (
            f"Móvil: {dispositivo.modelo} · {dispositivo.descripcion_modo}"
            if dispositivo
            else "No hay ningún móvil detectado."
        )
        ctk.CTkLabel(
            self, text=subtitulo, font=base.fuente_normal(), text_color=base.GRIS,
            anchor="w",
        ).pack(fill="x", padx=20, pady=(0, 12))

        rejilla = ctk.CTkFrame(self, fg_color="transparent")
        rejilla.pack(fill="x", padx=20)
        rejilla.columnconfigure((0, 1), weight=1)

        self._boton(
            rejilla, 0, 0, "Ver información del dispositivo",
            "Modelo, chipset, estado del bootloader...", self._info,
        )
        self._boton(
            rejilla, 0, 1, "Copia de seguridad de IMEI/NVRAM",
            "Guarda las particiones únicas antes de tocar nada.",
            self._respaldar,
            habilitado=herramientas.modo_permite_backup(modo),
            motivo="Solo disponible en modo BROM.",
        )
        self._boton(
            rejilla, 1, 0, "Restaurar copia de seguridad",
            "Vuelve a escribir un backup guardado.",
            self._restaurar,
            habilitado=herramientas.modo_permite_backup(modo),
            motivo="Solo disponible en modo BROM.",
        )
        self._boton(
            rejilla, 1, 1, "Borrar bloqueo de pantalla",
            "Quita un patrón/PIN olvidado (borra todos los datos).",
            self._borrar_bloqueo,
            habilitado=modo != "" and modo != MODO_ADB,
            motivo="Reinicia a fastboot o BROM primero." if modo == MODO_ADB else "",
        )
        self._boton(
            rejilla, 2, 0, "Guía: desbloquear bootloader",
            "Pasos del método oficial de Xiaomi.",
            lambda: self._mostrar_guia(
                "Desbloquear bootloader", herramientas.GUIA_DESBLOQUEO_BOOTLOADER
            ),
        )
        self._boton(
            rejilla, 2, 1, "Cuenta Google / Mi bloqueada",
            "Qué se puede hacer (y qué no) legítimamente.",
            lambda: self._mostrar_guia(
                "Cuentas bloqueadas", herramientas.GUIA_CUENTAS
            ),
        )
        self._boton(
            rejilla, 3, 0, "Preparar sesión BROM (Secure Boot)",
            "Lanza el exploit del bootrom para poder flashear un móvil con "
            "SBC/DAA activados.",
            self._preparar_brom,
            habilitado=modo in herramientas.MODOS_BROM,
            motivo="Solo en modo BROM/preloader.",
        )

        self.etiqueta_fase = ctk.CTkLabel(
            self, text="", font=base.fuente_normal(), text_color=base.GRIS, anchor="w"
        )
        self.etiqueta_fase.pack(fill="x", padx=20, pady=(14, 2))

        self.barra = ctk.CTkProgressBar(self)
        self.barra.set(0)
        self.barra.pack(fill="x", padx=20, pady=(0, 8))

        self.registro = Registro(self, height=200)
        self.registro.pack(fill="both", expand=True, padx=20, pady=(0, 16))

    # ───────────────────────────── construcción ─────────────────────────────

    def _boton(self, padre, fila, col, titulo, ayuda, orden, habilitado=True, motivo=""):
        marco = ctk.CTkFrame(padre, fg_color=base.FONDO_TARJETA, corner_radius=8)
        marco.grid(row=fila, column=col, sticky="ew", padx=6, pady=6)

        boton = ctk.CTkButton(
            marco, text=titulo, command=orden,
            state="normal" if habilitado else "disabled",
        )
        boton.pack(fill="x", padx=10, pady=(10, 4))
        ctk.CTkLabel(
            marco,
            text=ayuda if habilitado else (motivo or ayuda),
            font=base.fuente_normal(),
            text_color=base.GRIS,
            wraplength=320,
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=10, pady=(0, 10))

    # ───────────────────────────── acciones ─────────────────────────────

    def _ocupada(self) -> bool:
        if self.operacion is not None and getattr(self.operacion, "activo", False):
            messagebox.showinfo(
                "Espera", "Hay una operación en curso. Espera a que termine."
            )
            return True
        return False

    def _log(self, linea, error=False):
        self.registro.escribir(linea, error=error or errores.es_linea_de_error(linea))

    def _progreso(self, porcentaje):
        self.barra.set(max(0.0, min(porcentaje / 100.0, 1.0)))

    def _fase(self, texto):
        self.etiqueta_fase.configure(text=texto)

    def _preparar_brom(self):
        if self._ocupada():
            return
        self._fase("Enviando el exploit al bootrom...")
        self._log(
            "Lanzando el payload de MTKClient (kamakiri/carbonara). En chipsets "
            "vulnerables esto salta SBC/DAA y abre la sesión para flashear."
        )
        self.operacion = mtk.lanzar_payload(
            al_recibir_linea=lambda l: self.wizard.en_ui(self._log, l),
            al_terminar=lambda c: self.wizard.en_ui(
                self._fin_generico, c, "Sesión BROM"
            ),
        )

    def _info(self):
        from core import detector

        self._fase("Leyendo información del dispositivo...")
        self.wizard.en_segundo_plano(detector.detectar, self._mostrar_info)

    def _mostrar_info(self, dispositivo):
        self._fase("")
        if isinstance(dispositivo, Exception):
            self._log(f"No se pudo leer: {dispositivo}", error=True)
            return
        if dispositivo is None:
            self._log("No se detecta ningún móvil.", error=True)
            return
        self._log("── Información del dispositivo ──")
        for linea in dispositivo.resumen().splitlines():
            self._log(linea)

    def _respaldar(self):
        if self._ocupada():
            return
        carpeta = filedialog.askdirectory(
            title="Dónde guardar la copia de seguridad"
        )
        if not carpeta:
            return
        destino = Path(carpeta) / herramientas.carpeta_backup_por_defecto(
            self.estado.codename
        ).name
        self._fase("Buscando qué particiones respaldar...")

        def preparar():
            return herramientas.particiones_a_respaldar()

        def continuar(particiones):
            if isinstance(particiones, Exception):
                self._fase("")
                self._log(f"No se pudo consultar el móvil: {particiones}", error=True)
                return
            if not particiones:
                self._fase("")
                self._log(
                    "No se han encontrado particiones críticas para respaldar. "
                    "Puede que el móvil no responda o esté protegido.",
                    error=True,
                )
                return
            self._log(f"Respaldando: {', '.join(particiones)}")
            self._fase(f"Guardando en {destino}...")
            self.operacion = herramientas.respaldar(
                destino,
                particiones,
                al_recibir_linea=lambda l: self.wizard.en_ui(self._log, l),
                al_progresar=lambda p: self.wizard.en_ui(self._progreso, p),
                al_terminar=lambda c: self.wizard.en_ui(self._fin_backup, c, destino),
            )

        self.wizard.en_segundo_plano(preparar, continuar)

    def _fin_backup(self, codigo, destino):
        self._fase("")
        self.barra.set(1 if codigo == 0 else 0)
        if codigo == 0:
            self._log(f"Copia de seguridad guardada en {destino}")
            messagebox.showinfo(
                "Copia hecha",
                f"El IMEI y la calibración se han guardado en:\n\n{destino}\n\n"
                "Guarda esa carpeta en sitio seguro: es lo que te devuelve el "
                "IMEI si algo sale mal.",
            )
        else:
            self._log("La copia de seguridad falló.", error=True)

    def _restaurar(self):
        if self._ocupada():
            return
        carpeta = filedialog.askdirectory(
            title="Carpeta de la copia de seguridad a restaurar"
        )
        if not carpeta:
            return
        encontrados = herramientas.backups_en(carpeta)
        if not encontrados:
            messagebox.showerror(
                "Nada que restaurar",
                "En esa carpeta no hay ninguna copia de particiones críticas "
                "(nvram.bin, nvdata.bin, ...).",
            )
            return
        if not messagebox.askyesno(
            "Restaurar copia",
            f"Se van a reescribir estas particiones desde la copia:\n\n"
            f"{', '.join(sorted(encontrados))}\n\n"
            "Hazlo solo con una copia de ESTE mismo móvil. ¿Continuar?",
            icon="warning",
        ):
            return
        self._fase("Restaurando la copia de seguridad...")
        self.operacion = herramientas.restaurar(
            carpeta,
            al_recibir_linea=lambda l: self.wizard.en_ui(self._log, l),
            al_progresar=lambda p: self.wizard.en_ui(self._progreso, p),
            al_terminar=lambda c: self.wizard.en_ui(self._fin_generico, c, "Restauración"),
        )

    def _borrar_bloqueo(self):
        if self._ocupada():
            return
        if not messagebox.askyesno(
            "Borrar bloqueo de pantalla",
            "Esto BORRA TODOS LOS DATOS del móvil (fotos, apps, cuentas), igual "
            "que un reset de fábrica. Es lo que quita un patrón o PIN olvidado.\n\n"
            "No afecta al bloqueo de cuenta Google o Mi, que es otra cosa.\n\n"
            "¿Continuar?",
            icon="warning",
        ):
            return
        modo = self.estado.modo
        self._fase("Borrando el bloqueo de pantalla...")
        self.operacion = herramientas.borrar_bloqueo_pantalla(
            modo,
            al_recibir_linea=lambda l: self.wizard.en_ui(self._log, l),
            al_terminar=lambda c: self.wizard.en_ui(self._fin_generico, c, "Borrado"),
        )
        if self.operacion is None:
            self._fase("")

    def _fin_generico(self, codigo, que):
        self._fase("")
        self.barra.set(1 if codigo == 0 else 0)
        if codigo == 0:
            self._log(f"{que} completada correctamente.")
        elif codigo == -1:
            self._log(f"{que} cancelada.", error=True)
        else:
            self._log(f"{que} terminó con errores.", error=True)

    def _mostrar_guia(self, titulo, texto):
        ventana = ctk.CTkToplevel(self)
        ventana.title(titulo)
        ventana.geometry("640x520")
        caja = Registro(ventana)
        caja.pack(fill="both", expand=True, padx=16, pady=16)
        for linea in texto.splitlines():
            caja.escribir(linea)
