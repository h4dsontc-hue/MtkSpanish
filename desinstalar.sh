#!/bin/sh
# Desinstala RescateMTK: quita el comando y el lanzador del menú.
#
# No borra la carpeta del proyecto, ni MTKClient, ni las dependencias de
# Python: eso lo puede querer conservar el usuario. Tampoco toca el historial
# de rescates. Solo deshace lo que puso instalar.sh en el sistema.

set -eu

LANZADOR="$HOME/.local/bin/rescatemtk"
DESKTOP="$HOME/.local/share/applications/rescatemtk.desktop"

quitar() {
    if [ -e "$1" ]; then
        rm -f "$1"
        printf 'Quitado: %s\n' "$1"
    else
        printf 'No estaba: %s\n' "$1"
    fi
}

quitar "$LANZADOR"
quitar "$DESKTOP"
update-desktop-database "$(dirname "$DESKTOP")" >/dev/null 2>&1 || true

echo
echo "Hecho. La carpeta del proyecto, MTKClient y el historial siguen intactos."
echo "Si también quieres quitarlos:  rm -rf \"$(CDPATH= cd -- \"$(dirname -- \"$0\")\" && pwd)\" ~/mtkclient"
