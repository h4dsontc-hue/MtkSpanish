"""Paso 3 — Escribir el firmware en el móvil.

Es el único paso que no se puede deshacer, así que hay tres cosas que importan
más que la estética:

  * que el usuario sepa exactamente qué se va a escribir antes de empezar;
  * que la barra de progreso se mueva de verdad, para que nadie desconecte el
    cable pensando que se ha colgado;
  * que se pueda cancelar, y que cancelar avise de lo que eso implica.
"""

from __future__ import annotations

import re
import time
from tkinter import messagebox

import customtkinter as ctk

from core import adb, detector, errores, fastboot, mtk
from core.detector import MODO_ADB, MODO_BROM, MODO_FASTBOOT, MODO_PRELOADER
from ui import base
from ui.base import PasoBase, Registro, Tarjeta
from utils import validar

AVISO_FINAL = (
    "Esto va a BORRAR TODOS LOS DATOS del móvil y a reinstalar el sistema.\n\n"
    "Mientras dure:\n"
    "  •  NO desconectes el cable USB.\n"
    "  •  NO apagues el ordenador ni dejes que se suspenda.\n"
    "  •  NO toques los botones del móvil.\n\n"
    "Puede tardar entre 5 y 20 minutos.\n\n"
    "¿Empezamos?"
)


class PasoFlash(PasoBase):
    titulo = "Reinstalar el firmware"
    subtitulo = "Revisa el resumen y, cuando estés listo, empieza. No desconectes nada durante el proceso."

    def construir(self, cuerpo) -> None:
        self.operacion_en_curso = False
        self.seguimiento = None
        self.carpeta_temporal = None
        self.hubo_errores = False

        self.tarjeta_resumen = Tarjeta(cuerpo)
        self.tarjeta_resumen.pack(fill="x")

        self.etiqueta_resumen = ctk.CTkLabel(
            self.tarjeta_resumen,
            text="",
            font=base.fuente_normal(),
            justify="left",
            anchor="w",
            wraplength=820,
        )
        self.etiqueta_resumen.pack(fill="x", padx=16, pady=14)

        # Marcado por defecto: perder el IMEI es el peor final posible, y una
        # copia previa es lo único que lo devuelve. Solo tiene sentido por BROM,
        # que es donde se pueden leer las particiones.
        self.variable_backup = ctk.BooleanVar(value=True)
        self.check_backup = ctk.CTkCheckBox(
            cuerpo,
            text="Hacer copia de seguridad del IMEI/NVRAM antes de flashear (recomendado)",
            variable=self.variable_backup,
            font=base.fuente_normal(),
        )
        self.check_backup.pack(fill="x", padx=4, pady=(0, 4))

        controles = ctk.CTkFrame(cuerpo, fg_color="transparent")
        controles.pack(fill="x", pady=12)

        self.boton_empezar = ctk.CTkButton(
            controles,
            text="Empezar a reinstalar",
            width=220,
            height=40,
            command=self._empezar,
        )
        self.boton_empezar.pack(side="left")

        self.boton_cancelar = ctk.CTkButton(
            controles,
            text="Cancelar",
            width=130,
            height=40,
            fg_color=base.ROJO,
            command=self._cancelar,
            state="disabled",
        )
        self.boton_cancelar.pack(side="left", padx=12)

        self.etiqueta_fase = ctk.CTkLabel(
            controles, text="", font=base.fuente_normal(), text_color=base.GRIS, anchor="w"
        )
        self.etiqueta_fase.pack(side="left", fill="x", expand=True, padx=10)

        self.barra = ctk.CTkProgressBar(cuerpo)
        self.barra.set(0)
        self.barra.pack(fill="x", pady=(0, 10))

        self.registro = Registro(cuerpo, height=240)
        self.registro.pack(fill="both", expand=True)

    # ───────────────────────────── ciclo de vida ─────────────────────────────

    def al_entrar(self) -> None:
        self.estado.reiniciar_flasheo()
        self.hubo_errores = False
        self.barra.set(0)
        self.registro.limpiar()
        self.etiqueta_fase.configure(text="")
        self.boton_empezar.configure(state="normal", text="Empezar a reinstalar")
        self.boton_cancelar.configure(state="disabled")
        self.etiqueta_resumen.configure(text=self._texto_resumen())

        # El backup solo se puede leer por BROM/preloader (fastboot no lee).
        if self.estado.modo in (MODO_BROM, MODO_PRELOADER):
            self.check_backup.configure(
                state="normal",
                text="Hacer copia de seguridad del IMEI/NVRAM antes de flashear (recomendado)",
            )
        else:
            self.variable_backup.set(False)
            self.check_backup.configure(
                state="disabled",
                text="Copia del IMEI no disponible en este modo (solo por BROM)",
            )
        # Hasta que no termine el flasheo no hay nada que ver en el paso 4.
        self.permitir_avance(False)

    def al_salir(self) -> bool:
        return not self.operacion_en_curso

    def _texto_resumen(self) -> str:
        dispositivo = self.estado.dispositivo
        firmware = self.estado.firmware
        if dispositivo is None or firmware is None:
            return "Faltan datos. Vuelve atrás y completa los pasos anteriores."

        seguras = firmware.imagenes_seguras()
        saltadas = set(firmware.imagenes) - set(seguras)

        lineas = [
            f"Móvil:      {dispositivo.modelo}"
            + (f" ({dispositivo.codename})" if dispositivo.codename else ""),
            f"Modo:       {dispositivo.descripcion_modo}",
            f"Método:     {self._nombre_metodo()}",
            "",
            f"Firmware:   {firmware.nombre_tipo}"
            + (f" — {firmware.version}" if firmware.version else ""),
            f"Carpeta:    {firmware.ruta}",
            f"Se escriben {len(seguras)} particiones "
            f"({validar.formatear_tamano(sum(r.stat().st_size for r in seguras.values()))}):",
            "            " + ", ".join(sorted(seguras)),
        ]
        if saltadas:
            lineas += [
                "",
                f"{base.ICONO_AVISO}  Se saltan {len(saltadas)} particiones con datos únicos de "
                f"tu móvil: {', '.join(sorted(saltadas))}.",
            ]
        return "\n".join(lineas)

    def _nombre_metodo(self) -> str:
        modo = self.estado.modo
        if modo in (MODO_BROM, MODO_PRELOADER):
            return "MTKClient (bootrom)"
        if modo == MODO_FASTBOOT:
            return "fastboot"
        if modo == MODO_ADB:
            return "reiniciar a fastboot y flashear"
        return "desconocido"

    # ───────────────────────────── arranque ─────────────────────────────

    def _empezar(self) -> None:
        if self.estado.dispositivo is None or self.estado.firmware is None:
            messagebox.showerror(
                "Faltan datos", "Vuelve atrás y completa los pasos anteriores."
            )
            return
        if not messagebox.askyesno("Última confirmación", AVISO_FINAL, icon="warning"):
            return

        # Sin este reinicio, un segundo intento tras una cancelación arrastraría
        # `flash_cancelado = True` y el paso 5 diría «cancelado» aunque esta vez
        # hubiera salido bien.
        self.estado.reiniciar_flasheo()
        self.operacion_en_curso = True
        self.hubo_errores = False
        self.seguimiento = None
        self.boton_empezar.configure(state="disabled", text="Reinstalando...")
        self.boton_cancelar.configure(state="normal")
        self.wizard.bloquear_navegacion(True)
        self.registro.limpiar()
        self.barra.set(0)

        modo = self.estado.modo
        # Si toca copia de seguridad, se hace antes de escribir nada; cuando
        # termina, sigue el flasheo. Si no, se flashea directamente.
        if modo in (MODO_BROM, MODO_PRELOADER) and self.variable_backup.get():
            self._respaldar_y_continuar()
        else:
            self._flashear_segun_modo()

    def _flashear_segun_modo(self) -> None:
        modo = self.estado.modo
        if modo in (MODO_BROM, MODO_PRELOADER):
            self._flashear_por_brom()
        elif modo == MODO_FASTBOOT:
            self._flashear_por_fastboot()
        elif modo == MODO_ADB:
            self._reiniciar_y_flashear()
        else:
            self._escribir("No se sabe cómo flashear en este modo.", error=True)
            self._al_terminar(1)

    # ───────────────────────── copia previa ─────────────────────────

    def _respaldar_y_continuar(self) -> None:
        from core import herramientas

        self._fase("Copia de seguridad del IMEI antes de flashear...")
        destino = herramientas.carpeta_backup_por_defecto(self.estado.codename)

        def buscar():
            return herramientas.particiones_a_respaldar()

        def continuar(particiones):
            if self.estado.flash_cancelado:
                self._escribir("Cancelado antes de la copia.")
                self._al_terminar(-1)
                return
            if isinstance(particiones, Exception) or not particiones:
                motivo = (
                    str(particiones)
                    if isinstance(particiones, Exception)
                    else "el móvil no ha devuelto ninguna partición crítica"
                )
                self._escribir(f"No se pudo preparar la copia: {motivo}", error=True)
                self._preguntar_seguir_sin_copia()
                return
            self._escribir(f"Copiando {', '.join(particiones)} a {destino}")
            self.seguimiento = herramientas.respaldar(
                destino,
                particiones,
                al_recibir_linea=lambda l: self.en_ui(self._escribir, l),
                al_progresar=lambda p: self.en_ui(self._progreso, p),
                al_terminar=lambda c: self.en_ui(self._tras_copia, c, destino),
            )

        self.en_segundo_plano(buscar, continuar)

    def _tras_copia(self, codigo: int, destino) -> None:
        if self.estado.flash_cancelado:
            self._al_terminar(-1)
            return
        if codigo == 0:
            self._escribir(f"Copia de seguridad guardada en {destino}")
            self.estado.ruta_backup = str(destino)
            self.barra.set(0)
            self._flashear_segun_modo()
        else:
            self._escribir("La copia de seguridad falló.", error=True)
            self._preguntar_seguir_sin_copia()

    def _preguntar_seguir_sin_copia(self) -> None:
        seguir = messagebox.askyesno(
            "La copia no se pudo hacer",
            "No se ha podido guardar la copia del IMEI.\n\n"
            "Si continúas y algo sale mal, no habrá forma de recuperar el IMEI.\n\n"
            "¿Continuar de todos modos con la reinstalación?",
            icon="warning",
        )
        if seguir:
            self.barra.set(0)
            self._flashear_segun_modo()
        else:
            self.estado.flash_cancelado = True
            self._al_terminar(-1)

    # ───────────────────────────── estrategias ─────────────────────────────

    def _flashear_por_brom(self) -> None:
        self._fase("Preparando las imágenes...")
        firmware = self.estado.firmware

        def preparar():
            # `mtk wl` deduce la partición del nombre del archivo y escribiría
            # cualquier cosa que encuentre en la carpeta, así que se le pasa
            # una carpeta nueva con solo lo que queremos escribir.
            return mtk.preparar_carpeta_de_flasheo(firmware.imagenes_seguras())

        def continuar(carpeta):
            if isinstance(carpeta, Exception):
                self._escribir(f"No se pudieron preparar las imágenes: {carpeta}", error=True)
                self._al_terminar(1)
                return
            self.carpeta_temporal = carpeta
            # Preparar las imágenes tarda, y el botón «Cancelar» ya está activo
            # durante ese rato. Si el usuario canceló mientras tanto, no hay
            # que empezar a escribir: sería justo lo contrario de lo que pidió.
            if self.estado.flash_cancelado:
                self._escribir("Cancelado antes de empezar a escribir.")
                self._al_terminar(-1)
                return
            self._escribir(f"Imágenes preparadas en {carpeta}")
            self._fase("Escribiendo en la memoria del móvil...")
            self.seguimiento = mtk.flashear_carpeta(
                carpeta,
                al_recibir_linea=lambda linea: self.en_ui(self._escribir, linea),
                al_progresar=lambda porcentaje: self.en_ui(self._progreso, porcentaje),
                al_terminar=lambda codigo: self.en_ui(self._al_terminar, codigo),
            )

        self.en_segundo_plano(preparar, continuar)

    def _flashear_por_fastboot(self) -> None:
        self._fase("Escribiendo por fastboot...")
        firmware = self.estado.firmware
        particiones = sorted(firmware.imagenes_seguras().items())

        def linea(texto: str) -> None:
            # Cada mensaje del lote viene marcado con «[3/12]». Se lee de ahí
            # en vez de contar llamadas: una partición saltada genera una sola
            # línea y una escrita dos, así que contarlas se desincronizaría.
            marca = re.match(r"\[(\d+)/(\d+)\]", texto)
            if marca:
                hechas, total = int(marca.group(1)), int(marca.group(2))
                self.en_ui(self._progreso, hechas / total * 100)
            self.en_ui(self._escribir, texto)

        self.seguimiento = fastboot.flashear_lote(
            particiones,
            al_recibir_linea=linea,
            al_terminar=lambda codigo: self.en_ui(self._al_terminar, codigo),
        )

    def _reiniciar_y_flashear(self) -> None:
        self._fase("Reiniciando el móvil al modo fastboot...")
        self._escribir("Pidiéndole al móvil que arranque en modo fastboot...")

        def reiniciar():
            resultado = adb.reiniciar_a_fastboot()
            if not resultado.ok:
                return resultado
            # El bootloader tarda unos segundos en aparecer por USB. Se mira
            # el flag de cancelación en cada vuelta para no dejar al usuario
            # veinte segundos esperando a algo que ya no quiere.
            for _ in range(20):
                if self.estado.flash_cancelado:
                    return False
                time.sleep(1)
                if detector.detectar_modo() == MODO_FASTBOOT:
                    return True
            return False

        def continuar(resultado):
            if self.estado.flash_cancelado:
                self._escribir("Cancelado durante el reinicio.")
                self._al_terminar(-1)
                return
            if resultado is True:
                self._escribir("El móvil ya está en modo fastboot.")
                self.estado.dispositivo = fastboot.describir_dispositivo()
                self._flashear_por_fastboot()
                return
            detalle = resultado.texto if hasattr(resultado, "texto") else ""
            self._escribir(
                "El móvil no llegó a modo fastboot. " + detalle, error=True
            )
            self._al_terminar(1)

        self.en_segundo_plano(reiniciar, continuar)

    # ───────────────────────────── progreso ─────────────────────────────

    def _fase(self, texto: str) -> None:
        self.etiqueta_fase.configure(text=texto)

    def _escribir(self, linea: str, error: bool = False) -> None:
        es_error = error or errores.es_linea_de_error(linea)
        if es_error:
            self.hubo_errores = True
        self.registro.escribir(linea, error=es_error)
        self.estado.registro_flash.append(linea)

    def _progreso(self, porcentaje: float) -> None:
        self.barra.set(max(0.0, min(porcentaje / 100.0, 1.0)))
        if self.seguimiento is not None and getattr(self.seguimiento, "particion_actual", ""):
            self._fase(
                f"Escribiendo {self.seguimiento.particion_actual}... {porcentaje:.0f}%"
            )

    def _cancelar(self) -> None:
        if not messagebox.askyesno(
            "Cancelar la reinstalación",
            "Si cancelas ahora, el móvil se queda a medio escribir y "
            "probablemente no arrancará.\n\n"
            "Podrás volver a intentarlo, pero tendrás que empezar de cero.\n\n"
            "¿Seguro que quieres cancelar?",
            icon="warning",
        ):
            return
        self._escribir("Cancelando...", error=True)
        self.estado.flash_cancelado = True
        if self.seguimiento is not None:
            self.seguimiento.cancelar()
        self.boton_cancelar.configure(state="disabled")

    # ───────────────────────────── final ─────────────────────────────

    def _al_terminar(self, codigo: int) -> None:
        self.operacion_en_curso = False
        self.boton_cancelar.configure(state="disabled")
        self.boton_empezar.configure(state="normal", text="Volver a intentarlo")
        self.wizard.bloquear_navegacion(False)
        self._limpiar_temporales()

        cancelado = codigo == -1 or self.estado.flash_cancelado
        correcto = codigo == 0 and not cancelado and not self.hubo_errores

        self.estado.flash_correcto = correcto
        self.estado.flash_cancelado = cancelado

        if cancelado:
            self._fase("Cancelado")
            self.wizard.decir("Reinstalación cancelada.", base.AMBAR)
        elif correcto:
            self.barra.set(1)
            self._fase("Terminado correctamente")
            self._escribir("Reinstalación completada.")
            self.wizard.decir("Listo. Pulsa «Siguiente».", base.VERDE)
            if self.estado.modo in (MODO_BROM, MODO_PRELOADER):
                # En segundo plano: `mtk reset` puede tardar hasta un minuto y
                # en el hilo de la interfaz dejaría la ventana congelada.
                self.en_segundo_plano(
                    mtk.reiniciar,
                    lambda resultado: self._escribir(
                        resultado.texto
                        if hasattr(resultado, "texto")
                        else f"No se pudo enviar el reinicio: {resultado}"
                    ),
                )
        else:
            self._fase("Terminado con errores")
            explicacion = errores.traducir("\n".join(self.estado.registro_flash[-80:]))
            self.estado.mensaje_error = str(explicacion)
            self.wizard.decir("Hubo errores. Pulsa «Siguiente» para ver qué pasó.", base.ROJO)

        self.permitir_avance(True)

    def _limpiar_temporales(self) -> None:
        if self.carpeta_temporal is None:
            return
        import shutil

        try:
            shutil.rmtree(self.carpeta_temporal, ignore_errors=True)
        finally:
            self.carpeta_temporal = None
