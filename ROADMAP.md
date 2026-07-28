# 🗺️ ROADMAP — MtkSpanish

---

## v1.0 — Base funcional ✅

- [x] Detector automático ADB / Fastboot / BROM *(y Preloader, que se distingue
      de BROM por el PID USB y se rescata distinto)*
- [x] Wrapper MTKClient (payload + flash completo + particiones sueltas)
- [x] Wrapper ADB y Fastboot
- [x] UI wizard paso a paso con CustomTkinter
- [x] Preparación automática del sistema Linux *(un solo script con `pkexec`:
      una petición de contraseña, no siete)*
- [x] Mensajes de error en español humano
- [x] README + CONTEXT.md + ROADMAP.md
- [x] Licencia GPLv3
- [x] Suite de tests (122, sin necesidad de móvil ni de pantalla)
- [~] Scraper mifirm.net — **búsqueda sí, descarga no.** El listado se lee
      bien (versión, Android, región, canal, tamaño), pero mifirm.net genera
      los enlaces de descarga con JavaScript ofuscado. La descarga se abre en
      el navegador del usuario. Ver *Pendiente de decidir* al final.

---

## v1.1 — Información y seguridad

- [~] Lector de información del dispositivo — modelo, codename, chipset,
      Android y número de serie ya se leen por ADB/fastboot. **Falta el IMEI**
      y el firmware actual cuando el móvil está en BROM.
- [x] Backup y restauración de particiones críticas (nvram, nvdata, nvcfg,
      persist, proinfo, protect1/2) — en «Herramientas avanzadas». Devuelve el
      IMEI si algo sale mal. Solo por BROM (fastboot no sabe leer). **Falta**
      ofrecerlo automáticamente antes de cada flasheo. **Hecho:** el paso de
      flasheo ofrece la copia (marcada por defecto) y respalda antes de escribir.
- [~] Validación del firmware antes de flashear — se comprueba el tipo de ROM,
      las particiones esenciales, que el codename coincida, **se parsea el
      scatter de verdad** (partición→archivo según el fabricante, respetando
      `is_download`), se **unen las imágenes partidas en crudo** y se **avisa de
      las imágenes sparse** (que MTKClient escribe mal). **Falta** convertir las
      sparse con simg2img y verificar checksums.
- [x] Historial de dispositivos flasheados con fecha y firmware usado *(JSON en
      la carpeta de datos del usuario; se registra solo al terminar cada rescate
      y se consulta en «Herramientas → Ver historial»)*
- [ ] Detector de cable USB malo (uno de los problemas más comunes)

---

## v1.2 — Control avanzado

- [ ] Flashear partición individual (boot, recovery, vbmeta, etc.)
- [x] Desbloqueo de bootloader guiado paso a paso *(guía del método oficial de
      Xiaomi en «Herramientas avanzadas»; el desbloqueo real lo hace Mi Unlock,
      no se puede saltar la espera)*
- [ ] Rebloqueo de bootloader
- [x] Borrar bloqueo de pantalla olvidado (patrón/PIN) — reset de fábrica desde
      «Herramientas avanzadas», por BROM o fastboot. **No** es bypass de cuenta.
- [ ] Modo básico / modo avanzado (el novato ve 3 botones, el avanzado ve todo)
- [x] Log exportable a fichero .txt para pedir ayuda en foros *(adelantado a
      v1.0: el paso 5 lo guarda con cabecera de móvil, modo y firmware)*

---

## v1.3 — Usuario novato

- [ ] Guía visual de cómo entrar en modo BROM según el modelo (imágenes/GIF)
- [ ] Base de datos de codenames Xiaomi incluida offline
- [ ] Identificación automática del modelo sin conexión a internet
- [ ] Sugerencia automática del firmware recomendado para cada modelo

---

## v1.4 — Herramientas extra

- [x] Restaurar el IMEI desde una copia propia *(hecho en v1.1: respaldar y
      restaurar nvram/nvdata. Restaurar TU copia es legítimo; escribir un IMEI
      arbitrario es delito en muchos países y por eso no se hace)*
- [x] Guía legítima para cuentas Google (FRP) y Mi bloqueadas *(en
      «Herramientas avanzadas»: cómo recuperarlas oficialmente. Ver abajo el
      porqué de NO automatizar el bypass)*
- [ ] Notificación cuando sale firmware nuevo para tu dispositivo
- [ ] Sistema de plugins para añadir soporte a otras marcas MTK (Realme, OPPO, etc.)

> **Por qué el bypass de FRP y de cuenta Mi no está ni estará.** Son candados
> antirrobo, no averías: existen para que un móvil robado no sirva sin las
> credenciales del dueño. Una herramienta con interfaz que lo hace en cualquier
> móvil no puede comprobar de quién es cada uno, así que en la práctica sería la
> herramienta que blanquea móviles robados — y distribuir eso tiene consecuencias
> legales en muchos países. Para un dueño legítimo que olvidó su cuenta, el
> camino es re-loguearse o la retirada oficial del fabricante con la factura, y
> eso sí está documentado dentro de la app.

---

## v2.0 — Multiplataforma

- [x] Instalador de un comando (`instalar.sh`) — instala dependencias del
      sistema (detecta apt/dnf/pacman/zypper), clona MTKClient, instala las
      libs de Python y crea el comando `rescatemtk` + lanzador en el menú. Con
      `--dry-run`. Desinstalador aparte. Es el 80% del valor de un AppImage sin
      su complejidad; verificado con gestor simulado y HOME temporal.
- [ ] AppImage universal para cualquier distro Linux sin instalar nada
- [ ] Instalador .deb para Ubuntu/Debian/Pop!_OS
- [ ] Instalador .rpm para Fedora/openSUSE
- [ ] Soporte Windows (nativo, sin WSL)

---

## v2.1 — Comunidad

- [ ] Sistema de traducciones (inglés, portugués, francés)
- [ ] Web de documentación en español
- [ ] Canal de Telegram para soporte
- [ ] Sistema de reporte de dispositivos compatibles por la comunidad

---

## Pendiente de decidir

Cosas que no son «hacer o no hacer» sino «decidir cómo»:

**Descargas de mifirm.net.** Los enlaces los genera JavaScript ofuscado en la
página. Tres caminos, de menos a más frágil:

1. *Como está ahora*: se abre el navegador. Nunca se rompe, pero el usuario
   tiene que salir de la app.
2. Empotrar un navegador (`pywebview` / `QtWebEngine`) y capturar la descarga.
   Funciona sin salir de la app, a costa de una dependencia pesada.
3. Reimplementar el descifrado del enlace. Se rompe cada vez que toquen el
   script de la web, y salta el sistema con el que se financia el sitio.

Mi voto es quedarse en 1 y ofrecer 2 si la gente lo pide.

**Escritura de IMEI (v1.4).** En muchos países reescribir el IMEI es delito,
no solo «legalmente dudoso». Antes de escribir una línea de eso conviene
decidir si el proyecto quiere esa responsabilidad encima: leer el IMEI y
restaurar un backup propio es una cosa, escribir uno arbitrario es otra muy
distinta. Sugiero limitar la función a restaurar el backup que la propia
herramienta hizo en v1.1.

**Soporte Windows (v2.0).** El grueso del trabajo no es la UI (CustomTkinter
ya es multiplataforma) sino que `utils/sistema.py` es Linux puro: udev,
ModemManager y `pkexec` no existen ahí. En Windows el equivalente es instalar
los drivers de MediaTek con `libusb-win32`/Zadig, que no se puede automatizar
igual de limpio.
