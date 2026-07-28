"""Herramientas de mantenimiento que no forman parte del rescate en sí.

Son cosas legítimas que le hacen falta a alguien que quiere reparar SU móvil:

  * copia de seguridad del IMEI y la calibración de radio antes de tocar nada;
  * restaurar esa copia si algo salió mal;
  * borrar un patrón/PIN/contraseña olvidados (un reset de fábrica);
  * la guía del desbloqueo oficial del bootloader.

Lo que aquí NO hay, a propósito: saltarse el bloqueo de cuenta Google (FRP) ni
el de cuenta Xiaomi. Eso son candados antirrobo, no averías; retirarlos sin las
credenciales del dueño es lo que hace útil un móvil robado. El camino legítimo
para un dueño que olvidó su cuenta es re-loguearse o pedir la retirada oficial
al fabricante con la factura, y eso se explica en GUIA_CUENTAS.
"""

from __future__ import annotations

from pathlib import Path

from core import fastboot, mtk
from core.detector import (
    MODO_ADB,
    MODO_BROM,
    MODO_FASTBOOT,
    MODO_PRELOADER,
)

# Particiones con datos irrepetibles de cada móvil. Son justo las que el
# rescate se salta al escribir; aquí, al revés, son las que interesa respaldar.
PARTICIONES_CRITICAS = [
    "proinfo",
    "nvram",
    "nvdata",
    "nvcfg",
    "persist",
    "protect1",
    "protect2",
]

# Lo que se borra para quitar un bloqueo de pantalla olvidado. `metadata` solo
# existe en móviles con cifrado por archivo (FBE); si no está, MTKClient lo
# salta sin más.
PARTICIONES_BLOQUEO = ["userdata", "metadata"]

MODOS_BROM = (MODO_BROM, MODO_PRELOADER)


GUIA_DESBLOQUEO_BOOTLOADER = """\
Desbloquear el bootloader (Xiaomi / Redmi / POCO)

Xiaomi obliga a hacerlo desde su herramienta oficial, con una espera de entre
7 y 30 días que impone el fabricante. No hay forma legítima de saltársela.

  1.  En el móvil: Ajustes → Acerca del teléfono → toca 7 veces «Versión MIUI»
      para activar las opciones de desarrollador.
  2.  Ajustes → Ajustes adicionales → Opciones de desarrollador:
        · activa «Desbloqueo OEM»
        · activa «Depuración USB»
        · en «Estado de Mi Unlock», añade tu cuenta y el dispositivo.
  3.  En un PC con Windows, descarga «Mi Unlock» de la web oficial de Xiaomi.
  4.  Inicia sesión con la MISMA cuenta Mi que pusiste en el móvil.
  5.  Pon el móvil en modo fastboot (apagado + Volumen abajo + cable) y pulsa
      «Unlock». Si sale una espera de X días, hay que esperar y repetir.

AVISO: desbloquear el bootloader BORRA TODOS LOS DATOS del móvil y anula parte
de la garantía. Es un requisito para flashear por fastboot, pero no hace falta
para el rescate por BROM.
"""

GUIA_CUENTAS = """\
Cuenta de Google (FRP) o cuenta Mi bloqueada

Si al encender pide una cuenta Google o Xiaomi que no recuerdas, es la
protección antirrobo. Esta herramienta NO la retira, y con razón: es lo que
impide que un móvil robado se pueda usar.

Si el móvil es tuyo:

  · Cuenta Google: inicia sesión con tu cuenta y contraseña. Si no la
    recuerdas, recupérala en accounts.google.com/signin/recovery desde otro
    dispositivo. Tras cambiar la contraseña, espera 24-72 h antes de volver a
    intentarlo (Google bloquea el reset reciente a propósito).

  · Cuenta Mi: entra en account.xiaomi.com y recupera el acceso. Para quitar el
    bloqueo de activación, Xiaomi tiene un formulario oficial donde se presenta
    la factura de compra.

Comprar un móvil de segunda mano con la cuenta del anterior dueño puesta no da
derecho a retirarla: hay que pedirle a quien te lo vendió que la quite desde su
cuenta, o reclamarle. Es la única vía correcta.
"""


# ─────────────────────────── información ───────────────────────────


def modo_permite_backup(modo: str) -> bool:
    """El backup de particiones solo se puede leer por BROM/preloader.

    fastboot no tiene orden para *leer* particiones, solo para escribirlas, así
    que ahí no se puede hacer copia.
    """
    return modo in MODOS_BROM


def particiones_a_respaldar(todas: list[str] | None = None) -> list[str]:
    """De las críticas, las que este móvil tiene de verdad en su tabla GPT.

    Si no se pasa la lista de particiones se consulta al móvil (bloqueante). Se
    devuelven en el orden de PARTICIONES_CRITICAS para que el backup sea
    predecible entre distintos móviles.
    """
    if todas is None:
        todas = mtk.listar_particiones()
    disponibles = set(todas)
    return [p for p in PARTICIONES_CRITICAS if p in disponibles]


def carpeta_backup_por_defecto(codename: str = "") -> Path:
    from datetime import datetime

    nombre = codename or "movil"
    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path.home() / "Descargas" / "RescateMTK" / f"backup-{nombre}-{marca}"


def backups_en(carpeta: str | Path) -> dict[str, Path]:
    """Los `.bin` de una carpeta que corresponden a particiones críticas."""
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return {}
    encontrados: dict[str, Path] = {}
    for archivo in carpeta.glob("*.bin"):
        nombre = archivo.stem.lower()
        if nombre in PARTICIONES_CRITICAS:
            encontrados[nombre] = archivo
    return encontrados


# ─────────────────────────── operaciones ───────────────────────────


def respaldar(
    carpeta: str | Path,
    particiones: list[str],
    al_recibir_linea,
    al_progresar=None,
    al_terminar=None,
) -> mtk.SeguimientoFlash:
    """Vuelca a `carpeta` las particiones indicadas. Requiere BROM/preloader."""
    return mtk.leer_particiones(
        particiones,
        carpeta,
        al_recibir_linea=al_recibir_linea,
        al_progresar=al_progresar,
        al_terminar=al_terminar,
    )


def restaurar(
    carpeta: str | Path,
    al_recibir_linea,
    al_progresar=None,
    al_terminar=None,
) -> mtk.SeguimientoFlash | None:
    """Escribe de vuelta los `.bin` de un backup. Requiere BROM/preloader.

    Devuelve None si en la carpeta no hay ninguna partición crítica que
    restaurar (para que la UI avise en vez de lanzar una escritura vacía).
    """
    imagenes = backups_en(carpeta)
    if not imagenes:
        return None
    return mtk.escribir_particiones(
        imagenes,
        al_recibir_linea=al_recibir_linea,
        al_progresar=al_progresar,
        al_terminar=al_terminar,
    )


def borrar_bloqueo_pantalla(
    modo: str,
    al_recibir_linea,
    al_terminar=None,
):
    """Borra userdata para quitar un patrón/PIN olvidado (reset de fábrica).

    Según el modo se hace de una forma u otra. En fastboot hace falta que el
    bootloader esté desbloqueado; en BROM no. Devuelve el manejador de la
    operación, o None si desde este modo no se puede (y ya lo ha explicado por
    `al_recibir_linea`).
    """
    if modo in MODOS_BROM:
        return mtk.borrar_particiones(
            PARTICIONES_BLOQUEO,
            al_recibir_linea=al_recibir_linea,
            al_terminar=al_terminar,
        )

    if modo == MODO_FASTBOOT:
        return _borrar_bloqueo_fastboot(al_recibir_linea, al_terminar)

    if modo == MODO_ADB:
        al_recibir_linea(
            "El móvil está encendido en modo ADB. Para borrar el bloqueo hay que "
            "reiniciarlo primero a fastboot o a BROM desde el paso de detección."
        )
        return None

    al_recibir_linea("No se puede borrar el bloqueo desde este modo.")
    return None


def _borrar_bloqueo_fastboot(al_recibir_linea, al_terminar):
    """Borra userdata/metadata por fastboot, en un hilo para no bloquear la UI."""
    import threading

    from core import binarios

    handle = binarios.ProcesoEnVivo()

    def trabajar() -> None:
        desbloqueado = fastboot.bootloader_desbloqueado()
        if desbloqueado is False:
            al_recibir_linea(
                "El bootloader está bloqueado, así que fastboot no deja borrar nada. "
                "Desbloquéalo primero (mira la guía de desbloqueo) o hazlo por BROM."
            )
            if al_terminar:
                al_terminar(1)
            return

        fallos = 0
        for particion in PARTICIONES_BLOQUEO:
            if handle.cancelado:
                break
            al_recibir_linea(f"Borrando {particion}...")
            resultado = binarios.ejecutar(
                ["fastboot", "erase", particion], timeout=120
            )
            # metadata puede no existir: no cuenta como fallo.
            if resultado.ok:
                al_recibir_linea(f"{particion}: borrado")
            elif particion == "metadata":
                al_recibir_linea("metadata no existe en este móvil (normal).")
            else:
                fallos += 1
                al_recibir_linea(f"ERROR al borrar {particion}: {resultado.texto}")
        if al_terminar:
            al_terminar(-1 if handle.cancelado else (1 if fallos else 0))

    handle.hilo = threading.Thread(target=trabajar, daemon=True)
    handle.hilo.start()
    return handle
