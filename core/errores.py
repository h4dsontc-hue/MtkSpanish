"""Traducción de los errores de las herramientas a lenguaje humano.

MTKClient, adb y fastboot escupen mensajes en inglés y muy técnicos. Aquí se
convierten en una explicación de qué ha pasado y qué puede hacer el usuario.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Explicacion:
    titulo: str
    detalle: str
    solucion: str

    def __str__(self) -> str:
        return f"{self.titulo}\n\n{self.detalle}\n\nQué hacer: {self.solucion}"


DESCONOCIDO = Explicacion(
    titulo="Error no identificado",
    detalle=(
        "La herramienta terminó con un error que no sabemos interpretar. "
        "El texto original está en el registro de abajo."
    ),
    solucion=(
        "Guarda el registro completo y búscalo en el foro de MTKClient. "
        "Volver a intentarlo con otro cable USB y otro puerto resuelve muchos casos."
    ),
)

# (patrón, explicación). El primero que coincida gana, así que van de lo más
# concreto a lo más genérico.
_REGLAS: list[tuple[re.Pattern[str], Explicacion]] = [
    (
        re.compile(r"no device detected|couldn'?t detect the device|no port detected", re.I),
        Explicacion(
            titulo="No se detecta el móvil",
            detalle=(
                "El ordenador no ve el teléfono por el cable USB. Para entrar en modo "
                "BROM el móvil tiene que estar completamente apagado antes de conectarlo."
            ),
            solucion=(
                "1) Desconecta el cable.\n"
                "2) Apaga el móvil del todo (mantén Encendido + Volumen abajo 10 segundos).\n"
                "3) Pulsa «Detectar» aquí.\n"
                "4) Conecta el cable manteniendo pulsado VOLUMEN ABAJO.\n"
                "Usa un cable de datos (no de solo carga) y un puerto USB 2.0 si puedes."
            ),
        ),
    ),
    (
        re.compile(r"sla.*enabled|daa.*(?:is )?enabled|sbc.*(?:is )?enabled", re.I),
        Explicacion(
            titulo="El móvil tiene la protección del fabricante activada",
            detalle=(
                "Este dispositivo lleva SBC/DAA/SLA activado: el bootrom solo acepta "
                "cargadores firmados por el fabricante. Sin el fichero de autenticación "
                "correcto no se puede escribir en la memoria."
            ),
            solucion=(
                "Necesitas el fichero de autenticación (auth_sv5.auth) del fabricante, "
                "o usar el modo fastboot en vez de BROM si el bootloader está desbloqueado. "
                "No hay forma de saltárselo desde esta herramienta."
            ),
        ),
    ),
    (
        re.compile(r"permission denied|access denied|usb.*permission|libusb.*access", re.I),
        Explicacion(
            titulo="Permisos de USB insuficientes",
            detalle=(
                "El sistema no deja acceder al dispositivo USB. Faltan las reglas udev "
                "o el programa no se está ejecutando con permisos suficientes."
            ),
            solucion=(
                "Vuelve al paso 0 y pulsa «Preparar sistema». Si ya lo hiciste, "
                "desconecta y vuelve a conectar el móvil para que se apliquen las reglas nuevas."
            ),
        ),
    ),
    (
        re.compile(r"modemmanager|ttyacm.*busy|device or resource busy", re.I),
        Explicacion(
            titulo="Otro programa está ocupando el puerto",
            detalle=(
                "ModemManager (el gestor de módems de Linux) ha secuestrado el puerto "
                "del móvil antes de que MTKClient pudiera usarlo."
            ),
            solucion="Vuelve al paso 0 y pulsa «Preparar sistema», que lo desactiva.",
        ),
    ),
    (
        re.compile(r"couldn'?t detect partition|partition.*not found|invalid partition", re.I),
        Explicacion(
            titulo="El firmware no encaja con este móvil",
            detalle=(
                "Alguna de las particiones del firmware no existe en el dispositivo. "
                "Casi siempre significa que el firmware es de otro modelo."
            ),
            solucion=(
                "Comprueba que el nombre en clave del firmware coincide con el detectado "
                "en el paso 1. Descargar el firmware del modelo equivocado no funciona "
                "aunque el móvil se parezca."
            ),
        ),
    ),
    (
        re.compile(r"failed to write|write.*failed|da.*error|error on sending", re.I),
        Explicacion(
            titulo="Fallo al escribir en la memoria",
            detalle=(
                "La escritura se cortó a mitad. Suele ser el cable, un hub USB o que "
                "el móvil se ha reiniciado durante el proceso."
            ),
            solucion=(
                "Conecta el cable directamente al ordenador (sin hub ni alargador), "
                "usa un puerto USB 2.0 y repite el proceso desde el paso 1. "
                "NO desconectes el móvil mientras la barra avanza."
            ),
        ),
    ),
    (
        re.compile(r"remote:?\s*.*not allowed|flashing.*not allowed|bootloader.*locked", re.I),
        Explicacion(
            titulo="El bootloader está bloqueado",
            detalle=(
                "Fastboot rechaza la escritura porque el bootloader del móvil está "
                "bloqueado por el fabricante."
            ),
            solucion=(
                "Hay que desbloquearlo primero desde la cuenta del fabricante "
                "(en Xiaomi, con Mi Unlock y su espera de días). Ojo: desbloquear borra todos los datos."
            ),
        ),
    ),
    (
        re.compile(r"device unauthorized|unauthorized", re.I),
        Explicacion(
            titulo="El móvil no ha autorizado a este ordenador",
            detalle=(
                "La depuración USB está activada pero no has aceptado la huella de "
                "este ordenador en la pantalla del móvil."
            ),
            solucion=(
                "Mira la pantalla del móvil, marca «Permitir siempre» y acepta. "
                "Si no aparece nada, desconecta y vuelve a conectar el cable."
            ),
        ),
    ),
    (
        re.compile(r"no such file or directory|no se encuentra", re.I),
        Explicacion(
            titulo="Falta un programa o un archivo",
            detalle="No se ha encontrado en el sistema algo que hace falta para continuar.",
            solucion=(
                "Vuelve al paso 0: allí se comprueba qué falta (adb, fastboot o MTKClient) "
                "y se indica cómo instalarlo."
            ),
        ),
    ),
    (
        re.compile(r"timed?\s*out|timeout", re.I),
        Explicacion(
            titulo="El móvil dejó de responder",
            detalle="La herramienta esperó una respuesta del dispositivo y no llegó a tiempo.",
            solucion=(
                "Desconecta el cable, apaga el móvil del todo y repite el proceso desde el paso 1. "
                "Prueba otro cable y otro puerto USB."
            ),
        ),
    ),
    (
        re.compile(r"keyerror|traceback \(most recent call last\)", re.I),
        Explicacion(
            titulo="MTKClient se ha roto por dentro",
            detalle=(
                "La herramienta subyacente ha lanzado un error de programación, "
                "normalmente porque el chipset no está soportado o el cargador (DA) no es el correcto."
            ),
            solucion=(
                "Comprueba en la web de MTKClient si tu chipset está soportado. "
                "Guarda el registro: es lo que hace falta para reportarlo."
            ),
        ),
    ),
]


def traducir(texto: str) -> Explicacion:
    """Convierte la salida cruda de una herramienta en una explicación en español."""
    if not texto:
        return DESCONOCIDO
    for patron, explicacion in _REGLAS:
        if patron.search(texto):
            return explicacion
    return DESCONOCIDO


def es_linea_de_error(linea: str) -> bool:
    """¿Esta línea del registro merece pintarse en rojo?"""
    return bool(re.search(r"\berror\b|\bfailed\b|\bfallo\b|traceback", linea, re.I))


def resumir_para_log(linea: str) -> str | None:
    """Traduce las líneas de progreso más comunes de MTKClient al español.

    Devuelve None si la línea no aporta nada al usuario (ruido de depuración).
    """
    limpia = linea.strip()
    if not limpia:
        return None

    ruido = (
        "Preloader - ",
        "DA_handler - ",
        "Port - ",
        "Xflash - ",
        "Legacy - ",
        "Mtk - ",
    )
    for prefijo in ruido:
        if limpia.startswith(prefijo):
            limpia = limpia[len(prefijo) :]

    reemplazos = [
        (r"^Preloader detected", "Preloader detectado"),
        (r"^Device detected", "Dispositivo detectado"),
        (r"^Connected to device", "Conectado al dispositivo"),
        (r"^Handshake failed", "Fallo al saludar al dispositivo"),
        (r"^Uploading (?:stage ?2|da)", "Enviando el cargador al móvil"),
        (r"^Successfully uploaded", "Cargador enviado correctamente"),
        (r"^Reading (.+)", r"Leyendo \1"),
        (r"^Writing (?:partition )?(.+)", r"Escribiendo la partición \1"),
        (r"^Wrote (.+?) to sector.*", r"Escrita la partición \1"),
        (r"^Failed to write (.+?) to sector.*", r"FALLO al escribir la partición \1"),
        (r"^Erasing (.+)", r"Borrando \1"),
        (r"^Reset command was sent.*", "Orden de reinicio enviada. Ya puedes desconectar el cable."),
    ]
    for patron, sustituto in reemplazos:
        nueva, n = re.subn(patron, sustituto, limpia, flags=re.I)
        if n:
            return nueva
    return limpia


PORCENTAJE = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s*%")


def extraer_porcentaje(linea: str) -> float | None:
    """Saca el porcentaje de una línea de progreso de MTKClient, si lo hay."""
    coincidencia = PORCENTAJE.search(linea)
    if not coincidencia:
        return None
    try:
        valor = float(coincidencia.group(1).replace(",", "."))
    except ValueError:
        return None
    return valor if 0.0 <= valor <= 100.0 else None
