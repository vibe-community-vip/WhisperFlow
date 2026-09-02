# WhisperFlow local

Dictado por voz **local, offline y gratis** (sin suscripción) — un reemplazo casero
de Wispr Flow. Transcribe con IA (faster-whisper) corriendo en tu propia máquina y
pega el texto donde tengas el cursor. Funciona en **Windows, macOS y Linux**.

Este proyecto es **código fuente editable a propósito**, no un instalador cerrado.
Está pensado para que lo sigas ajustando — a mano, o pidiéndole los cambios a un
agente de código como Claude Code (ver más abajo).

## Comunidad

Creado por la comunidad **[Vibe Community VIP](https://www.skool.com/vibe-community-vip)**.
Allí conseguís más información, guías, soporte y novedades sobre este y otros
proyectos.

## Atajos

- **Push-to-talk** — habla mientras sostienes las teclas; al soltar, transcribe y pega.
  - Windows/Linux: `Ctrl + Win` (Linux: `Ctrl + Super`)
  - macOS: `Cmd + Ctrl`
- **Manos libres** — sigue grabando aunque sueltes las teclas. Para detener y
  transcribir, vuelve a presionar el mismo acorde (o suma `Espacio`). Suena **un
  solo bip**, más grave que el de push-to-talk, para que sepas en qué modo estás.
  - Windows/Linux: `Ctrl + Win + Espacio`  ·  macOS: `Cmd + Ctrl + Espacio`
- **Re-pegar último** — por si no había ningún campo con foco cuando dictaste. Presionado
  varias veces seguidas sin dictar nada nuevo en medio, retrocede a las últimas 3
  grabaciones (dictar algo nuevo reinicia el ciclo). Se persiste en disco
  (`last_recordings.json`), así que sobrevive a reinicios de la app.
  - Windows/Linux: `Ctrl + Alt + Z`  ·  macOS: `Cmd + Shift + Z`

El dictado es **uno solo, sin modos**: lo que dictas es lo que se pega. (Hubo
perfiles de tono "amigable"/"profesional" que reescribían el texto con un LLM; se
quitaron para dejar la herramienta simple y predecible.)

Un indicador flotante aparece abajo al centro mientras grabas/transcribes: una
cápsula translúcida con degradado, halo de luz y un mini-ecualizador que reacciona a
tu voz.

**El micrófono queda armado desde que arranca la app.** Abrirlo en el momento de
pulsar el atajo costaba ~120 ms reales y se perdían las primeras sílabas; ahora la
grabación empieza exactamente cuando pulsas, y hasta rescata los ~350 ms previos.
El indicador de "micrófono en uso" del sistema queda encendido siempre: el audio
vive solo en un buffer en memoria que se descarta solo y nunca se escribe a disco.
Si prefieres el comportamiento anterior, `WHISPERFLOW_MIC_ALWAYS_ON=0`.

## Requisitos

- **Windows 10/11**, **macOS** o **Linux** (X11; Wayland en modo *best-effort*).
- **Python 3.11–3.13** (en Windows, 3.12). Marca "Add to PATH" al instalar.
- Opcional: GPU NVIDIA (Windows/Linux) para transcribir más rápido. Sin GPU, usa CPU
  (en ese caso conviene bajar `WHISPERFLOW_MODEL_SIZE` a `small`).

## Instalación

> **¿Es tu primera vez?** Hay una **[guía paso a paso](INSTALACION.md)** escrita para
> seguirla sin saber programar, con la sección de problemas reales al final. Lo de
> abajo es el resumen para quien ya se maneja.

### Windows
1. Copia esta carpeta a tu computadora.
2. Clic derecho sobre `setup.ps1` → "Ejecutar con PowerShell" (o `.\setup.ps1`).
   Crea `venv\` e instala todo. La primera vez tarda varios minutos.
3. Corre la app:
   ```
   .\venv\Scripts\python.exe whisperflow.py
   ```
4. (Opcional) Arranque automático al iniciar sesión: `.\venv\Scripts\python.exe
   install_startup.py` (desinstalar: agrega `--remove`).

### macOS / Linux
1. Copia esta carpeta a tu computadora.
2. Ejecuta el instalador guiado (te pregunta todo paso a paso):
   ```
   bash install.sh
   ```
   Crea el venv, instala dependencias (en Linux también `xclip`/`xdotool`/
   `wl-clipboard`/`wtype`), te deja elegir el modelo de Whisper, escribe el archivo
   `.env` y (opcional) configura el arranque automático.
3. Corre la app:
   ```
   ./venv-mac/bin/python whisperflow.py      # Mac
   ./venv-linux/bin/python whisperflow.py    # Linux
   ```
4. **Permisos** (importantísimo en Mac): Configuración del Sistema → Privacidad y
   seguridad → activa **Accesibilidad** y **Supervisión de entrada** para la
   terminal/Python. Sin esto, los atajos no funcionan.
   En Linux, tu usuario debe poder leer el teclado / escribir a `/dev/uinput`
   (grupo `input`); el instalador te lo recuerda.

La primera vez, la app **descarga el modelo de Whisper** (~1.5 GB con el default
`medium`). La bandeja aparece al instante con el mensaje "cargando modelo…" y puedes
dictar en cuanto termina.

## Configuración

Toda la configuración va en un archivo **`.env`** en la carpeta del proyecto (copia
de `.env.example`). Las variables del sistema, si las definís, tienen prioridad.

Claves principales:

| Variable | Default | Qué hace |
|---|---|---|
| `WHISPERFLOW_MODEL_SIZE` | `medium` | Modelo de Whisper (`tiny`/`base`/`small`/`medium`/`large-v3`/`large-v3-turbo`). Sin GPU, usá `small`. |
| `WHISPERFLOW_LANGUAGE` | `es` | Idioma de transcripción. |
| `WHISPERFLOW_MIC_ALWAYS_ON` | `1` | Micrófono armado siempre (no se pierde el arranque del dictado). `0` = abrirlo en cada dictado. |
| `WHISPERFLOW_PREROLL_MS` | `350` | Cuánto audio anterior al atajo se conserva. |
| `WHISPERFLOW_HANDSFREE_GRACE_MS` | `220` | Ventana para cancelar el bip de push-to-talk cuando el atajo asciende a manos libres. |
| `WHISPERFLOW_MAC_HOTKEY` | `cgevent` | Solo Mac: `cgevent` (nativo) o `pynput` (fallback). |

### ¿Qué modelo conviene?

`scripts/bench_models.py` compara modelos **en tu máquina** midiendo exactitud (WER)
y latencia sobre las mismas frases. Lo más fiable es medir con tu propia voz:

```
python scripts/bench_models.py --record --audio-dir bench_audio
```

Te va mostrando frases para leer en voz alta y después compara todos los modelos
sobre esas grabaciones. Medido así en una RTX 4050 de portátil (6 GB) con frases en
español y vocabulario técnico:

| modelo | WER | latencia mediana | VRAM |
|---|---|---|---|
| `small` | 7.8 % | 0.48 s | 554 MB |
| **`medium`** | **2.3 %** | **0.94 s** | **1472 MB** |
| `large-v3-turbo` | 5.9 % | 0.68 s | 1574 MB |
| `large-v3` | 3.9 % | 1.41 s | 2976 MB |

De ahí sale el default `medium`: **tres veces menos errores que `small`** por menos
de un segundo de espera. En CPU la cuenta cambia por completo — ahí `small` gana.

## Personalización

- **`dictionary.txt`** — vocabulario propio (nombres, herramientas, jerga) para que
  Whisper transcriba mejor esos términos. Se relee en cada dictado: edítalo sin
  reiniciar. Las instrucciones están dentro del archivo.
  Este archivo **no se versiona** (suele llenarse de nombres de clientes y proyectos);
  los instaladores lo crean copiando `dictionary.example.txt`, que es la plantilla que
  sí está en el repo. Si `dictionary.txt` no existe, la app lee la plantilla.
- **Ícono en la bandeja** — clic derecho → "Salir" para cerrar la app.
- Casi cualquier otra cosa es una constante en `whisperflow/core/*.py` o una entrada
  del `.env`.

## Editar este proyecto con un agente de código (Claude Code, etc.)

Esta carpeta incluye un archivo `CLAUDE.md` con el contexto técnico del proyecto
(arquitectura en paquete `whisperflow/`, backends por SO, decisiones no obvias, cómo
probar cambios). Si tienes Claude Code instalado, abre una terminal en esta carpeta y
corre `claude`, y pídele en español lo que quieras cambiar — el agente ya tiene el
contexto necesario.

## Estado y limitaciones

- **Windows**: soporte completo y verificado en uso diario.
- **macOS / Linux**: implementados pero **requieren verificación en cada SO real**
  (el desarrollo se hizo desde macOS, sin poder ejecutar los backends de teclado/
  overlay nativos). Reportá lo que fallen y se ajusta.
- **Wayland** (Linux): *best-effort* (los atajos globales y la inyección de teclas
  están restringidos por el compositor). Si falla, probá sesión X11.
