"""Análisis de la carpeta de firmware: qué es y cómo hay que escribirla.

Esta es la parte que decide si el rescate va a salir bien, porque «una carpeta
con el firmware» puede significar cosas muy distintas:

  ROM fastboot (Xiaomi y similares)
      images/boot.img, images/super.img, flash_all.sh, android-info.txt...
      El nombre del archivo sin extensión ya es el nombre de la partición.

  ROM con scatter (herramientas tipo SP Flash Tool)
      MT6768_Android_scatter.txt + boot.img, lk.bin, preloader_xxx.bin...
      El scatter dice qué archivo va a qué dirección de memoria.

  Carpeta suelta de particiones
      Lo que produce un volcado con `mtk rl`: boot.bin, system.bin...

Las tres acaban en el mismo sitio: un diccionario {partición: archivo}. Lo que
cambia es cómo se llega hasta él y qué avisos hay que darle al usuario.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

TIPO_FASTBOOT = "fastboot"
TIPO_SCATTER = "scatter"
TIPO_PARTICIONES = "particiones"
TIPO_DESCONOCIDO = "desconocido"

NOMBRES_TIPO = {
    TIPO_FASTBOOT: "ROM de fastboot",
    TIPO_SCATTER: "ROM con archivo scatter (MediaTek)",
    TIPO_PARTICIONES: "Carpeta de particiones sueltas",
    TIPO_DESCONOCIDO: "No reconocido",
}

EXTENSIONES_IMAGEN = {".img", ".bin", ".mbn", ".mem", ".fv"}

# Archivos que están en la carpeta pero no son particiones. Sin esta lista,
# `mtk wl` intentaría escribir el checksum o el script de instalación.
NO_SON_PARTICIONES = {
    "android-info", "flash_all", "flash_all_lock", "flash_all_except_data_storage",
    "flash_all_except_storage", "md5sum", "readme", "checksum", "sha1sum",
    "cust", "flashall", "windows", "linux",
}

# Sin estas particiones el móvil no arranca; si faltan, el firmware está incompleto.
ESENCIALES = {"boot", "lk", "preloader", "super", "system", "vbmeta"}

# Guardan datos únicos de cada móvil (IMEI, calibración de radio, claves). Un
# firmware genérico las trae con valores de fábrica: escribirlas deja el móvil
# sin cobertura y eso no se arregla volviendo a flashear.
PELIGROSAS = {
    "nvram", "nvdata", "nvcfg", "persist", "protect1", "protect2",
    "proinfo", "seccfg", "efuse", "frp",
}


@dataclass
class Firmware:
    ruta: Path
    tipo: str = TIPO_DESCONOCIDO
    imagenes: dict[str, Path] = field(default_factory=dict)
    codename: str = ""
    version: str = ""
    scatter: Path | None = None
    avisos: list[str] = field(default_factory=list)
    problemas: list[str] = field(default_factory=list)

    @property
    def valido(self) -> bool:
        return bool(self.imagenes) and not self.problemas

    @property
    def nombre_tipo(self) -> str:
        return NOMBRES_TIPO.get(self.tipo, self.tipo)

    @property
    def tamano_total(self) -> int:
        return sum(ruta.stat().st_size for ruta in self.imagenes.values() if ruta.is_file())

    def imagenes_seguras(self) -> dict[str, Path]:
        """Las imágenes quitando las que guardan datos únicos del móvil."""
        return {n: r for n, r in self.imagenes.items() if n not in PELIGROSAS}

    def resumen(self) -> str:
        lineas = [
            f"Tipo: {self.nombre_tipo}",
            f"Particiones encontradas: {len(self.imagenes)}",
            f"Tamaño total: {formatear_tamano(self.tamano_total)}",
        ]
        if self.codename:
            lineas.append(f"Modelo al que pertenece: {self.codename}")
        if self.version:
            lineas.append(f"Versión: {self.version}")
        return "\n".join(lineas)


def formatear_tamano(bytes_: int) -> str:
    unidades = ["B", "KB", "MB", "GB", "TB"]
    valor = float(bytes_)
    for unidad in unidades:
        if valor < 1024 or unidad == unidades[-1]:
            return f"{valor:.1f} {unidad}".replace(".0 ", " ")
        valor /= 1024
    return f"{valor:.1f} TB"


def _nombre_de_particion(archivo: Path) -> str | None:
    """Deduce el nombre de la partición a partir del nombre del archivo."""
    nombre = archivo.stem.lower()
    if nombre in NO_SON_PARTICIONES:
        return None
    if archivo.suffix.lower() not in EXTENSIONES_IMAGEN:
        return None
    # preloader_daisy.bin, preloader_k62v1.bin... todos son «preloader».
    if nombre.startswith("preloader"):
        return "preloader"
    # super.img.0, super.img.1 -> partes de una imagen partida, no valen sueltas.
    if re.search(r"\.\d+$", archivo.name):
        return None
    return nombre


def _buscar_imagenes(carpeta: Path) -> dict[str, Path]:
    imagenes: dict[str, Path] = {}
    for archivo in sorted(carpeta.rglob("*")):
        if not archivo.is_file():
            continue
        particion = _nombre_de_particion(archivo)
        if particion and particion not in imagenes:
            imagenes[particion] = archivo
    return imagenes


def _leer_android_info(carpeta: Path) -> tuple[str, str]:
    """Saca (codename, versión) del android-info.txt de las ROM fastboot."""
    for candidato in carpeta.rglob("android-info.txt"):
        try:
            texto = candidato.read_text(errors="replace")
        except OSError:
            continue
        codename = ""
        version = ""
        coincidencia = re.search(r"require\s+board\s*=\s*(\S+)", texto, re.I)
        if coincidencia:
            codename = coincidencia.group(1).strip()
        coincidencia = re.search(r"require\s+version-baseband\s*=\s*(\S+)", texto, re.I)
        if coincidencia:
            version = coincidencia.group(1).strip()
        return codename, version
    return "", ""


def _codename_del_nombre(carpeta: Path) -> str:
    """Las ROM de Xiaomi vienen en carpetas tipo `daisy_global_images_V11.0.5.0_...`."""
    coincidencia = re.match(r"^([a-z0-9]+)_", carpeta.name.lower())
    return coincidencia.group(1) if coincidencia else ""


def _version_del_nombre(carpeta: Path) -> str:
    coincidencia = re.search(r"(V\d+(?:\.\d+)+[A-Z0-9.]*)", carpeta.name)
    return coincidencia.group(1) if coincidencia else ""


def analizar(ruta: str | Path) -> Firmware:
    """Mira una carpeta de firmware y decide qué es y si sirve."""
    carpeta = Path(ruta).expanduser()
    firmware = Firmware(ruta=carpeta)

    if not carpeta.exists():
        firmware.problemas.append("La carpeta indicada no existe.")
        return firmware
    if carpeta.is_file():
        if carpeta.suffix.lower() == ".zip":
            firmware.problemas.append(
                "Esto es un archivo ZIP. Descomprímelo primero y elige la carpeta resultante."
            )
        else:
            firmware.problemas.append("Hay que elegir una carpeta, no un archivo suelto.")
        return firmware

    scatters = list(carpeta.rglob("*scatter*.txt"))
    tiene_flash_all = any(carpeta.rglob("flash_all*.sh")) or any(carpeta.rglob("flash_all*.bat"))
    tiene_images = any(d.is_dir() and d.name == "images" for d in carpeta.rglob("images"))

    if scatters:
        firmware.tipo = TIPO_SCATTER
        firmware.scatter = scatters[0]
    elif tiene_flash_all or tiene_images:
        firmware.tipo = TIPO_FASTBOOT
    else:
        firmware.tipo = TIPO_PARTICIONES

    firmware.imagenes = _buscar_imagenes(carpeta)

    codename, version = _leer_android_info(carpeta)
    firmware.codename = codename or _codename_del_nombre(carpeta)
    firmware.version = version or _version_del_nombre(carpeta)

    if not firmware.imagenes:
        firmware.problemas.append(
            "No se ha encontrado ninguna imagen de partición (.img o .bin) en esa carpeta. "
            "Comprueba que has elegido la carpeta correcta y que el firmware está "
            "descomprimido del todo."
        )
        return firmware

    faltan = ESENCIALES - set(firmware.imagenes)
    if "boot" in faltan:
        firmware.problemas.append(
            "Falta la imagen de arranque (boot.img). Sin ella el móvil no arrancará "
            "aunque se escriba todo lo demás."
        )
    elif faltan == ESENCIALES - {"boot"}:
        firmware.avisos.append(
            "Este firmware solo trae la partición de arranque. Sirve para reparar un "
            "arranque roto, pero no para reinstalar el sistema entero."
        )

    peligrosas_presentes = sorted(set(firmware.imagenes) & PELIGROSAS)
    if peligrosas_presentes:
        firmware.avisos.append(
            f"El firmware incluye particiones delicadas ({', '.join(peligrosas_presentes)}). "
            "Se van a saltar: contienen el IMEI y la calibración de radio de tu móvil "
            "y sobrescribirlas te dejaría sin cobertura."
        )

    partidas = [a for a in carpeta.rglob("*.img.*") if re.search(r"\.img\.\d+$", a.name)]
    if partidas:
        firmware.avisos.append(
            f"Hay {len(partidas)} archivos de imagen partidos en trozos "
            "(super.img.0, super.img.1...). Esta herramienta no los sabe unir, "
            "así que esas particiones se quedarán sin escribir."
        )

    return firmware


def comprobar_compatibilidad(firmware: Firmware, codename_dispositivo: str) -> tuple[bool, str]:
    """¿Este firmware es de este móvil?

    Devuelve (es_compatible, explicación). Cuando no hay datos suficientes para
    decidirlo devuelve True con un aviso: bloquear el rescate por no poder leer
    el codename de un móvil que ni siquiera arranca sería absurdo.
    """
    esperado = (codename_dispositivo or "").strip().lower()
    encontrado = (firmware.codename or "").strip().lower()

    if not esperado:
        return True, (
            "No se ha podido leer el modelo del móvil (normal si está en modo BROM). "
            "Asegúrate tú de que el firmware es exactamente el de tu modelo."
        )
    if not encontrado:
        return True, (
            f"El firmware no dice a qué modelo pertenece. Tu móvil es «{esperado}»: "
            "comprueba en la web de donde lo descargaste que coincide."
        )
    if esperado == encontrado:
        return True, f"El firmware coincide con tu móvil ({esperado})."
    return False, (
        f"Este firmware es para «{encontrado}» y tu móvil es «{esperado}».\n\n"
        "Flashear el firmware de otro modelo puede dejar el móvil inservible de forma "
        "permanente. Descarga el que corresponde a tu modelo exacto."
    )


def listar_zip(ruta_zip: str | Path) -> list[str]:
    """Contenido de un ZIP de firmware, para enseñarlo antes de descomprimir."""
    try:
        with zipfile.ZipFile(ruta_zip) as archivo:
            return archivo.namelist()
    except (zipfile.BadZipFile, OSError):
        return []


def descomprimir(ruta_zip: str | Path, destino: str | Path, al_progresar=None) -> Path:
    """Descomprime un firmware informando del progreso.

    Se descomprime entrada a entrada en vez de con `extractall` para poder ir
    contando: un firmware son varios gigas y sin barra de progreso parece
    que la aplicación se ha colgado.
    """
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ruta_zip) as archivo:
        entradas = archivo.infolist()
        total = sum(e.file_size for e in entradas) or 1
        hecho = 0
        for entrada in entradas:
            # Un ZIP puede traer rutas como ../../etc/passwd. Python 3.6.2+ ya
            # sanea en extract(), pero más vale comprobarlo aquí también.
            nombre = Path(entrada.filename)
            if nombre.is_absolute() or ".." in nombre.parts:
                continue
            archivo.extract(entrada, destino)
            hecho += entrada.file_size
            if al_progresar:
                al_progresar(hecho / total * 100)
    return destino
