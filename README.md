# 🛠️ MtkSpanish

**Herramienta de rescate y flasheo para dispositivos MediaTek — en español**

MtkSpanish es un wizard paso a paso diseñado para usuarios hispanohablantes que necesitan recuperar o flashear un teléfono con chip MediaTek (Xiaomi, Redmi, POCO, etc.) sin tener conocimientos técnicos.

---

## ¿Para qué sirve?

- Rescatar un teléfono atascado en **modo BROM** o **Preloader**
- Flashear firmware completo desde cero
- Gestionar dispositivos en modo **ADB** o **Fastboot**
- Buscar el firmware correcto en **mifirm.net** por nombre en clave
- Todo con mensajes en **español claro**, sin tecnicismos

---

## ¿Por qué existe este proyecto?

Todas las herramientas de flasheo para MediaTek están en inglés y asumen conocimientos técnicos previos. La comunidad hispanohablante es enorme y merece una herramienta que le hable en su idioma y le lleve de la mano en el proceso.

---

## Características

- ✅ Detección automática del modo del dispositivo (ADB / Fastboot / Preloader / BROM)
- ✅ Wizard paso a paso con interfaz gráfica
- ✅ Bypass de SBC/DAA en chipsets vulnerables (vía los exploits de MTKClient) + diagnóstico en español
- ✅ Búsqueda de firmware en mifirm.net (la descarga se abre en tu navegador)
- ✅ **Copia automática del IMEI/NVRAM antes de flashear** (por si algo sale mal)
- ✅ **Verificación de integridad del firmware** (checksums md5/sha) antes de escribir
- ✅ Analiza el firmware: parsea el scatter, une imágenes partidas y avisa de las sparse
- ✅ **Herramientas avanzadas**: copia/restaura IMEI, borra bloqueo de pantalla olvidado, historial de rescates
- ✅ Sistema de actualizaciones (de la app y de MTKClient)
- ✅ Barra de progreso en tiempo real, con cancelación
- ✅ Mensajes de error explicados en español humano
- ✅ Preparación automática del sistema Linux (ModemManager, udev, etc.)
- ✅ Instalador de un comando y lanzador en el menú de aplicaciones
- ✅ Compatible con Linux (Pop!_OS, Ubuntu, Mint, Arch...)

> **Sobre el Secure Boot y las descargas, para que no haya sorpresas:**
> MTKClient trae exploits del bootrom (kamakiri, carbonara...) que **sí saltan
> SBC y DAA** en los chipsets que son vulnerables: cargan el DA sin firma y
> permiten flashear aunque el Secure Boot esté activado. La app los lanza con
> `mtk payload`, así que ese bypass ya está aquí. El límite es el hardware: en
> chipsets nuevos con el bootrom parcheado y **SLA** activado no hay exploit
> público, y ahí sí hace falta el fichero de autenticación del fabricante (o
> tirar de fastboot, si el bootloader está desbloqueado). La herramienta te
> **dice en cuál de los dos casos estás** con la comprobación de protecciones.
>
> Las descargas de mifirm.net se abren en tu navegador porque esa web genera
> los enlaces con JavaScript ofuscado; descomprimes el archivo y lo eliges en
> la pestaña «Ya lo tengo descargado».

---

## Requisitos

- Python 3.10+
- Linux (Ubuntu 22.04+ recomendado)
- [MTKClient](https://github.com/bkerler/mtkclient) — el instalador lo clona por ti
- `python3-tk`, `adb` y `fastboot` — el instalador los instala
- Cable USB **de datos** (los de solo carga no sirven)

---

## Instalación

### La forma fácil (recomendada)

```bash
git clone https://github.com/h4dsontc-hue/MtkSpanish
cd MtkSpanish
sh instalar.sh
```

`instalar.sh` instala las dependencias del sistema (detecta apt / dnf / pacman /
zypper), clona MTKClient, instala las librerías de Python y crea el comando
`rescatemtk` más el lanzador del menú de aplicaciones. Con
`sh instalar.sh --dry-run` puedes ver lo que hará sin tocar nada.

Después, abre **RescateMTK** desde el menú o ejecuta `rescatemtk` en una terminal.

### A mano

```bash
# 1. Dependencias del sistema (Debian / Ubuntu / Pop!_OS)
sudo apt install python3-tk android-tools-adb android-tools-fastboot git

# 2. MTKClient (el motor de rescate)
git clone https://github.com/bkerler/mtkclient ~/mtkclient
pip install -r ~/mtkclient/requirements.txt

# 3. RescateMTK
git clone https://github.com/h4dsontc-hue/MtkSpanish
cd MtkSpanish
pip install -r requirements.txt
python3 main.py
```

No hace falta `sudo` para lanzar la app: el primer paso del wizard pide la
contraseña de administrador una sola vez, con el diálogo gráfico del sistema,
solo para instalar las reglas udev y desactivar ModemManager.

---

## Uso

1. Conecta el teléfono al PC (apagado si está en BROM)
2. Abre **RescateMTK** desde el menú (o ejecuta `rescatemtk` / `python3 main.py`)
3. El wizard te guía paso a paso

---

## Dispositivos compatibles

Cualquier dispositivo con chip **MediaTek** que soporte MTKClient:
- Xiaomi / Redmi / POCO
- Realme
- OPPO
- Otros fabricantes con chip MTK

---

## Créditos

Este proyecto no existiría sin el trabajo de:

- **[@bkerler](https://github.com/bkerler)** — autor de [MTKClient](https://github.com/bkerler/mtkclient), el motor que hace posible la comunicación con dispositivos MediaTek en modo BROM. Todo el crédito por el bypass de Secure Boot y la comunicación de bajo nivel es suyo.
- **[mifirm.net](https://mifirm.net)** — base de datos de firmwares Xiaomi usada por el buscador de firmware.

---

## Licencia

Este proyecto está licenciado bajo **GNU General Public License v3.0** en cumplimiento con la licencia de MTKClient.

Ver [LICENSE](LICENSE) para más detalles.

---

## Contribuir

Las contribuciones son bienvenidas. Si tienes un dispositivo MTK y quieres ayudar a probar o mejorar la herramienta, abre un issue o un pull request.

---

## Aviso legal

Esta herramienta es para uso legítimo de recuperación de dispositivos propios. El autor no se responsabiliza del mal uso. Úsala bajo tu propia responsabilidad.
