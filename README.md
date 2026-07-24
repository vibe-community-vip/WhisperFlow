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
  transcribir, vuelve a presionar el mismo acorde (o suma `Espacio`).
  - Windows/Linux: `Ctrl + Win + Espacio`  ·  macOS: `Cmd + Ctrl + Espacio`
- **Re-pegar último** — por si no había ningún campo con foco cuando dictaste. Presionado
  varias veces seguidas sin dictar nada nuevo en medio, retrocede a las últimas 3
  grabaciones (dictar algo nuevo reinicia el ciclo). Se persiste en disco
  (`last_recordings.json`), así que sobrevive a reinicios de la app.
  - Windows/Linux: `Ctrl + Alt + Z`  ·  macOS: `Cmd + Shift + Z`

Mientras grabas, puedes tocar una vez (sin soltar nada más) una de estas teclas para
que el texto pase por un LLM antes de pegarse y le cambie el tono:

- `,` → **Amigable** (cálido, algún emoji)
- `.` → **Profesional** (directo, técnico)
- `-` → **Normal** (cancela el perfil; pega tal cual)

> En **Windows/Linux** estas teclas se bloquean al escribir mientras grabás. En
> **macOS** se eligen el perfil pero se escriben (borralas); la supresión nativa se
activa con `WHISPERFLOW_MAC_HOTKEY=cgevent` (experimental).

Un indicador flotante aparece abajo al centro mientras grabas/transcribe, con un
mini-ecualizador que reacciona a tu voz.

## Requisitos

- **Windows 10/11**, **macOS** o **Linux** (X11; Wayland en modo *best-effort*).
- **Python 3.11–3.13** (en Windows, 3.12). Marca "Add to PATH" al instalar.
- Opcional: GPU NVIDIA (Windows/Linux) para transcribir más rápido. Sin GPU, usa CPU.
- Opcional: **Ollama** (reescritura de tono local, gratis y offline) **o** una API
  key de OpenAI. Sin ninguno, el resto funciona igual (sin reescritura de tono).

## Instalación

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
   `wl-clipboard`/`wtype`), te ofrece instalar **Ollama** o usar **OpenAI**,
   escribe el archivo `.env` y (opcional) configura el arranque automático.
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

La primera vez, la app **descarga el modelo de Whisper** (~500 MB). La bandeja
aparece al instante con el mensaje "cargando modelo…" y puedes dictar en cuanto
termina.

## Configuración

Toda la configuración va en un archivo **`.env`** en la carpeta del proyecto (copia
de `.env.example`). Las variables del sistema, si las definís, tienen prioridad.

Claves principales:

| Variable | Default | Qué hace |
|---|---|---|
| `WHISPERFLOW_MODEL_SIZE` | `small` | Modelo de Whisper (`tiny`/`base`/`small`/`medium`/`large-v3`). En Mac recomiendo `base`/`tiny`. |
| `WHISPERFLOW_LANGUAGE` | `es` | Idioma de transcripción. |
| `WHISPERFLOW_LLM_BACKEND` | `auto` | `auto` (Ollama si corre → OpenAI si hay key → ninguno), u `ollama`/`openai`/`none`. |
| `WHISPERFLOW_OLLAMA_MODEL` | `qwen2.5:3b` | Modelo local (alternativas: `qwen2.5:7b`, `llama3.1:8b`). |
| `OPENAI_API_KEY` | — | Para el backend OpenAI. |
| `WHISPERFLOW_MAC_HOTKEY` | `pynput` | Solo Mac: `pynput` (estable) o `cgevent` (suprime tone-keys, experimental). |

**Reescritura de tono local (Ollama)** — recomendado, offline y gratis:

1. Instalá Ollama: Windows `winget install Ollama.Ollama`; Mac `brew install ollama`;
   Linux `curl -fsSL https://ollama.com/install.sh | sh`.
2. Descargá un modelo: `ollama pull qwen2.5:3b`.
3. Dejá `WHISPERFLOW_LLM_BACKEND=auto` (lo detecta solo). El tooltip de la bandeja
   dirá "LLM: ollama".

## Personalización

- **`dictionary.txt`** — vocabulario propio (nombres, herramientas, jerga) para que
  Whisper transcriba mejor esos términos. Se relee en cada dictado: edítalo sin
  reiniciar. Las instrucciones están dentro del archivo.
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
