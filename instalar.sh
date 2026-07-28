#!/bin/sh
# Instalador de RescateMTK. Deja la app lista para usar desde el menú de
# aplicaciones, sin que el usuario tenga que saber de git ni de pip.
#
#   sh instalar.sh              instala de verdad
#   sh instalar.sh --dry-run    enseña lo que haría, sin tocar nada
#
# Todo lo de Python va a un entorno virtual propio (.venv) por dos motivos:
#   - las distros modernas (PEP 668) no dejan instalar con pip en el sistema;
#   - así no se pisan versiones con otros programas.
# El venv se crea con --system-site-packages para ver el tkinter del sistema,
# que NO se instala con pip (viene en python3-tk).

set -eu

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ] || [ "${1:-}" = "-n" ]; then
    DRY_RUN=1
fi

DIR_APP=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DIR_MTKCLIENT="$HOME/mtkclient"
VENV="$DIR_APP/.venv"
PY_VENV="$VENV/bin/python3"
PIP_VENV="$VENV/bin/pip"
BIN_LOCAL="$HOME/.local/bin"
LANZADOR="$BIN_LOCAL/rescatemtk"
DESKTOP="$HOME/.local/share/applications/rescatemtk.desktop"

azul()  { printf '\033[1;34m%s\033[0m\n' "$1"; }
verde() { printf '\033[1;32m%s\033[0m\n' "$1"; }
rojo()  { printf '\033[1;31m%s\033[0m\n' "$1"; }

ejecutar() {
    if [ "$DRY_RUN" = "1" ]; then
        printf '   [dry-run] %s\n' "$*"
    else
        "$@"
    fi
}

# ─────────────────────── 1. dependencias del sistema ───────────────────────

detectar_gestor() {
    for gestor in apt-get dnf pacman zypper; do
        if command -v "$gestor" >/dev/null 2>&1; then
            echo "$gestor"
            return 0
        fi
    done
    return 1
}

instalar_deps_sistema() {
    azul "[1/6] Dependencias del sistema"
    gestor=$(detectar_gestor || true)
    if [ -z "${gestor:-}" ]; then
        rojo "   No reconozco tu gestor de paquetes."
        echo  "   Instala a mano: tkinter y venv de Python, adb, fastboot, git y libusb."
        return 0
    fi

    # libusb hace falta para que MTKClient (pyusb) pueda hablar por USB.
    case "$gestor" in
        apt-get)
            ejecutar sudo apt-get update
            ejecutar sudo apt-get install -y python3-tk python3-venv python3-pip \
                android-tools-adb android-tools-fastboot git libusb-1.0-0
            ;;
        dnf)
            ejecutar sudo dnf install -y python3-tkinter python3-pip android-tools \
                git libusbx
            ;;
        pacman)
            ejecutar sudo pacman -S --needed --noconfirm tk python-pip android-tools \
                git libusb
            ;;
        zypper)
            ejecutar sudo zypper install -y python3-tk python3-pip android-tools \
                git libusb-1_0-0
            ;;
    esac
    verde "   Dependencias del sistema listas."
}

# ─────────────────────── 2. entorno virtual ───────────────────────

crear_entorno_virtual() {
    azul "[2/6] Entorno virtual de Python"
    if [ -d "$VENV" ]; then
        verde "   Ya existe en $VENV."
    else
        # --system-site-packages para ver el tkinter del sistema (python3-tk),
        # que no se puede instalar con pip.
        ejecutar python3 -m venv --system-site-packages "$VENV"
    fi
    ejecutar "$PIP_VENV" install --upgrade pip
    verde "   Entorno virtual listo."
}

# ─────────────────────── 3. MTKClient ───────────────────────

instalar_mtkclient() {
    azul "[3/6] MTKClient"
    if [ -f "$DIR_MTKCLIENT/mtk.py" ]; then
        verde "   Ya está en $DIR_MTKCLIENT."
    else
        ejecutar git clone https://github.com/bkerler/mtkclient "$DIR_MTKCLIENT"
    fi
    if [ -f "$DIR_MTKCLIENT/requirements.txt" ] || [ "$DRY_RUN" = "1" ]; then
        ejecutar "$PIP_VENV" install -r "$DIR_MTKCLIENT/requirements.txt"
    fi
    verde "   MTKClient listo."
}

# ─────────────────────── 4. dependencias de la app ───────────────────────

instalar_deps_app() {
    azul "[4/6] Dependencias de RescateMTK"
    ejecutar "$PIP_VENV" install -r "$DIR_APP/requirements.txt"
    verde "   Listas."
}

# ─────────────────────── 5. comando rescatemtk ───────────────────────

crear_lanzador() {
    azul "[5/6] Comando «rescatemtk»"
    ejecutar mkdir -p "$BIN_LOCAL"
    if [ "$DRY_RUN" = "1" ]; then
        printf '   [dry-run] crear %s (usa %s)\n' "$LANZADOR" "$PY_VENV"
    else
        cat > "$LANZADOR" <<FIN
#!/bin/sh
exec "$PY_VENV" "$DIR_APP/main.py" "\$@"
FIN
        chmod +x "$LANZADOR"
    fi
    verde "   Creado $LANZADOR"

    case ":$PATH:" in
        *":$BIN_LOCAL:"*) : ;;
        *) echo "   Aviso: $BIN_LOCAL no está en tu PATH. Añádelo a ~/.profile:"
           echo "          export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
    esac
}

# ─────────────────────── 6. lanzador del menú ───────────────────────

crear_desktop() {
    azul "[6/6] Lanzador del menú de aplicaciones"
    ejecutar mkdir -p "$(dirname "$DESKTOP")"

    icono="utilities-terminal"
    if [ -f "$DIR_APP/assets/logo.png" ]; then
        icono="$DIR_APP/assets/logo.png"
    fi

    if [ "$DRY_RUN" = "1" ]; then
        printf '   [dry-run] crear %s (icono: %s)\n' "$DESKTOP" "$icono"
    else
        cat > "$DESKTOP" <<FIN
[Desktop Entry]
Type=Application
Name=RescateMTK
GenericName=Rescate de móviles MediaTek
Comment=Recupera móviles MediaTek que no arrancan
Exec=$LANZADOR
Icon=$icono
Terminal=false
Categories=System;
Keywords=mediatek;mtk;flash;brom;xiaomi;
FIN
        update-desktop-database "$(dirname "$DESKTOP")" >/dev/null 2>&1 || true
    fi
    verde "   Creado $DESKTOP"
}

# ─────────────────────── principal ───────────────────────

main() {
    azul "================================================"
    azul " Instalador de RescateMTK"
    [ "$DRY_RUN" = "1" ] && rojo " (modo dry-run: no se cambia nada)"
    azul "================================================"

    instalar_deps_sistema
    crear_entorno_virtual
    instalar_mtkclient
    instalar_deps_app
    crear_lanzador
    crear_desktop

    echo
    verde "¡Listo! Abre «RescateMTK» desde el menú de aplicaciones,"
    verde "o ejecuta «rescatemtk» en una terminal."
}

main
