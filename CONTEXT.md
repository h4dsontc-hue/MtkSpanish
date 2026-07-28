# RescateMTK — CONTEXT.md

Herramienta de rescate y flasheo para dispositivos MediaTek en español.
Wizard paso a paso para usuarios sin conocimientos técnicos.

---

## Stack tecnológico

- **Python 3.10+**
- **CustomTkinter** — UI de escritorio moderna
- **MTKClient** (bkerler) — motor BROM/Preloader (GPLv3)
- **ADB + Fastboot** — comandos estándar Android
- **requests + BeautifulSoup4** — scraping mifirm.net
- **subprocess** — ejecución de comandos externos

---

## Estructura del proyecto

```
rescatemtk/
├── main.py                   # Punto de entrada
├── ui/
│   ├── wizard.py             # Ventana principal, gestiona los pasos
│   ├── paso_bienvenida.py    # Paso 0: bienvenida + preparar sistema
│   ├── paso_detectar.py      # Paso 1: detectar dispositivo
│   ├── paso_firmware.py      # Paso 2: seleccionar o descargar firmware
│   ├── paso_flash.py         # Paso 3: progreso del flash en tiempo real
│   └── paso_resultado.py     # Paso 4: resultado final
├── core/
│   ├── detector.py           # Detecta ADB / Fastboot / BROM automáticamente
│   ├── adb.py                # Wrapper comandos ADB
│   ├── fastboot.py           # Wrapper comandos Fastboot
│   └── mtk.py                # Wrapper MTKClient (subprocess)
├── scraper/
│   └── mifirm.py             # Scraping de mifirm.net por codename
├── utils/
│   ├── sistema.py            # Preparar Linux (ModemManager, udev, etc.)
│   └── validar.py            # Validar firmware (scatter file, integridad)
├── assets/
│   └── logo.png              # Logo de la app
├── requirements.txt
├── README.md
└── LICENSE                   # GPLv3
```

---

## Flujo del wizard (paso a paso)

```
[Paso 0] Bienvenida
  → Botón "Preparar sistema"
  → Ejecuta: stop ModemManager, udev rules, rmmod cdc_acm
  → Confirma que el sistema está listo

[Paso 1] Detectar dispositivo
  → Espera conexión USB
  → Detecta automáticamente: ADB / Fastboot / BROM
  → Muestra: modelo, chipset, modo, SBC/DAA si es BROM

[Paso 2] Firmware
  → Opción A: seleccionar carpeta con firmware ya descargado
  → Opción B: buscar en mifirm.net por codename detectado
      → Lista firmwares disponibles (versión, región, tamaño)
      → Descarga con barra de progreso

[Paso 3] Flash
  → Resumen de qué se va a flashear
  → Aviso de borrado de datos
  → Barra de progreso en tiempo real
  → Log con mensajes en español (errores traducidos a lenguaje humano)

[Paso 4] Resultado
  → Éxito: instrucciones de qué hacer ahora
  → Error: explicación clara de qué salió mal y cómo solucionarlo
```

---

## Módulos — detalle técnico

### core/detector.py

```python
import subprocess

def detectar_modo():
    """Detecta en qué modo está el dispositivo conectado."""
    if _check_adb():
        return "ADB"
    elif _check_fastboot():
        return "FASTBOOT"
    elif _check_brom():
        return "BROM"
    return None

def _check_adb():
    result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
    lineas = result.stdout.strip().split("\n")
    return len(lineas) > 1 and "device" in lineas[1]

def _check_fastboot():
    result = subprocess.run(["fastboot", "devices"], capture_output=True, text=True)
    return bool(result.stdout.strip())

def _check_brom():
    # Buscar USB con VID 0e8d (MediaTek)
    result = subprocess.run(["lsusb"], capture_output=True, text=True)
    return "0e8d" in result.stdout
```

---

### core/adb.py

```python
import subprocess

def reiniciar_fastboot():
    subprocess.run(["adb", "reboot", "bootloader"])

def reiniciar_recovery():
    subprocess.run(["adb", "reboot", "recovery"])

def sideload(ruta_zip):
    subprocess.run(["adb", "sideload", ruta_zip])

def obtener_info():
    """Devuelve modelo, codename, etc."""
    props = {}
    for prop in ["ro.product.model", "ro.product.device", "ro.build.version.release"]:
        r = subprocess.run(["adb", "shell", f"getprop {prop}"], capture_output=True, text=True)
        props[prop] = r.stdout.strip()
    return props
```

---

### core/fastboot.py

```python
import subprocess

def flashear_particion(particion, ruta_img):
    subprocess.run(["fastboot", "flash", particion, ruta_img])

def desbloquear_bootloader():
    subprocess.run(["fastboot", "flashing", "unlock"])

def reiniciar():
    subprocess.run(["fastboot", "reboot"])

def obtener_info():
    r = subprocess.run(["fastboot", "getvar", "product"], capture_output=True, text=True)
    return r.stderr.strip()  # fastboot imprime en stderr
```

---

### core/mtk.py

```python
import subprocess
import threading

def lanzar_payload(callback_log):
    """Ejecuta mtk payload y llama callback_log con cada línea."""
    def run():
        proceso = subprocess.Popen(
            ["python3", "mtkclient/mtk.py", "payload"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        for linea in proceso.stdout:
            callback_log(linea.strip())
    threading.Thread(target=run, daemon=True).start()

def flashear_todo(ruta_firmware, callback_log):
    """Ejecuta mtk wl con la carpeta del firmware."""
    def run():
        proceso = subprocess.Popen(
            ["python3", "mtkclient/mtk.py", "wl", ruta_firmware],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        for linea in proceso.stdout:
            callback_log(linea.strip())
    threading.Thread(target=run, daemon=True).start()
```

---

### scraper/mifirm.py

```python
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://mifirm.net"

def buscar_firmwares(codename, region="global", tipo="fastboot"):
    """
    Devuelve lista de firmwares disponibles para un codename.
    tipo: "fastboot" o "zip"
    region: "global", "eea", "cn", "in", "ru", "id", "tr"
    """
    url = f"{BASE_URL}/model/{codename}.ttt"
    try:
        r = requests.get(url, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        return []

    firmwares = []
    tablas = soup.find_all("table")
    for tabla in tablas:
        filas = tabla.find_all("tr")
        for fila in filas[1:]:
            celdas = fila.find_all("td")
            if len(celdas) >= 6:
                enlace_tag = celdas[5].find("a")
                if enlace_tag:
                    firmwares.append({
                        "version": celdas[0].text.strip(),
                        "android": celdas[1].text.strip(),
                        "tamaño": celdas[2].text.strip(),
                        "fecha": celdas[3].text.strip(),
                        "descargas": celdas[4].text.strip(),
                        "url": BASE_URL + enlace_tag["href"] if enlace_tag["href"].startswith("/") else enlace_tag["href"]
                    })
    return firmwares

def descargar_firmware(url, ruta_destino, callback_progreso=None):
    """Descarga un firmware con progreso."""
    with requests.get(url, stream=True, timeout=30) as r:
        total = int(r.headers.get("content-length", 0))
        descargado = 0
        with open(ruta_destino, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
                descargado += len(chunk)
                if callback_progreso and total:
                    callback_progreso(descargado / total * 100)
```

---

### utils/sistema.py

```python
import subprocess
import os

def preparar_sistema():
    """Ejecuta todos los pasos de preparación del sistema Linux."""
    pasos = [
        ("Deteniendo ModemManager...", ["sudo", "systemctl", "stop", "ModemManager"]),
        ("Deshabilitando ModemManager...", ["sudo", "systemctl", "disable", "ModemManager"]),
        ("Descargando módulo cdc_acm...", ["sudo", "rmmod", "cdc_acm"]),
        ("Aplicando reglas udev...", None),  # se hace aparte
        ("Recargando udev...", ["sudo", "udevadm", "control", "--reload-rules"]),
        ("Activando udev trigger...", ["sudo", "udevadm", "trigger"]),
        ("Reinstalando cdc_acm...", ["sudo", "modprobe", "cdc_acm"]),
    ]

    udev_rule = (
        'SUBSYSTEM=="usb", ATTR{idVendor}=="0e8d", MODE="0666", GROUP="plugdev"\n'
        'KERNEL=="ttyACM*", MODE="0666", GROUP="plugdev"\n'
        'KERNEL=="ttyUSB*", MODE="0666", GROUP="plugdev"\n'
    )

    resultados = []
    for mensaje, cmd in pasos:
        if cmd is None:
            # Escribir regla udev
            try:
                with open("/tmp/51-MTK-brom.rules", "w") as f:
                    f.write(udev_rule)
                subprocess.run(["sudo", "cp", "/tmp/51-MTK-brom.rules", "/etc/udev/rules.d/51-MTK-brom.rules"])
                resultados.append((mensaje, True))
            except Exception as e:
                resultados.append((mensaje, False))
        else:
            r = subprocess.run(cmd, capture_output=True)
            resultados.append((mensaje, r.returncode == 0))
    return resultados
```

---

## requirements.txt

```
customtkinter
requests
beautifulsoup4
```

---

## Orden de desarrollo recomendado

1. `git init` + repo GitHub + LICENSE GPLv3 + README básico
2. `utils/sistema.py` — preparar Linux
3. `core/detector.py` — detectar ADB / Fastboot / BROM
4. `core/adb.py` + `core/fastboot.py` — wrappers básicos
5. `core/mtk.py` — wrapper MTKClient
6. `scraper/mifirm.py` — buscar y descargar firmwares
7. UI con CustomTkinter — wizard paso a paso
8. Tests manuales con dispositivos reales
9. Compilar con PyInstaller → AppImage o .bin

---

## Licencia y créditos

- Licencia: **GPLv3** (obligatorio por uso de MTKClient)
- MTKClient: © bkerler — https://github.com/bkerler/mtkclient
- mifirm.net: fuente de firmwares Xiaomi

---

## Mensaje para bkerler (GitHub)

> Hi bkerler! I'm building a Spanish-language GUI wizard on top of MTKClient
> to help non-technical Spanish-speaking users recover devices stuck in BROM mode.
> Your tool is the backbone of the project. Full GPLv3 compliance and credit in the README.
> Just wanted to let you know and say thanks for your amazing work.

---

## Notas

- MTKClient debe estar clonado en `~/mtkclient/` o en el PATH
- La app se ejecuta con `sudo` para acceso a USB y udev
- xhost requerido en Linux para abrir ventana gráfica como root:
  `xhost +si:localuser:root`
