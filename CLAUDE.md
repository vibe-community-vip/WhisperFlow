# WhisperFlow local — contexto para un agente de código

Reemplazo casero de Wispr Flow: dictado por voz local/offline (faster-whisper),
push-to-talk y modo manos libres por atajo global, indicador flotante animado,
y reescritura opcional de tono vía LLM. Un solo archivo principal:
`whisperflow.py`. Windows únicamente (usa APIs de win32 y atajos globales).

Este es un proyecto personal del usuario, pensado para seguir modificándose
a mano o con ayuda de un agente. No hay tests automatizados ni CI — la forma
de verificar un cambio es corriendo la app y observándola (ver "Cómo probar
cambios" abajo). Sé conservador: es una herramienta que la persona usa a
diario para escribir, un bug la deja sin poder dictar.

## Comandos (instalación y ejecución)

Todo corre en Windows con Python 3.12. No hay build ni linter.

- **Instalar** (crea `venv\` e instala `requirements.txt`, CUDA incluida —
  tarda varios minutos la primera vez):
  ```
  .\setup.ps1            # o: clic derecho > "Ejecutar con PowerShell"
  ```
- **Correr la app** (la primera vez descarga el modelo de Whisper, ~500 MB):
  ```
  .\venv\Scripts\python.exe whisperflow.py
  ```
- **Arranque automático al iniciar sesión** (atajo a `pythonw.exe`, sin
  ventana de consola). Desinstalar con `--remove` al final:
  ```
  .\venv\Scripts\python.exe install_startup.py
  ```
- Para ver los `print` de diagnóstico al desarrollar, ver "Cómo probar
  cambios" abajo (`pythonw.exe` no tiene stdout).

## Arquitectura (todo en `whisperflow.py`)

- **Hilo principal**: `pystray.Icon.run()` (bloqueante) — el ícono de la
  bandeja del sistema. Salir de la app es "clic derecho → Salir" ahí.
- **Hooks de teclado** (`keyboard.hook`, `keyboard.hook_key`): corren en
  hilos propios de la librería `keyboard`, son hooks globales de verdad a
  nivel de Windows (no solo de esta ventana). `_on_event` maneja Ctrl/Win/
  Espacio; `_make_profile_key_handler` maneja `,`/`.`/`-` con `suppress=True`
  (bloquea la tecla para que no se escriba mientras se está grabando, la
  deja pasar normal el resto del tiempo).
- **Grabación** (`Recorder`, clase con `sd.InputStream`): el callback de audio
  corre en su propio hilo (el de PortAudio), por eso usa un lock para
  `_frames` pero NO para `_current_mic_level` (ver más abajo, es intencional).
- **Overlay flotante**: su propio hilo con su propio `tk.Tk()` y
  `mainloop()`, se le mandan comandos (`overlay_show`/`overlay_hide`) por una
  `queue.Queue` desde los hilos de teclado. Nunca toques widgets de Tkinter
  desde otro hilo directamente — todo pasa por la cola y se aplica dentro del
  loop `poll()` del propio hilo del overlay.
- **Transcripción**: `transcribe_and_paste` corre en un hilo dedicado (no
  bloquea el hook de teclado mientras Whisper procesa).
- **Diccionario de precisión** (`dictionary.txt`, releído en cada dictado):
  tres mecanismos alimentados por el mismo archivo — (1) `initial_prompt` de
  faster-whisper sesga la decodificación hacia esos términos; (2) alias
  exactos `mal=>bien` (`apply_aliases`, reemplazo literal); (3) corrección
  difusa post-transcripción (`apply_dictionary_corrections`: ventana
  deslizante para frases multi-palabra + comparación individual para palabras
  sueltas, con umbrales distintos `MULTI_WORD_THRESHOLD`/`SINGLE_WORD_THRESHOLD`).
- **Perfiles de tono (reescritura por LLM)**: durante una grabación, `,`/`.`
  eligen perfil amigable/profesional; `-` lo cancela. La tecla se bloquea
  (`suppress=True`) para que no se escriba en el campo destino mientras se
  graba. El texto transcrito pasa por OpenAI (`rewrite_with_llm`,
  `PROFILE_PROMPTS`) antes de pegarse. **Degrada de forma transparente sin
  `OPENAI_API_KEY`**: se pega el texto tal cual y se avisa una sola vez por
  consola; el resto de la app sigue igual.

## Decisiones no obvias (léelas antes de "arreglar" algo que parece un bug)

- **DPI awareness debe ir ANTES de `import tkinter`**, al principio absoluto
  del archivo (`SetProcessDpiAwareness`). Sin esto, en pantallas con
  escalado (125%/150%) o multi-monitor, Windows re-escala la ventana después
  de que Tkinter ya calculó su posición, y el overlay aparece movido de
  donde el código pidió.
- **El overlay NUNCA debe usar `-alpha`** (transparencia real de ventana).
  Se descubrió que combinarlo con el renderizado ClearType de Windows
  (sub-pixel, asume un fondo sólido conocido) produce texto con flecos de
  color. Usa solo `-transparentcolor` (colorkey binario: cada pixel es 100%
  opaco o 100% invisible, nunca una mezcla) para las esquinas redondeadas.
- **El beep usa `winsound.PlaySound`, no `sounddevice`**. `sd.play()`
  compite por el mismo stream de PortAudio que `sd.InputStream` (la
  grabación), y sonaba de forma intermitente. `winsound` es una ruta de
  audio de Windows totalmente aparte.
- **El beep se reproduce síncrono** (`winsound.SND_MEMORY` sin
  `SND_ASYNC`) dentro de su propio hilo daemon: combinar `SND_MEMORY` +
  `SND_ASYNC` deja a Windows reproduciendo un buffer que Python puede
  recolectar antes de que termine de sonar, cortándolo al azar.
- **El overlay tiene `WS_EX_NOACTIVATE`** para nunca robarle el foco al
  campo de texto donde se está dictando.
- **`_current_mic_level` es un float global sin lock**: se escribe desde el
  callback de audio y se lee desde el hilo del overlay. Es intencional — es
  solo para algo cosmético (las barritas animadas), una lectura levemente
  "vieja" es inofensiva, y el GIL hace que un solo float sea seguro para
  esto sin necesidad de sincronización real.
- **Ctrl+Win+Espacio siempre pasa primero por "Ctrl+Win abajo"**: la gente
  presiona los modificadores antes que Espacio. Por eso se empieza a grabar
  en cuanto Ctrl+Win están ambos abajo (cero audio perdido), tratándolo como
  push-to-talk provisional; si Espacio se suma, esa misma grabación
  "asciende" a manos libres sin cortar el audio ya capturado.
- **Volver a presionar Ctrl+Win detiene el modo manos libres** (no hace
  falta tocar Espacio otra vez). Efecto secundario conocido y aceptado: si
  el usuario presiona Ctrl+Win por cualquier otra razón mientras está en
  manos libres (ej. un atajo de Windows), eso detiene la grabación.
- **`register_cuda_dlls()`** agrega al PATH los directorios `cublas`/`cudnn`
  de los paquetes pip `nvidia-cublas-cu12`/`nvidia-cudnn-cu12` (si están
  instalados), para que `ctranslate2` los encuentre sin depender de una
  instalación de `torch` con CUDA. `load_model()` intenta GPU en varias
  variantes y cae a CPU si todas fallan — no se rompe si no hay GPU.
- **`install_startup.py` usa `dirname(sys.executable)`, no
  `sys.exec_prefix`**, para ubicar `pythonw.exe`: dentro de un venv de
  Windows, `pythonw.exe` vive en `<venv>\Scripts\`, pero `sys.exec_prefix`
  apunta a la raíz del venv (sin `\Scripts`).
- **`_clipboard_paste` libera `alt`/`z` antes de mandar `ctrl+v`**: si el
  pegado lo dispara un atajo (ej. Ctrl+Alt+Z se detecta al bajar la Z, antes
  de soltar los modificadores), dejar `alt` abajo haría que el destino
  reciba Ctrl+Alt+V (que no pega) en vez de Ctrl+V. Además pega `texto + " "`
  (un espacio al final, para separar del cursor) y restaura el portapapeles
  previo tras 0.6 s en un hilo aparte (devolverlo sin bloquear el pegado).
- **`on_quit` usa `os._exit(0)`, no `sys.exit()`**: hay hilos daemon (overlay,
  audio, transcripción) y el `mainloop()` de pystray; un apagado "limpio"
  colgaría la salida. Es intencional.

## Cómo probar cambios

No hay tests automatizados. Para verificar un cambio de verdad:

1. Lanza la app en modo consola (para ver los `print` de diagnóstico, ya que
   `pythonw.exe` no tiene stdout):
   ```
   py -3.12 whisperflow.py > debug.log 2> debug_err.log
   ```
   o con `WHISPERFLOW_DEBUG=1` en el entorno para loguear cada evento crudo
   de teclado (`_on_event`).
2. Simula los atajos globales desde OTRO proceso de Python con la librería
   `keyboard` (`keyboard.press("ctrl")`, etc.) — funciona porque el hook de
   esta app es un hook real de Windows, indistinguible de una tecla física.
3. Si el cambio afecta al overlay visual, toma una captura de pantalla real
   con `PIL.ImageGrab.grab(all_screens=True)` (el `all_screens=True` es
   necesario en setups multi-monitor; sin él solo se captura el monitor
   principal y se puede pasar por alto que el overlay ni apareció).
4. Borra `debug.log`/`debug_err.log` y cualquier captura temporal al
   terminar, y relanza la app normal con `pythonw.exe` (sin consola) para
   uso diario.

## Cosas que NO están conectadas a nada (para no asumir que existen)

- No hay actualizador automático ni telemetría.
- No hay UI de configuración — todo se ajusta editando constantes en
  `whisperflow.py` o el contenido de `dictionary.txt`.
- El idioma de transcripción está fijo en `LANGUAGE = "es"` (español) al
  principio de `whisperflow.py`; cambiarlo es una sola línea.
