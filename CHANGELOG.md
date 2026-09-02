# Changelog

Todos los cambios notables de **WhisperFlow** se documentan en este archivo.

El formato se basa en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/)
y este proyecto se rige por [Versionado Semántico](https://semver.org/lang/es/).

## [Unreleased]

### Cambiado
- **Indicador flotante rediseñado.** Se dibuja con Pillow
  (`core/overlay_render.py`) en lugar de primitivas de `tkinter.Canvas`: cápsula con
  degradado vertical, borde tenue (el color de estado al 13 % en vez de una línea
  sólida), luz difusa que nace del punto de estado y de las barras, brillo de vidrio
  en el filo superior, y tipografía Segoe UI Semilight en minúsculas con *tracking*.
  El texto lo rasteriza Pillow, no Tk, así que ya no depende de ClearType. Coste
  medido: ~0.04 ms por frame (fondo y sprites cacheados por estado).
  El color-key pasó de magenta a un casi-negro `(1,0,1)`: como el colorkey de Windows
  solo borra el color exacto, el borde antialiaseado dejaba un **fleco fucsia**
  alrededor de la cápsula.
- **La animación del overlay se unificó en `core/overlay_base.TkOverlayBase`.** Los
  tres backends por SO tenían el mismo bucle duplicado; ahora solo implementan
  `_configure_window` (transparencia y flags de ventana).
- **Manos libres suena UN solo bip, distinto al de push-to-talk.** Antes se oían
  tres (uno por cada paso del acorde `Ctrl+Win` → `Espacio`). El bip de inicio ahora
  se difiere `WHISPERFLOW_HANDSFREE_GRACE_MS` (220 ms) y se cancela si el atajo
  asciende a manos libres. Se difiere **solo el sonido**: la grabación arranca igual
  al instante. PTT = 880 Hz corto; manos libres = 620 Hz más largo.
- **Modelo por defecto: `small` → `medium`.** Medido con `scripts/bench_models.py`
  en una RTX 4050 de portátil sobre frases en español con vocabulario técnico:
  `small` 7.8 % WER / 0.48 s · **`medium` 2.3 % / 0.94 s** · `large-v3-turbo` 5.9 % /
  0.68 s · `large-v3` 3.9 % / 1.41 s. Tres veces menos errores por medio segundo más.
  En CPU conviene volver a `small` vía `.env`.
- **`condition_on_previous_text=False`** en ambos motores ASR: cada dictado es
  independiente y arrastrar el texto anterior es la causa clásica de los bucles de
  repetición.

### Agregado
- **Guía de instalación paso a paso** (`INSTALACION.md`), escrita para seguirla sin
  saber programar, con una sección de problemas reales (atajo que no responde, app
  que se cierra, dictado lento, VAD demasiado estricto) y enlazada desde el README.
- **Filtro de alucinaciones conocidas** (`core/hallucinations.py`): quita el crédito
  *"Subtítulos realizados por la comunidad de Amara.org"* que Whisper alucina sobre
  audio casi mudo. Venía de la instalación monolítica del autor y no había llegado al
  paquete. Es la cuarta y última red, después del VAD por energía, el `vad_filter`
  interno y `condition_on_previous_text=False`.
  Nota: el parámetro `hallucination_silence_threshold` de faster-whisper, que el
  monolito también pasaba, **es inerte sin `word_timestamps=True`** (está dentro de
  ese `if` en `transcribe.py`), así que no se portó.
- **Micrófono siempre armado + pre-roll** (`core/recorder.py`). El `sd.InputStream`
  se abre al arrancar la app y no se cierra entre dictados; mientras no se graba, el
  audio cae en un buffer circular de `WHISPERFLOW_PREROLL_MS` (350 ms) que se usa
  como semilla al pulsar el atajo. Abrir el stream en el momento del atajo costaba
  **~120 ms medidos** (~470 ms la primera vez) de audio que simplemente no se
  grababa — de ahí la sensación de que "no graba bien hasta después del bip". Ahora
  `start()` tarda 0 ms y además entra lo dicho justo antes de pulsar. Se puede volver
  al comportamiento anterior con `WHISPERFLOW_MIC_ALWAYS_ON=0`.
- **`scripts/bench_models.py`**: compara modelos locales de Whisper en tu máquina
  midiendo WER y latencia sobre el mismo audio. Con `--record` graba las frases con
  tu propia voz (la única medición que de verdad decide) y con `--noise` simula
  ruido de fondo.

### Seguridad
- **El diccionario personal ya no se versiona.** `dictionary.txt` pasó a `.gitignore`
  y se agregó `dictionary.example.txt` como plantilla versionada. El diccionario real
  se llena de nombres de clientes, proyectos y jerga propia, y este repo es público:
  antes cualquier `git add -A` los publicaba. Los instaladores crean `dictionary.txt`
  copiando la plantilla (sin pisar uno existente) y, si no existe, la app lee la
  plantilla para que un clon recién bajado funcione igual.

### Quitado
- **Perfiles de tono amigable/profesional y todo el reescritor por LLM.** Se
  eliminaron `core/rewriter.py`, las tone-keys `,`/`.`/`-`, la configuración de
  Ollama/OpenAI (`WHISPERFLOW_LLM_BACKEND`, `WHISPERFLOW_OLLAMA_*`,
  `WHISPERFLOW_OPENAI_*`, `OPENAI_API_KEY`) y la dependencia `openai`. El dictado es
  uno solo: lo que se dicta es lo que se pega.

### Corregido
- **Descarga de modelos en Windows sin modo desarrollador**: se fija
  `HF_HUB_DISABLE_SYMLINKS=1` antes de importar `faster_whisper`. La caché de Hugging
  Face usa symlinks y Windows los bloquea, así que bajar un modelo no cacheado
  fallaba con `WinError 1314` (reproducido con `large-v3-turbo`).
- **Los archivos de texto se leen con `utf-8-sig`** (`.env`, el diccionario y
  `last_recordings.json`). El Bloc de notas de Windows y el `Out-File` de PowerShell
  guardan con BOM; con `utf-8` puro ese BOM se pegaba al primer valor y la línea se
  perdía en silencio — o hacía reventar `json.load` con "Unexpected UTF-8 BOM"
  (reproducido).
- **Nombres de tecla localizados en `Application._normalize`**: en un Windows en
  español la librería `keyboard` reporta Shift como `"mayusculas"`, así que
  `WHISPERFLOW_PTT_KEYS=shift` no funcionaba fuera de un sistema en inglés. Se
  agregaron alias para shift/super/alt/space en varios idiomas.

## [1.0.1]

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
