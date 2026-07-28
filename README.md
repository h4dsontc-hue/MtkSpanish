# 🛠️ MtkSpanish

**Herramienta de rescate y flasheo para dispositivos MediaTek — en español**

MtkSpanish es un wizard paso a paso diseñado para usuarios hispanohablantes que necesitan recuperar o flashear un teléfono con chip MediaTek (Xiaomi, Redmi, POCO, etc.) sin tener conocimientos técnicos.

---

## ¿Para qué sirve?

- Rescatar un teléfono atascado en **modo BROM** o **Preloader**
- Flashear firmware completo desde cero
- Gestionar dispositivos en modo **ADB** o **Fastboot**
- Descargar el firmware correcto automáticamente desde **mifirm.net**
- Todo con mensajes en **español claro**, sin tecnicismos

---

## ¿Por qué existe este proyecto?

Todas las herramientas de flasheo para MediaTek están en inglés y asumen conocimientos técnicos previos. La comunidad hispanohablante es enorme y merece una herramienta que le hable en su idioma y le lleve de la mano en el proceso.

---

## Características

- ✅ Detección automática del modo del dispositivo (ADB / Fastboot / BROM)
- ✅ Wizard paso a paso con interfaz gráfica
- ✅ Bypass automático de SBC/SLA/DAA (Secure Boot MediaTek)
- ✅ Búsqueda y descarga de firmware desde mifirm.net
- ✅ Barra de progreso en tiempo real
- ✅ Mensajes de error explicados en español humano
- ✅ Preparación automática del sistema Linux (ModemManager, udev, etc.)
- ✅ Compatible con Linux (Pop!_OS, Ubuntu, Mint, Arch...)

---

## Requisitos

- Python 3.10+
- Linux (Ubuntu 22.04+ recomendado)
- [MTKClient](https://github.com/bkerler/mtkclient) instalado
- `adb` y `fastboot` instalados (`sudo apt install adb fastboot`)
- Cable USB de calidad

---

## Instalación

```bash
git clone https://github.com/h4dsontc-hue/MtkSpanish
cd MtkSpanish
pip install -r requirements.txt
sudo python3 main.py
```

---

## Uso

1. Conecta el teléfono al PC (apagado si está en BROM)
2. Ejecuta `sudo python3 main.py`
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
- **[mifirm.net](https://mifirm.net)** — base de datos de firmwares Xiaomi usada para las descargas automáticas.

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
