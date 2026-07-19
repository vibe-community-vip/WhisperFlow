# WhisperFlow local — contexto para un agente de código

Dictado por voz local/offline (faster-whisper), push-to-talk y modo manos libres
por atajo global, indicador flotante animado, y reescritura opcional de tono vía
LLM (**OpenAI u Ollama local**). **Multiplataforma**: Windows, macOS y Linux (X11
con soporte; Wayland best-effor). La app es un paquete `whisperflow/` con un shim
`whisperflow.py` que conserva el comando de ejecución original.

Proyecto personal del usuario, pensado para modificarse a mano o con un agente. No
hay tests automatizados ni CI — la forma de verificar un cambio es corriendo la app
y observándola (ver "Cómo probar cambios"). **Sé conservador**: es una herramienta
que la persona usa a diario para escribir; un bug la deja sin poder dictar.

> **Rama de reingeniería:** `refactor/cross-platform`. `main` todavía conserva la
> versión monolítica Windows-only original (un solo `whisperflow.py`). Este CLAUDE
> describe el estado de `refactor/cross-platform` (Fases 0–7 aplicadas).

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
                                         #         Ollama/OpenAI/none, escribe .env, autostart, permisos
./venv-mac/bin/python whisperflow.py     # Mac
./venv-linux/bin/python whisperflow.py   # Linux
```

## Arquitectura (paquete `whisperflow/`)

- **`whisperflow.py`**: shim permanente (`from whisperflow.app import main`).
- **`app.py`**: orquestador. La clase `Application` cablea backends + servicios y
  contiene la **máquina de estados** (`on_event`, `make_profile_key_handler`,
  `transcribe_and_paste`, `recover_last_text`, `run`). Mantiene el estado de
  grabación (`_pressed`, `_recording_active`, `_hands_free`, …) bajo `_state_lock`.
- **`core/`** — núcleo multiplataforma, **sin dependencias de SO**:
  `recorder.py` (sounddevice), `asr.py` (faster-whisper, **carga perezosa**),
  `dictionary.py` (3 niveles de precisión), `rewriter.py` (**selector de LLM**
  Ollama/OpenAI/Noop), `config.py` (lee `.env`), `tray.py` (pystray), más las
  interfaces `beep_base.py` / `overlay_base.py` / `paste_base.py` / `hotkey_base.py`.
- **`backends/<os>/`** — implementaciones por SO de beep/overlay/paste/hotkey/
  startup_init. `backends/_selector.py` elige según `sys.platform`
  (`win32` → `windows/`, `darwin` → `macos/`, `linux` → `linux/`).

Hilos (como en el monolito): bandeja pystray (principal, bloqueante); hooks de
teclado (hilos del backend); callback de audio (PortAudio); overlay (hilo + Tk
propio, comandos por `queue.Queue` — **nunca toques widgets desde otro hilo**);
transcripción (hilo dedicado por enunciado); beeps y restore-portapapeles (daemon).
El **modelo se carga en un hilo en background al arrancar** (no al importar): la
bandeja aparece al instante ("cargando modelo…") y la máquina **bloquea el dictado**
hasta que esté listo (overlay "loading" + beep).

**Backends de tono** (`core/rewriter.py`): `select_rewriter()` con `auto` (default) =
Ollama si responde (~200 ms de sonda TCP) → OpenAI si hay `OPENAI_API_KEY` → Noop.
Forzable con `WHISPERFLOW_LLM_BACKEND`. Cada reescritura tiene timeout de 30 s y
**degrada a texto original + aviso** si falla.

### Atajos por SO
- **Windows / Linux (X11)**: `Ctrl+Win`/`Ctrl+Super` push-to-talk; `+Espacio` manos
  libres; `Ctrl+Alt+Z` re-pegar; `,`/`.`/`-` eligen perfil (y se **suprimen** al escribir).
- **macOS (v1)**: `Cmd+Ctrl` PTT; `Cmd+Ctrl+Espacio` manos libres; `Cmd+Shift+Z`
  re-pegar; `,`/`.`/`-` eligen perfil pero **no se suprimen** (se escriben; bórralas).
  Para supresión nativa: `WHISPERFLOW_MAC_HOTKEY=cgevent` (CGEventTap, experimental).

## Decisiones no obvias (léelas antes de "arreglar" algo que parece un bug)

- **DPI awareness ANTES de `import tkinter`** (`backends/windows/startup_init.py`,
  llamado al principio de `app.main`). Sin esto, en pantallas con escalado Windows
  re-escala la ventana y el overlay aparece movido. (En Mac/Linux no hace falta.)
- **El overlay de Windows NUNCA usa `-alpha`**: con ClearType (sub-pixel) produce
  texto con flecos. Usa solo `-transparentcolor` (colorkey) para las esquinas
  redondeadas. **Mac/Linux sí usan `-alpha`** (allí no existe ClearType ni
  `-transparentcolor`): por eso sus overlays tienen **esquinas cuadradas**.
- **Los beeps van por una ruta de audio separada de la grabación**: `winsound`
  (Windows), `afplay` (Mac), `paplay`/`aplay` (Linux) — nunca `sd.play()`, que
  compite con el `sd.InputStream` de la grabación y sonaba intermitente. Se
  reproducen **síncrono dentro de un hilo daemon** (`BaseBeepBackend._beep`).
- **Overlay con `WS_EX_NOACTIVATE`** (Windows) para no robar el foco del campo donde
  se dicta.
- **`recorder.current_mic_level` es un float sin lock**: lo escribe el callback de
  audio y lo lee el overlay. Es intencional (cosmético; el GIL lo hace seguro).
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
- **`install_startup.py` usa `dirname(sys.executable)`** (no `sys.exec_prefix`) para
  ubicar `pythonw.exe` en el venv de Windows (`<venv>\Scripts\`).
- **macOS v1 no suprime las tone-keys**: pynput no suprime teclas de forma fiable en
  Mac; las teclas `,`/`.`/`-` eligen el perfil pero se escriben (limitación aceptada).
  CGEventTap (`WHISPERFLOW_MAC_HOTKEY=cgevent`) sí suprime, pero es experimental.
- **Wayland es best-effort**: restringe los hotkeys globales y la inyección de
  Ctrl+V. X11 funciona con setup (grupo `input`/udev para `/dev/uinput`, y
  `xclip`+`xdotool` instalados).

## Cómo probar cambios

No hay tests automatizados. Para verificar de verdad:

1. **Harness de caracterización** (rápido, multiplataforma): `python3
   scripts/characterize.py` compara las funciones puras del diccionario contra
   valores *golden* (`scripts/golden/`). Único chequeo que corre en macOS sin
   instalar nada. `--update` para regenerar los golden si el cambio es intencional.
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
- El idioma de transcripción se cambia con `WHISPERFLOW_LANGUAGE` (default `"es"`).
- No hay empaquetado (`.app`/`.exe`/AppImage): el instalador crea un venv por SO.
