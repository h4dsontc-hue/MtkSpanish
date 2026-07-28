"""Búsqueda de firmware en mifirm.net por nombre en clave del móvil.

Sobre el enlace de descarga
---------------------------
mifirm.net no publica el enlace directo al archivo en el HTML: lo genera con
JavaScript ofuscado en la página de cada firmware. Esta herramienta **no**
intenta descifrar ese mecanismo — es frágil (se rompe cada vez que tocan el
script) y salta el sistema con el que se financia la web.

Lo que sí se hace:

  * leer el listado, que es HTML limpio y da versión, Android, tamaño, fecha,
    canal y región de cada firmware;
  * abrir la página de descarga en el navegador del usuario para que descargue
    como lo haría normalmente;
  * descargar directamente si el usuario pega una URL directa de un espejo
    (ahí sí, con reanudación y barra de progreso).
"""

from __future__ import annotations

import re
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://mifirm.net"
CABECERAS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
TIMEOUT = 20

TIPO_FASTBOOT = "fastboot"
TIPO_ZIP = "zip"
TIPO_ARCHIVO = "archivo"

# Cada tipo de enlace del listado corresponde a una clase de descarga distinta.
_TIPOS_POR_RUTA = {
    "/download/": TIPO_FASTBOOT,
    "/downloadzip/": TIPO_ZIP,
    "/downloadfile/": TIPO_ARCHIVO,
}

_REGIONES = {
    "global": "Global",
    "eu": "Europa",
    "eea": "Europa",
    "china": "China",
    "cn": "China",
    "india": "India",
    "russia": "Rusia",
    "indonesia": "Indonesia",
    "turkey": "Turquía",
    "taiwan": "Taiwán",
}


class ErrorDeRed(RuntimeError):
    """Fallo al hablar con mifirm.net, ya traducido al español."""


@dataclass
class FirmwareRemoto:
    version: str = ""
    android: str = ""
    tamano: str = ""
    fecha: str = ""
    descargas: str = ""
    url: str = ""
    tipo: str = TIPO_FASTBOOT
    canal: str = ""
    region: str = ""
    nombre_archivo: str = ""

    @property
    def recomendado_para_brom(self) -> bool:
        """Para rescatar por BROM hace falta una ROM de fastboot, no un ZIP.

        Los ZIP son actualizaciones que se instalan desde el propio Android:
        no sirven de nada si el móvil no arranca.
        """
        return self.tipo in (TIPO_FASTBOOT, TIPO_ARCHIVO)

    def descripcion(self) -> str:
        partes = [self.version or self.nombre_archivo or "sin versión"]
        if self.android:
            partes.append(f"Android {self.android}")
        if self.region:
            partes.append(self.region)
        if self.canal:
            partes.append(self.canal)
        if self.tamano:
            partes.append(self.tamano)
        return " · ".join(partes)


def _limpiar_url(href: str) -> str:
    href = (href or "").strip()
    if not href:
        return ""
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return BASE_URL + href
    return href


def _clasificar_encabezado(texto: str) -> tuple[str, str, str]:
    """De 'Mi A2 LiteFastbootStableGlobal' saca (tipo, canal, región).

    Los encabezados vienen sin espacios entre las palabras porque la web las
    reparte en varios <span>, así que se busca por subcadenas.
    """
    minusculas = texto.lower()

    if "fastboot" in minusculas:
        tipo = TIPO_FASTBOOT
    elif "zip" in minusculas:
        tipo = TIPO_ZIP
    else:
        tipo = TIPO_ARCHIVO

    if "developer" in minusculas or "weekly" in minusculas:
        canal = "Beta"
    elif "stable" in minusculas:
        canal = "Estable"
    else:
        canal = ""

    region = ""
    for clave, nombre in _REGIONES.items():
        if re.search(rf"\b{clave}\b|{clave}", minusculas):
            region = nombre
            break

    return tipo, canal, region


def _tipo_por_url(url: str, por_defecto: str) -> str:
    for fragmento, tipo in _TIPOS_POR_RUTA.items():
        if fragmento in url:
            return tipo
    return por_defecto


def _parsear_tabla(tabla, tipo: str, canal: str, region: str) -> list[FirmwareRemoto]:
    encabezados = [th.get_text(strip=True).lower() for th in tabla.find_all("th")]
    # La tabla de «Files» tiene otras columnas: empieza por el nombre del
    # archivo en vez de por la versión de MIUI.
    es_tabla_de_archivos = bool(encabezados) and "file name" in encabezados[0]

    resultados: list[FirmwareRemoto] = []
    for fila in tabla.find_all("tr"):
        celdas = fila.find_all("td")
        if len(celdas) < 5:
            continue
        enlace = fila.find("a", href=True)
        if not enlace:
            continue
        url = _limpiar_url(enlace["href"])
        if not url:
            continue

        textos = [celda.get_text(strip=True) for celda in celdas]
        if es_tabla_de_archivos:
            # Nombre, autor, tipo, tamaño, fecha, descargas, [descarga]
            firmware = FirmwareRemoto(
                nombre_archivo=textos[0],
                version=textos[2] if len(textos) > 2 else "",
                tamano=textos[3] if len(textos) > 3 else "",
                fecha=textos[4] if len(textos) > 4 else "",
                descargas=textos[5] if len(textos) > 5 else "",
            )
        else:
            # Versión MIUI, Android, tamaño, fecha, descargas, [descarga]
            firmware = FirmwareRemoto(
                version=textos[0],
                android=textos[1] if len(textos) > 1 else "",
                tamano=textos[2] if len(textos) > 2 else "",
                fecha=textos[3] if len(textos) > 3 else "",
                descargas=textos[4] if len(textos) > 4 else "",
            )
        firmware.url = url
        firmware.tipo = _tipo_por_url(url, tipo)
        firmware.canal = canal
        firmware.region = region
        resultados.append(firmware)
    return resultados


def buscar_firmwares(codename: str, solo_utiles: bool = False) -> list[FirmwareRemoto]:
    """Lista los firmwares publicados para un nombre en clave.

    `solo_utiles` deja fuera los ZIP de actualización, que no sirven cuando el
    móvil no arranca.
    """
    codename = (codename or "").strip().lower()
    if not codename:
        return []

    url = f"{BASE_URL}/model/{codename}.ttt"
    try:
        respuesta = requests.get(url, headers=CABECERAS, timeout=TIMEOUT)
    except requests.Timeout as exc:
        raise ErrorDeRed(
            "mifirm.net tardó demasiado en responder. Comprueba tu conexión "
            "e inténtalo de nuevo."
        ) from exc
    except requests.RequestException as exc:
        raise ErrorDeRed(
            "No se ha podido conectar con mifirm.net. Comprueba tu conexión a internet."
        ) from exc

    if respuesta.status_code == 404:
        raise ErrorDeRed(
            f"mifirm.net no tiene ninguna página para «{codename}». "
            "Puede que el nombre en clave no sea correcto o que ese modelo no "
            "esté en la web (solo tiene dispositivos Xiaomi)."
        )
    if respuesta.status_code != 200:
        raise ErrorDeRed(
            f"mifirm.net respondió con un error {respuesta.status_code}. "
            "Prueba otra vez dentro de un rato."
        )

    sopa = BeautifulSoup(respuesta.text, "html.parser")
    resultados: list[FirmwareRemoto] = []
    for tabla in sopa.find_all("table"):
        encabezado = tabla.find_previous(["h1", "h2", "h3", "h4", "h5"])
        texto_encabezado = encabezado.get_text(strip=True) if encabezado else ""
        tipo, canal, region = _clasificar_encabezado(texto_encabezado)
        resultados.extend(_parsear_tabla(tabla, tipo, canal, region))

    if solo_utiles:
        resultados = [f for f in resultados if f.recomendado_para_brom]
    return resultados


def detalles(url_pagina: str) -> dict[str, str]:
    """Lee la ficha de un firmware (nombre de archivo, modelo, MD5, tamaño).

    Sirve para enseñarle al usuario qué va a descargar y para comprobar después
    que el archivo que eligió es el que decía ser.
    """
    try:
        respuesta = requests.get(url_pagina, headers=CABECERAS, timeout=TIMEOUT)
        respuesta.raise_for_status()
    except requests.RequestException as exc:
        raise ErrorDeRed("No se ha podido leer la ficha del firmware.") from exc

    sopa = BeautifulSoup(respuesta.text, "html.parser")
    datos: dict[str, str] = {}
    # La ficha es una rejilla de pares: un div con la etiqueta y el siguiente
    # con el valor.
    for etiqueta in sopa.find_all(class_="fw-information-title"):
        valor = etiqueta.find_next_sibling("div")
        if valor is None:
            continue
        clave = etiqueta.get_text(strip=True).lower()
        datos[clave] = valor.get_text(" ", strip=True)

    traduccion = {
        "file name": "nombre_archivo",
        "model": "codename",
        "model name": "modelo",
        "miui version": "version",
        "android version": "android",
        "file size": "tamano",
        "md5": "md5",
        "file type": "tipo",
    }
    return {nuevo: datos[viejo] for viejo, nuevo in traduccion.items() if viejo in datos}


def abrir_en_navegador(url: str) -> bool:
    """Abre la página de descarga en el navegador del usuario."""
    try:
        return webbrowser.open(url)
    except Exception:
        return False


def descargar_archivo(
    url: str,
    ruta_destino: str | Path,
    al_progresar: Callable[[float, int, int], None] | None = None,
    reanudar: bool = True,
) -> Path:
    """Descarga una URL directa a disco, reanudando si ya había parte bajada.

    `al_progresar` recibe (porcentaje, bytes_descargados, bytes_totales). Los
    firmwares pesan más de un giga, así que reanudar no es un lujo: es lo que
    evita empezar de cero cuando se corta el wifi.
    """
    destino = Path(ruta_destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    ya_descargado = destino.stat().st_size if (reanudar and destino.exists()) else 0
    cabeceras = dict(CABECERAS)
    if ya_descargado:
        cabeceras["Range"] = f"bytes={ya_descargado}-"

    try:
        with requests.get(
            url, headers=cabeceras, stream=True, timeout=(TIMEOUT, 60)
        ) as respuesta:
            if respuesta.status_code == 416:  # ya estaba entero
                return destino
            respuesta.raise_for_status()

            reanudado = respuesta.status_code == 206
            if not reanudado:
                ya_descargado = 0  # el servidor no admite reanudar: desde cero

            longitud = int(respuesta.headers.get("content-length", 0))
            total = longitud + ya_descargado if longitud else 0

            modo = "ab" if reanudado and ya_descargado else "wb"
            descargado = ya_descargado if reanudado else 0
            with open(destino, modo) as fichero:
                for trozo in respuesta.iter_content(chunk_size=1024 * 256):
                    if not trozo:
                        continue
                    fichero.write(trozo)
                    descargado += len(trozo)
                    if al_progresar:
                        porcentaje = (descargado / total * 100) if total else 0.0
                        al_progresar(porcentaje, descargado, total)
    except requests.RequestException as exc:
        raise ErrorDeRed(
            f"La descarga falló: {exc}\n\n"
            "Si el enlace venía de mifirm.net, esa web genera los enlaces con "
            "JavaScript y no se pueden descargar desde aquí. Usa el botón "
            "«Abrir en el navegador» y elige después la carpeta descargada."
        ) from exc

    return destino
