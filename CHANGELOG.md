# Changelog

Todos los cambios notables de **WhisperFlow** se documentan en este archivo.

El formato se basa en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/)
y este proyecto se rige por [Versionado Semántico](https://semver.org/lang/es/).

## [Unreleased]

### Agregado
- **Historial persistido para Ctrl+Alt+Z** (`core/recall.py`): recuerda hasta las
  últimas 3 transcripciones (antes solo la última, y solo en memoria). Presionar
  Ctrl+Alt+Z varias veces seguidas sin dictar nada nuevo en medio cicla hacia atrás
  por esas 3; dictar algo nuevo reinicia el ciclo a la más reciente. Se guarda en
  `last_recordings.json` (raíz del proyecto, en `.gitignore`), así que sobrevive a
  reinicios de la app — antes ese estado vivía en `Application.
  _last_transcribed_text` y se perdía en cada reinicio.

### Corregido
- **Detección de la tecla Windows en `Application._normalize`**: pasó de una lista
  de coincidencias exactas (`"windows_l"`, `"super_r"`, ...) a una comprobación por
  substring (como en el monolito original), porque en Windows con configuración
  regional en español la librería `keyboard` reporta el nombre de la tecla como
  `"windows izquierda"` / `"left windows"`, que no calzaba con ninguna entrada de la
  lista — el push-to-talk (`Ctrl+Win`) quedaba completamente inoperante en ese
  locale.

## [1.0.0] - 2026-07-20

Primera release. Refactor multiplataforma del monolito original (Windows-only) a
un paquete modular `whisperflow/` con backends por sistema operativo (Windows,
macOS, Linux). La funcionalidad de Windows se preserva intacta (regresión cero);
se suma soporte para macOS y Linux, motor MLX para Apple Silicon, VAD por energía,
historial Markdown y selector de LLM.

### Agregado
- **Arquitectura multiplataforma** (`whisperflow/`): núcleo `core/` **sin
  dependencias de SO** + `backends/<os>/` (`windows/`, `macos/`, `linux/`).
  `backends/_selector.py` elige la implementación según `sys.platform`. El shim
  `whisperflow.py` conserva el comando de ejecución original.
- **Soporte de GPU Apple Silicon** vía MLX
  (`mlx-community/whisper-large-v3-mlx-4bit`) con fallback automático a CPU /
  faster-whisper si falla. Motor seleccionable con `WHISPERFLOW_ASR_ENGINE`.
- **Selector de backend de reescritura de tono** (`core/rewriter.py`): Ollama
  local / OpenAI / Noop con auto-detección — `auto` prueba Ollama (~200 ms de
  sonda TCP) → OpenAI si hay `OPENAI_API_KEY` → Noop. Forzable con
  `WHISPERFLOW_LLM_BACKEND`. Cada reescritura tiene timeout de 30 s y degrada a
  texto original si falla.
- **VAD por energía** (`core/vad.py`, cableado en `transcribe_and_paste`) que
  descarta las capturas mudas ANTES de transcribir, evitando que Whisper alucine
  texto repetido sobre silencio (p. ej. `"arrendamos arrendamos…"`). Medido:
  silencio ~RMS 0.003, dictado real ~0.1–0.2. Configurable: `WHISPERFLOW_VAD`,
  `WHISPERFLOW_VAD_THRESHOLD`, `WHISPERFLOW_VAD_MIN_FRAMES`, `WHISPERFLOW_VAD_FRAME_MS`.
- **Historial de transcripciones en Markdown** (`core/history.py`), activo por defecto.
- **Configuración centralizada vía `.env`** (`core/config.py`, copia de
  `.env.example`), con prioridad: variable del SO > `.env` > defaults históricos
  (sin `.env`, sin cambio de comportamiento).
- **Carga perezosa del modelo** en un hilo en background al arrancar: la bandeja
  aparece al instante ("cargando modelo…") y la máquina de estados bloquea el
  dictado hasta tener el modelo listo.
- **Hotkeys configurables** (una sola configuración sirve en los 3 SO) y backend
  de CGEventTap nativo para macOS (`backends/macos/hotkey_cgevent.py`) que
  **suprime** las tone-keys (`,`/`.`/`-`).
- **Overlay flotante animado** con nivel de micrófono, por SO (Tk en macOS/Linux,
  Win32 en Windows), con `WS_EX_NOACTIVATE` / no-activación para no robar el foco.
- **Beeps por ruta de audio separada** de la grabación (`winsound` / `afplay` /
  `paplay`-`aplay`), síncronos en un hilo daemon.
- **Instaladores guiados**: `install.sh` (macOS/Linux) y `setup.ps1` interactivo
  (Windows). Requisitos por SO (`requirements.txt`).
- **Harness de caracterización** del diccionario (`scripts/characterize.py`) con
  valores *golden* (`scripts/golden/`) — único chequeo que corre en macOS sin
  instalar nada.
- **Licencia MIT** (`LICENSE`).

### Cambiado
- El monolito `whisperflow.py` (Windows-only, ~876 líneas) pasó a un paquete
  modular; el archivo quedó como shim (`from whisperflow.app import main`).
- En macOS, el backend de hotkeys por defecto pasó a `cgevent`
  (`WHISPERFLOW_MAC_HOTKEY=cgevent`); las tone-keys ahora se suprimen al escribir.
- Los atajos dejaron de estar hardcodeados por SO: ahora son **config-driven**
  (defaults documentados en `.env.example`).

### Corregido
- **Crash de `NSApplication` en macOS**: el overlay Tk ahora corre en el hilo
  principal (pystray *detached*).
- **Crash de `pynput`** resuelto al usar `cgevent` como backend por defecto en macOS.
- **Nombre de modelo MLX** correcto (`whisper-large-v3-mlx-4bit`) con fallback a
  `base-mlx`.
- **Pegado en macOS** ahora restaura el portapapeles previo (`pbpaste`/`pbcopy`
  en hilo daemon) — dictar ya no te pisa el portapapeles.
- Beeps reproducidos por ruta de audio propia: antes sonaban intermitentes al
  competir con el `sd.InputStream` de la grabación.

### Limitaciones conocidas
- **Wayland** es *best-effort*: restringe hotkeys globales e inyección de `Ctrl+V`.
  X11 funciona con setup (grupo `input`/udev para `/dev/uinput`, `xclip`+`xdotool`).
- **VAD por energía** no distingue voz de ruido sostenido (música, ventilador
  fuerte). Para eso haría falta un VAD neuronal (silero).
- El pegado restaura solo contenido **textual** del portapapeles (no imágenes):
  `pbpaste`/`pyperclip` no emiten binarios a stdout.
- **Sin tests automatizados ni CI**; la verificación es manual (ver `CLAUDE.md`).
- Backends de macOS y Linux compilan pero **requieren verificación runtime** en
  cada SO; la versión Windows es la usada a diario.

[1.0.0]: https://github.com/vibe-community-vip/WhisperFlow/releases/tag/v1.0.0
