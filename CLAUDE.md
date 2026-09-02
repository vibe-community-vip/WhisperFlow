# WhisperFlow local — contexto para un agente de código

Dictado por voz local/offline (faster-whisper), push-to-talk y modo manos libres
por atajo global, e indicador flotante animado. **Multiplataforma**: Windows, macOS
y Linux (X11 con soporte; Wayland best-effort). La app es un paquete `whisperflow/`
con un shim `whisperflow.py` que conserva el comando de ejecución original.

**No hay modos de dictado**: lo que se dicta es lo que se pega. Los perfiles de tono
("amigable"/"profesional", teclas `,`/`.`/`-`) y todo el backend de reescritura por
LLM (`core/rewriter.py`, Ollama/OpenAI) **se eliminaron** — si ves referencias a eso
en algún doc viejo, están obsoletas.

Proyecto personal del usuario, pensado para modificarse a mano o con un agente. No
hay tests automatizados ni CI — la forma de verificar un cambio es corriendo la app
y observándola (ver "Cómo probar cambios"). **Sé conservador**: es una herramienta
que la persona usa a diario para escribir; un bug la deja sin poder dictar.

> **Historia:** el proyecto empezó como un `whisperflow.py` monolítico Windows-only;
> la rama `refactor/cross-platform` lo partió en el paquete actual y ya está mergeada
> en `main`. Este CLAUDE describe `main`.

## Comandos (instalación y ejecución)

No hay build ni linter. La configuración va en un **`.env`** en la raíz (copia de
`.env.example`), cargado por `whisperflow/core/config.py`. Prioridad: variable del
SO > `.env` > defaults (los defaults son los históricos → sin `.env`, sin cambio).

**Windows** (Python 3.12):
```
.\setup.ps1                                    # venv\ + deps (CUDA opcional)
.\venv\Scripts\python.exe whisperflow.py       # corre la app
.\venv\Scripts\python.exe install_startup.py   # (opcional) arranque automático (--remove quita)
```
**macOS / Linux** (Python 3.11–3.13):
```
bash install.sh                          # guiado: venv, deps (+xclip/xdotool/wl-clipboard/wtype en Linux),
                                         #         elección de modelo, escribe .env, autostart, permisos
./venv-mac/bin/python whisperflow.py     # Mac
./venv-linux/bin/python whisperflow.py   # Linux
```

## Arquitectura (paquete `whisperflow/`)

- **`whisperflow.py`**: shim permanente (`from whisperflow.app import main`).
- **`app.py`**: orquestador. La clase `Application` cablea backends + servicios y
  contiene la **máquina de estados** (`on_event`, `_begin_recording`,
  `_stop_and_transcribe`, `transcribe_and_paste`, `recover_last_text`, `run`).
  Mantiene el estado de grabación (`_held`, `_recording_active`, `_hands_free`, …)
  bajo `_state_lock`.
- **`core/`** — núcleo multiplataforma, **sin dependencias de SO**:
  `recorder.py` (sounddevice, **micrófono siempre armado + pre-roll**), `asr.py`
  (dispatcher; `asr_ct2.py` faster-whisper y `asr_mlx.py` Apple Silicon, **carga
  perezosa**), `dictionary.py` (3 niveles de precisión), `config.py` (lee `.env`),
  `tray.py` (pystray), `vad.py`, `history.py`, `recall.py`, más
  `overlay_render.py` (dibujo del indicador con Pillow) y las interfaces/base
  `beep_base.py` / `overlay_base.py` / `paste_base.py` / `hotkey_base.py`.
- **`backends/<os>/`** — implementaciones por SO de beep/overlay/paste/hotkey/
  startup_init. `backends/_selector.py` elige según `sys.platform`
  (`win32` → `windows/`, `darwin` → `macos/`, `linux` → `linux/`).

Hilos (como en el monolito): bandeja pystray (principal, bloqueante); hooks de
teclado (hilos del backend); callback de audio (PortAudio, **corriendo siempre**);
overlay (hilo + Tk propio, comandos por `queue.Queue` — **nunca toques widgets desde
otro hilo**); transcripción (hilo dedicado por enunciado); beeps y
restore-portapapeles (daemon). El **modelo se carga en un hilo en background al
arrancar** (no al importar): la bandeja aparece al instante ("cargando modelo…") y la
máquina **bloquea el dictado** hasta que esté listo (overlay "loading" + beep).

### Atajos por SO
- **Windows / Linux (X11)**: `Ctrl+Win`/`Ctrl+Super` push-to-talk; `+Espacio` manos
  libres; `Ctrl+Alt+Z` re-pegar (cicla hasta las últimas 3 grabaciones, persistido en
  disco — ver `core/recall.py`).
- **macOS**: `Cmd+Ctrl` PTT; `Cmd+Ctrl+Espacio` manos libres; `Ctrl+Alt+Z` re-pegar.
  Backend default `WHISPERFLOW_MAC_HOTKEY=cgevent` (CGEventTap nativo vía pyobjc, el
  verificado en Mac real; requiere Accesibilidad + Supervisión de entrada). `pynput`
  es el fallback (puede crashear según versiones de pyobjc).

Los atajos son **config-driven** (una sola config sirve en los 3 SO); lo de arriba
son los defaults de `.env`. `register_suppressible_key` sigue existiendo en la
interfaz de hotkeys pero **ya nadie la usa** (era para las tone-keys de perfil).

## Decisiones no obvias (léelas antes de "arreglar" algo que parece un bug)

- **DPI awareness ANTES de `import tkinter`** (`backends/windows/startup_init.py`,
  llamado al principio de `app.main`). Sin esto, en pantallas con escalado Windows
  re-escala la ventana y el overlay aparece movido. (En Mac/Linux no hace falta.)
- **El overlay se dibuja con Pillow, no con `tkinter.Canvas`** (`core/overlay_render.py`):
  un frame entero es una imagen que se blitea al canvas. Motivo doble: (a) `Canvas`
  no sabe hacer degradados ni halos (solo formas planas), y (b) el texto lo rasteriza
  Pillow en escala de grises, lo que esquiva el problema de ClearType y permite
  pesos finos + *tracking*. Costo medido: ~0.04 ms por frame (fondo y sprites
  cacheados por estado); la animación corre a 30 fps solo mientras es visible.
- **El overlay de Windows NUNCA usa `-alpha`**: es incompatible con
  `-transparentcolor`, que es lo único que da las esquinas redondeadas.
  **Mac/Linux sí usan `-alpha`** (allí no existe colorkey): por eso sus overlays
  tienen **esquinas cuadradas**.
- **El color-key es un casi-negro `(1,0,1)`, no magenta.** El colorkey de Windows
  borra solo los píxeles *exactamente* iguales al color clave, y el borde redondeado
  es antialiaseado: sus píxeles son mezclas entre la píldora y el fondo sobre el que
  se aplanó. Con magenta eso deja un **fleco fucsia** visible alrededor de la cápsula
  (verificado en captura real). Con un casi-negro, el mismo fleco parece un borde
  oscuro suave — invisible sobre fondos oscuros, y como una sombra sobre los claros.
- **La animación del overlay vive en `core/overlay_base.TkOverlayBase`**, no en cada
  backend. Los tres `backends/<os>/overlay.py` solo implementan `_configure_window`
  (transparencia y flags de ventana). Antes había tres copias del mismo bucle de
  animación que había que mantener sincronizadas.
- **Los beeps van por una ruta de audio separada de la grabación**: `winsound`
  (Windows), `afplay` (Mac), `paplay`/`aplay` (Linux) — nunca `sd.play()`, que
  compite con el `sd.InputStream` de la grabación y sonaba intermitente. Se
  reproducen **síncrono dentro de un hilo daemon** (`BaseBeepBackend._beep`).
- **El bip de inicio es DIFERIDO y cancelable** (`HANDSFREE_GRACE_MS`, default 220 ms).
  Entrar a manos libres es "Ctrl+Win abajo" y después "Espacio", y cada paso sonaba:
  se oían **tres bips**. Ahora `recording_start()` programa su bip con un `Timer`; si
  `hands_free_on()` (o `no_speech()`) llega dentro de la ventana, lo **cancela**.
  Resultado: PTT = 1 bip (880 Hz), manos libres = 1 bip distinto (620 Hz, más largo).
  **Solo se difiere el sonido**: la grabación arranca igual al instante.
- **El micrófono queda armado desde el arranque** (`Recorder.arm()` en `app.run`) y
  el `sd.InputStream` **no se cierra entre dictados**. Abrirlo al pulsar el atajo
  costaba ~120 ms medidos (90 ms de construcción + 34 ms hasta el primer callback;
  ~470 ms la primera vez del proceso) y ese audio no existía: se comía las primeras
  sílabas. Mientras no se graba, el audio cae en un buffer circular de
  `PREROLL_MS` (350 ms) que además se usa como semilla de la grabación, así que
  también entra lo dicho *justo antes* de pulsar. `stop()` limpia el pre-roll para no
  arrastrar la cola de un dictado al siguiente. Contrapartida: el indicador de
  "micrófono en uso" del SO queda encendido siempre (`WHISPERFLOW_MIC_ALWAYS_ON=0`
  vuelve al modo anterior). Bonus: `stop()` ya no cierra el dispositivo, así que deja
  de bloquear al hilo del hook de teclado.
- **`condition_on_previous_text=False`** en ambos motores ASR. Cada dictado es
  independiente, no la continuación del anterior; con `True`, Whisper arrastra el
  texto ya decodificado y es la causa clásica de los bucles de repetición. No
  desactiva el `initial_prompt` (verificado: los términos del diccionario siguen
  acertando).
- **`HF_HUB_DISABLE_SYMLINKS=1` antes de importar `faster_whisper`** (`core/asr_ct2.py`).
  La caché de Hugging Face usa symlinks y Windows sin "modo desarrollador" no deja
  crearlos: descargar un modelo no cacheado revienta con `WinError 1314`
  (reproducido al bajar `large-v3-turbo`).
- **`_normalize` acepta nombres de tecla localizados.** Los backends reportan el
  nombre en el idioma del SO: en un Windows en español, Shift llega como
  `"mayusculas"`. Sin los alias, `WHISPERFLOW_PTT_KEYS=shift` no funcionaba fuera de
  un sistema en inglés.
- **Overlay con `WS_EX_NOACTIVATE`** (Windows) para no robar el foco del campo donde
  se dicta.
- **`recorder.current_mic_level` es un float sin lock**: lo escribe el callback de
  audio y lo lee el overlay. Es intencional (cosmético; el GIL lo hace seguro).
- **Cuatro defensas contra las alucinaciones de Whisper**, en orden: (1) el VAD por
  energía de `core/vad.py` descarta la captura antes de llamar al modelo, (2)
  `vad_filter=True` recorta los tramos mudos del audio que sí se transcribe, (3)
  `condition_on_previous_text=False` corta el bucle, y (4) `core/hallucinations.py`
  borra el crédito de Amara.org si aun así se cuela. NO agregar
  `hallucination_silence_threshold`: es inerte sin `word_timestamps=True` (está
  dentro de ese `if` en el `transcribe.py` de faster-whisper) y activar los
  timestamps de palabra cuesta cómputo en cada dictado.
- **VAD por energía antes de transcribir** (`core/vad.py`, cableado en
  `transcribe_and_paste`): Whisper **alucina texto repetido** sobre audio casi mudo
  (silencio/ruido bajo) — p.ej. `"arrendamos arrendamos…"`. Medido en la Mac de
  referencia: silencio ~RMS 0.003, dictado real ~0.1–0.2. El VAD descarta la captura
  si `peak < WHISPERFLOW_VAD_THRESHOLD` (default 0.008) o hay pocas tramas fuertes,
  **antes** de llamar al modelo. No es un bug: si rechazara dictado real, bajá el
  umbral o `WHISPERFLOW_VAD=0`. No distingue voz de ruido sostenido (para eso haría
  falta un VAD neuronal tipo silero).
- **Ctrl+Win+Espacio siempre pasa por "Ctrl+Win abajo"** primero: se empieza a
  grabar en cuanto ambos modificadores están abajo (cero audio perdido) como
  push-to-talk provisional; si Espacio se suma, la grabación **asciende** a manos
  libres sin cortar el audio. Volver a presionar Ctrl+Win detiene manos libres.
- **`register_cuda_dlls()` debe ejecutarse ANTES de `from faster_whisper import
  WhisperModel`** (en `core/asr.py`). Agrega al PATH `cublas`/`cudnn` de los pip
  `nvidia-*`. `load_model()` prueba GPU y cae a CPU si falla — no se rompe sin GPU.
- **El pegado (`backends/<os>/paste.py`) libera `alt`/`z` antes de inyectar el
  pegado**, pega `texto + " "` y restaura el portapapeles previo a los 0.6 s. Sin
  liberar `alt`, un pegado disparado por Ctrl+Alt+Z mandaría Ctrl+Alt+V (que no pega).
- **`on_quit` usa `os._exit(0)`**: con hilos daemon + el mainloop de pystray, un
  apagado "limpio" colgaría la salida.
- **El diccionario son DOS archivos**: `dictionary.example.txt` (plantilla, se
  versiona) y `dictionary.txt` (el del usuario, en `.gitignore`). El personal se
  llena de nombres de clientes y jerga propia y este repo es público. Si
  `dictionary.txt` no existe se lee la plantilla (`active_dictionary_path`), así que
  un clon recién bajado funciona; los instaladores copian una en la otra, y **nunca
  pisan** un `dictionary.txt` existente.
- **Los archivos de texto se leen con `utf-8-sig`, no `utf-8`** (`.env`,
  `dictionary.txt`, `last_recordings.json`). El Bloc de notas de Windows y el
  `Out-File` de PowerShell guardan con BOM; con `utf-8` puro ese BOM se pega al
  primer valor y la línea se pierde en silencio (o revienta `json.load`, verificado).
- **`setup.ps1` DEBE guardarse con BOM (UTF-8 with signature).** Windows PowerShell
  5.1 asume ANSI cuando no hay BOM, y los acentos del script se corrompen hasta
  romper el parseo (verificado: 4 errores de sintaxis). `install.sh`, al revés, NO
  debe tener BOM: rompería el shebang. Si editás `setup.ps1` con una herramienta que
  reescribe el archivo, comprobá los primeros bytes.
- **`install_startup.py` usa `dirname(sys.executable)`** (no `sys.exec_prefix`) para
  ubicar `pythonw.exe` en el venv de Windows (`<venv>\Scripts\`).
- **La supresión de teclas en macOS quedó sin uso**: pynput no suprime de forma
  fiable y CGEventTap sí, pero lo único que la usaba eran las tone-keys de perfil,
  que ya no existen. El mecanismo sigue en los backends de hotkeys por si vuelve a
  hacer falta.
- **Wayland es best-effort**: restringe los hotkeys globales y la inyección de
  Ctrl+V. X11 funciona con setup (grupo `input`/udev para `/dev/uinput`, y
  `xclip`+`xdotool` instalados).

## Cómo probar cambios

No hay tests automatizados. Para verificar de verdad:

1. **Harness de caracterización** (rápido, multiplataforma): `python3
   scripts/characterize.py` compara las funciones puras del diccionario contra
   valores *golden* (`scripts/golden/`). Único chequeo que corre en macOS sin
   instalar nada. `--update` para regenerar los golden si el cambio es intencional.
1b. **Comparar modelos ASR** (`scripts/bench_models.py`): mide WER y latencia de
   varios modelos sobre el mismo audio, en esta máquina. Con `--record` graba las
   frases con tu propia voz, que es la única medición que de verdad decide. Es lo que
   se usó para elegir el default `medium` sobre `small`.
2. **`py_compile`** de todo el árbol verifica sintaxis (incluidos backends de otros
   SO que no podés correr localmente):
   `find whisperflow scripts whisperflow.py -name "*.py" | xargs python3 -m py_compile`
3. Lanza la app en modo consola (para ver los `print`):
   - Windows: `py -3.12 whisperflow.py > debug.log 2> debug_err.log`
   - Mac/Linux: `./venv-*/bin/python whisperflow.py > debug.log 2> debug_err.log`
   - Con `WHISPERFLOW_DEBUG=1` se loguea cada evento crudo de teclado (`on_event`).
4. Simula los atajos globales desde **otro** proceso Python con la lib `keyboard`
   (`keyboard.press("ctrl")`, …) — funciona porque el hook es un hook real del SO.
5. Si el cambio afecta al overlay, captura de pantalla real (Windows:
   `PIL.ImageGrab.grab(all_screens=True)`; Mac `screencapture`; Linux `gnome-screenshot`).
6. Limpiá `debug.log`/`debug_err.log` y capturas al terminar.

> Los backends de Mac y Linux **no se pudieron ejecutar** durante el desarrollo
> (faltan pyobjc/pynput; los hooks requieren permisos). Compilan pero **requieren
> verificación runtime en cada SO**. Prioridad absoluta de verificación: la versión
> **Windows** (la que el usuario usa a diario) tras el refactor.

## Cosas que NO están conectadas a nada (para no asumir que existen)

- No hay actualizador automático ni telemetría.
- No hay UI de configuración — todo se ajusta via `.env` (ver `.env.example`) o
  editando `dictionary.txt`. Algunas constantes todavía viven en `core/*.py`.
- **No hay reescritura de tono ni ningún LLM.** `core/rewriter.py` fue eliminado
  junto con los perfiles amigable/profesional y las dependencias `openai`/Ollama.
- El `initial_prompt` del diccionario **se recorta a 800 chars** y Whisper solo
  reserva ~224 tokens de prompt: con un `dictionary.txt` grande (medido: 92 términos
  = 949 chars) los últimos términos **no llegan al modelo**. No quedan sin efecto —
  la corrección difusa post-transcripción se aplica a todos — pero conviene poner
  primero los términos que más importa que acierte de una.
- El idioma de transcripción se cambia con `WHISPERFLOW_LANGUAGE` (default `"es"`).
- No hay empaquetado (`.app`/`.exe`/AppImage): el instalador crea un venv por SO.
