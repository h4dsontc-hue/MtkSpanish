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

import hashlib
import re
import shutil
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


# Magia de las imágenes Android «sparse» (0xED26FF3A, little-endian). MTKClient
# escribe en crudo, sin convertir, así que una imagen sparse escrita tal cual
# deja la partición con basura. Hay que detectarlas y avisar.
MAGIA_SPARSE = b"\x3a\xff\x26\xed"


def es_imagen_sparse(ruta: Path) -> bool:
    """¿El archivo es una imagen Android sparse (no se puede escribir en crudo)?"""
    try:
        with open(ruta, "rb") as fichero:
            return fichero.read(4) == MAGIA_SPARSE
    except OSError:
        return False


def _parsear_scatter(texto: str) -> list[dict[str, str]]:
    """Extrae de un scatter MediaTek la lista de particiones.

    El scatter es un YAML donde cada partición es un bloque que empieza por
    `- partition_index:`. De cada uno interesan tres campos: el nombre de la
    partición, el archivo que le corresponde y si está marcada para escribir
    (`is_download`). Se parsea a mano para no añadir una dependencia de YAML
    por tres campos.
    """
    entradas: list[dict[str, str]] = []
    bloque: dict[str, str] = {}

    def cerrar() -> None:
        if "partition_name" in bloque:
            entradas.append(bloque.copy())

    campo = re.compile(
        r"-?\s*(partition_name|file_name|is_download)\s*:\s*(.+?)\s*$", re.I
    )
    for linea in texto.splitlines():
        stripped = linea.strip()
        if stripped.startswith("- partition_index:") or stripped.startswith("- general:"):
            cerrar()
            bloque = {}
            continue
        coincidencia = campo.match(stripped)
        if coincidencia:
            clave = coincidencia.group(1).lower()
            valor = coincidencia.group(2).strip().strip("\"'")
            bloque[clave] = valor
    cerrar()
    return entradas


def _imagenes_del_scatter(scatter: Path, carpeta: Path) -> dict[str, Path]:
    """Mapa {partición: archivo} según lo que declara el scatter.

    Es más fiable que adivinar por el nombre del archivo: usa los nombres de
    partición del fabricante y respeta `is_download` (salta las que el propio
    scatter marca como que no se escriben).
    """
    try:
        texto = scatter.read_text(errors="replace")
    except OSError:
        return {}

    imagenes: dict[str, Path] = {}
    for entrada in _parsear_scatter(texto):
        nombre = entrada.get("partition_name", "").lower()
        fichero = entrada.get("file_name", "")
        descargable = entrada.get("is_download", "").lower() in ("true", "1")
        if not nombre or not descargable:
            continue
        if not fichero or fichero.upper() == "NONE":
            continue
        ruta = scatter.parent / fichero
        if not ruta.is_file():
            ruta = _buscar_archivo(carpeta, fichero)
            if ruta is None:
                continue
        imagenes[nombre] = ruta
    return imagenes


def _buscar_archivo(carpeta: Path, nombre: str) -> Path | None:
    """Busca un archivo por nombre, tolerando diferencias de mayúsculas.

    En las ROM reales el nombre del scatter y el del archivo suelen coincidir,
    pero no siempre en las mayúsculas (PGPT vs pgpt), y perder una partición
    por eso sería una tontería.
    """
    exactos = list(carpeta.rglob(nombre))
    if exactos:
        return exactos[0]
    objetivo = nombre.lower()
    for archivo in carpeta.rglob("*"):
        if archivo.is_file() and archivo.name.lower() == objetivo:
            return archivo
    return None


def agrupar_imagenes_partidas(carpeta: Path) -> dict[str, list[Path]]:
    """Agrupa los trozos `nombre.img.0`, `nombre.img.1`... por partición, en orden."""
    grupos: dict[str, list[Path]] = {}
    for archivo in carpeta.rglob("*"):
        coincidencia = re.match(r"(.+?)\.img\.(\d+)$", archivo.name, re.I)
        if archivo.is_file() and coincidencia:
            grupos.setdefault(coincidencia.group(1).lower(), []).append(archivo)
    for nombre, trozos in grupos.items():
        trozos.sort(key=lambda p: int(re.search(r"\.(\d+)$", p.name).group(1)))
    return grupos


def unir_imagenes_partidas(trozos: list[Path], destino: Path) -> Path:
    """Une los trozos crudos de una imagen partida en un solo archivo.

    Solo vale para trozos EN CRUDO (raw). Si son sparse hay que convertirlos
    con simg2img primero: concatenar sparse no da una imagen válida, y por eso
    `analizar` avisa antes de dejar que se llegue aquí.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "wb") as salida:
        for trozo in trozos:
            with open(trozo, "rb") as entrada:
                shutil.copyfileobj(entrada, salida)
    return destino


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

    # Con scatter, el mapa partición→archivo lo da el propio fabricante; es más
    # fiable que deducirlo del nombre de cada archivo. Si el scatter no aporta
    # nada útil, se cae a la deducción por nombre.
    firmware.imagenes = {}
    if firmware.scatter is not None:
        firmware.imagenes = _imagenes_del_scatter(firmware.scatter, carpeta)
    if not firmware.imagenes:
        firmware.imagenes = _buscar_imagenes(carpeta)

    # Unir las imágenes partidas en crudo (super.img.0 + super.img.1 + ...).
    # Las que son sparse no se pueden concatenar sin más, así que se avisa
    # (más abajo) y se dejan fuera en vez de armar una imagen corrupta.
    for nombre, trozos in agrupar_imagenes_partidas(carpeta).items():
        if nombre in firmware.imagenes:
            continue
        if any(es_imagen_sparse(t) for t in trozos):
            firmware.avisos.append(
                f"La partición «{nombre}» viene partida en {len(trozos)} trozos de "
                "formato sparse. No se pueden unir en crudo (harían falta las "
                "herramientas de Android «simg2img»), así que esa partición se queda "
                "sin escribir. Busca una versión del firmware que no venga partida."
            )
            continue
        destino = carpeta / f"{nombre}.img"
        try:
            unir_imagenes_partidas(trozos, destino)
            firmware.imagenes[nombre] = destino
            firmware.avisos.append(
                f"La partición «{nombre}» venía en {len(trozos)} trozos y se han unido "
                "automáticamente."
            )
        except OSError as exc:
            firmware.avisos.append(f"No se pudieron unir los trozos de «{nombre}»: {exc}")

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

    # Imágenes sparse enteras (no partidas): MTKClient las escribe en crudo y el
    # resultado no arranca. Aún no se convierten solas, pero avisar evita el
    # flasheo silenciosamente roto.
    sparse = sorted(
        nombre
        for nombre, ruta in firmware.imagenes.items()
        if ruta.is_file() and es_imagen_sparse(ruta)
    )
    if sparse:
        firmware.avisos.append(
            f"Estas imágenes están en formato sparse: {', '.join(sparse)}. "
            "MTKClient las escribe en crudo, así que podrían no arrancar. Si el "
            "móvil no arranca tras el flasheo, busca una versión del firmware con "
            "esas imágenes en crudo (raw)."
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


# ─────────────────────── verificación de integridad ───────────────────────
#
# Una descarga corrupta escrita en el móvil es un brick silencioso: todo parece
# ir bien y luego no arranca. Si el firmware trae checksums (md5sum.txt, o un
# .md5/.sha256 junto a cada imagen), se pueden comprobar antes de flashear.

# La longitud del hash en hex delata el algoritmo, así no hay que adivinarlo.
_ALGO_POR_LONGITUD = {32: "md5", 40: "sha1", 64: "sha256"}

_FICHEROS_CHECKSUM = {"md5sum.txt", "md5sums", "sha1sum.txt", "sha256sum.txt", "sha256sums"}
_EXT_CHECKSUM = {".md5", ".sha1", ".sha256"}


@dataclass
class ResultadoIntegridad:
    verificados: list[tuple[str, bool]] = field(default_factory=list)  # (nombre, coincide)
    sin_hash: list[str] = field(default_factory=list)

    @property
    def hay_hashes(self) -> bool:
        return bool(self.verificados)

    @property
    def todo_ok(self) -> bool:
        return all(coincide for _, coincide in self.verificados)

    @property
    def fallidos(self) -> list[str]:
        return [nombre for nombre, coincide in self.verificados if not coincide]

    def resumen(self) -> str:
        if not self.hay_hashes:
            return (
                "Este firmware no trae checksums, así que no se puede comprobar su "
                "integridad. Descárgalo de una fuente fiable."
            )
        if self.todo_ok:
            extra = ""
            if self.sin_hash:
                extra = f" ({len(self.sin_hash)} imágenes sin hash que comprobar)"
            return f"Integridad correcta: {len(self.verificados)} imágenes verificadas{extra}."
        return (
            f"¡ATENCIÓN! Estas imágenes NO coinciden con su checksum: "
            f"{', '.join(self.fallidos)}.\n"
            "La descarga está corrupta o incompleta. NO la flashees: vuelve a "
            "descargar el firmware."
        )


def hash_de_archivo(
    ruta: Path, algo: str, al_progresar=None, _bloque: int = 1024 * 1024
) -> str:
    """Calcula el hash de un archivo por trozos (las imágenes pesan gigas)."""
    digest = hashlib.new(algo)
    total = ruta.stat().st_size or 1
    leido = 0
    with open(ruta, "rb") as fichero:
        while True:
            trozo = fichero.read(_bloque)
            if not trozo:
                break
            digest.update(trozo)
            leido += len(trozo)
            if al_progresar:
                al_progresar(leido / total * 100)
    return digest.hexdigest()


def _checksums_declarados(carpeta: Path) -> dict[str, tuple[str, str]]:
    """Lee los checksums que trae el firmware: {nombre_archivo: (algo, hash)}."""
    declarados: dict[str, tuple[str, str]] = {}
    for fichero in carpeta.rglob("*"):
        if not fichero.is_file():
            continue
        nombre = fichero.name.lower()
        es_lista = nombre in _FICHEROS_CHECKSUM
        es_suelto = fichero.suffix.lower() in _EXT_CHECKSUM
        if not (es_lista or es_suelto):
            continue
        try:
            texto = fichero.read_text(errors="replace")
        except OSError:
            continue

        encontrado_en_lista = False
        for linea in texto.splitlines():
            coincidencia = re.match(r"\s*([0-9a-fA-F]{32,64})\s+\*?(.+?)\s*$", linea)
            if not coincidencia:
                continue
            hsh = coincidencia.group(1).lower()
            algo = _ALGO_POR_LONGITUD.get(len(hsh))
            if algo:
                archivo = Path(coincidencia.group(2)).name.lower()
                declarados[archivo] = (algo, hsh)
                encontrado_en_lista = True

        # Un `.md5` suelto puede contener solo el hash, para el archivo con su
        # mismo nombre base (boot.img.md5 -> boot.img).
        if es_suelto and not encontrado_en_lista:
            bruto = texto.strip().split()[0].lower() if texto.strip() else ""
            algo = _ALGO_POR_LONGITUD.get(len(bruto))
            if algo and re.fullmatch(r"[0-9a-fA-F]+", bruto):
                declarados[fichero.stem.lower()] = (algo, bruto)
    return declarados


def verificar_integridad(
    firmware: "Firmware", al_progresar=None
) -> ResultadoIntegridad:
    """Comprueba las imágenes del firmware contra los checksums que trae.

    Solo verifica las imágenes que tienen un hash declarado; el resto va a
    `sin_hash`. Si el firmware no trae ningún checksum, el resultado lo dice.
    """
    declarados = _checksums_declarados(firmware.ruta)
    resultado = ResultadoIntegridad()

    total = len(firmware.imagenes) or 1
    for indice, (particion, ruta) in enumerate(sorted(firmware.imagenes.items())):
        clave = None
        if ruta.name.lower() in declarados:
            clave = ruta.name.lower()
        elif ruta.stem.lower() in declarados:
            clave = ruta.stem.lower()

        if clave is None:
            resultado.sin_hash.append(particion)
            continue

        algo, esperado = declarados[clave]

        def progreso_archivo(p, base=indice):
            if al_progresar:
                al_progresar((base + p / 100) / total * 100)

        try:
            real = hash_de_archivo(ruta, algo, al_progresar=progreso_archivo)
        except OSError:
            resultado.verificados.append((particion, False))
            continue
        resultado.verificados.append((particion, real == esperado))
    return resultado


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
