# Guía de instalación — WhisperFlow local

Esta guía está escrita para seguirla de principio a fin sin saber programar. Si algo
no sale como dice acá, salta a [Cuando algo no funciona](#cuando-algo-no-funciona) al
final: están los problemas reales que aparecen, no una lista genérica.

**Qué vas a tener al terminar:** mantienes `Ctrl` + `Win`, hablas, sueltas, y el texto
aparece escrito donde tengas el cursor. Todo ocurre en tu computadora: no se sube
audio a ningún servidor, no hay cuenta ni suscripción.

---

## Antes de empezar

**Necesitas:**

- **Windows 10/11**, **macOS** o **Linux**.
- **Python 3.12** (en Mac/Linux sirve 3.11–3.13). Es gratis y se instala en 2 minutos.
- **Unos 3 GB de disco** — el modelo de reconocimiento de voz se descarga una vez.
- **10–20 minutos** la primera vez, casi todo esperando descargas.

**Ayuda mucho, pero no es obligatorio:** una tarjeta gráfica **NVIDIA**. Con ella la
transcripción tarda menos de un segundo; sin ella funciona igual pero más lento, y
conviene usar un modelo más chico (la guía te dice cómo).

¿No sabes si tienes NVIDIA? En Windows, abre el **Administrador de tareas**
(`Ctrl+Shift+Esc`) → pestaña **Rendimiento**. Si en la lista de la izquierda aparece
una **GPU** que dice "NVIDIA", la tienes.

---

## Windows

### Paso 1 — Instalar Python

1. Ve a [python.org/downloads/windows](https://www.python.org/downloads/windows/),
   busca la sección **Python 3.12.x** más reciente y descarga
   **Windows installer (64-bit)**. Usa 3.12: con 3.13 algunas dependencias todavía
   no tienen instalador listo para Windows y la instalación puede fallar.
2. Al abrirlo, **marca la casilla "Add python.exe to PATH"** abajo del todo. Este es
   el paso que más se olvida y el que hace que después nada funcione.
3. Clic en **Install Now** y espera.

Para comprobar que quedó bien, abre **PowerShell** (botón Inicio → escribe
`powershell` → Enter) y escribe:

```
python --version
```

Debe responder `Python 3.12.x`. Si dice que no reconoce el comando, Python se instaló
sin marcar "Add to PATH": vuelve a ejecutar el instalador, elige **Modify** y activa
la casilla.

### Paso 2 — Descargar WhisperFlow

Si tienes Git:

```
git clone https://github.com/vibe-community-vip/WhisperFlow.git
cd WhisperFlow
```

Si no lo tienes, es igual de válido: entra a
[la página del proyecto](https://github.com/vibe-community-vip/WhisperFlow), botón
verde **Code** → **Download ZIP**, y descomprime la carpeta donde quieras tenerla
(por ejemplo `Documentos\WhisperFlow`).

### Paso 3 — Ejecutar el instalador

Abre **PowerShell** dentro de esa carpeta. La forma rápida: abre la carpeta en el
Explorador, haz clic en la barra de dirección, escribe `powershell` y Enter.

Luego:

```
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

> El `-ExecutionPolicy Bypass` es porque Windows bloquea los scripts descargados por
> defecto. Solo afecta a esta ejecución, no cambia la configuración de tu sistema.

El instalador va a:

1. Crear una carpeta `venv\` con todo lo que necesita (así no ensucia tu Python).
2. Instalar las dependencias — **esto tarda varios minutos**, son unos 2 GB de
   librerías de NVIDIA. Es normal que parezca colgado.
3. Preguntarte **qué modelo quieres**. Si detecta tarjeta NVIDIA te propone `medium`;
   si no, `small`. Puedes darle Enter y aceptar lo que sugiere.
4. Crear tu `dictionary.txt` a partir de la plantilla.
5. Preguntarte si quieres que **arranque solo** al encender la computadora.

### Paso 4 — Arrancarlo

```
.\venv\Scripts\python.exe whisperflow.py
```

Aparece un **icono en la bandeja del sistema** (abajo a la derecha, junto al reloj)
que dice *"cargando modelo…"*. La **primera vez descarga el modelo** (~1.5 GB con
`medium`), así que puede tardar unos minutos. Cuando el icono cambia a
*"WhisperFlow local"*, ya puedes dictar.

Si prefieres que no se quede una ventana negra abierta, usa `pythonw.exe` en lugar de
`python.exe` — es el mismo programa pero sin consola:

```
.\venv\Scripts\pythonw.exe whisperflow.py
```

---

## macOS y Linux

> **Aviso honesto:** estos dos sistemas están implementados y el código compila, pero
> **no están verificados en uso real** — el desarrollo y las pruebas se hicieron en
> Windows. Es probable que algo necesite ajuste. Si te animas a probarlo, reportar lo
> que falle ayuda muchísimo.

### Paso 1 — Descargar el proyecto

```
git clone https://github.com/vibe-community-vip/WhisperFlow.git
cd WhisperFlow
```

### Paso 2 — Ejecutar el instalador guiado

```
bash install.sh
```

Te va preguntando todo paso a paso: crea el entorno, instala las dependencias (en
Linux también `xclip`, `xdotool`, `wl-clipboard` y `wtype`), te deja elegir el modelo,
crea tu `dictionary.txt` y ofrece configurar el arranque automático.

### Paso 3 — Dar permisos (importante)

**En macOS**, los atajos globales no funcionan sin esto. Ve a **Configuración del
Sistema → Privacidad y seguridad** y activa, para tu Terminal (o para Python):

- **Accesibilidad**
- **Supervisión de entrada**

La primera vez que grabes, macOS también te pedirá permiso de **micrófono**.

**En Linux**, tu usuario necesita poder leer el teclado. Normalmente basta con
agregarlo al grupo `input` y volver a iniciar sesión:

```
sudo usermod -aG input $USER
```

Si usas **Wayland**, ten en cuenta que restringe los atajos globales por diseño y el
soporte es *best-effort*. Si nada responde, prueba iniciar sesión en **X11**.

### Paso 4 — Arrancarlo

```
./venv-mac/bin/python whisperflow.py      # macOS
./venv-linux/bin/python whisperflow.py    # Linux
```

---

## Cómo se usa

| Quiero… | Atajo |
|---|---|
| Dictar mientras sostengo las teclas | Mantén **`Ctrl` + `Win`**, habla, suelta (Mac: `Cmd`+`Ctrl`) |
| Dictar sin sostener nada (manos libres) | **`Ctrl` + `Win` + `Espacio`**. Vuelve a pulsar `Ctrl`+`Win` para terminar |
| Volver a pegar lo último que dicté | **`Ctrl` + `Alt` + `Z`** |
| Cerrar la app | Clic derecho en el icono de la bandeja → **Salir** |

**Los sonidos te dicen en qué modo estás:** un bip agudo = grabando normal. Un bip más
grave y largo = manos libres. Un bip grave corto = no se detectó voz.

Mientras hablas aparece un **indicador flotante** abajo al centro con un
ecualizador que reacciona a tu voz.

> **El micrófono queda encendido todo el tiempo** que la app esté abierta, así que
> verás el indicador de "micrófono en uso" de tu sistema siempre activo. Es a
> propósito: abrir el micrófono en el instante de pulsar la tecla se comía las
> primeras sílabas de cada frase. El audio solo vive unos milisegundos en memoria y se
> descarta solo — nunca se guarda en disco ni sale de tu computadora. Si prefieres el
> comportamiento anterior, pon `WHISPERFLOW_MIC_ALWAYS_ON=0` en el archivo `.env`.

---

## Enséñale tus palabras

Esto es lo que más mejora la calidad y casi nadie lo hace. Abre **`dictionary.txt`**
(en la carpeta del proyecto) con cualquier editor de texto y agrega los nombres,
marcas y jerga que uses seguido:

```
Coolify
Hugging Face
n8n
```

Y si notas que **siempre** transcribe mal lo mismo, corrígelo con una flecha:

```
clod => Claude
sas => SaaS
```

El archivo **se relee en cada dictado**: guardas, dictas, y ya está — no hace falta
reiniciar nada.

Dos cosas que ayudan:

- **Pon primero lo más importante.** Como pista previa al modelo solo caben unos 800
  caracteres, así que pasados ~60 términos los últimos ya no se le adelantan al
  modelo (se siguen corrigiendo después, pero acierta menos "de una").
- **`dictionary.txt` es tuyo y no se sube a ningún lado** — está excluido del control
  de versiones justamente porque suele llenarse de nombres de clientes. La plantilla
  versionada es `dictionary.example.txt`.

---

## Ajustes (archivo `.env`)

Todo se configura en un archivo llamado **`.env`** en la carpeta del proyecto. El
instalador te crea uno; para ver todas las opciones con su explicación, abre
`.env.example`.

Lo que más se toca:

| Si quieres… | Cambia |
|---|---|
| Que transcriba mejor (y algo más lento) | `WHISPERFLOW_MODEL_SIZE=medium` o `large-v3` |
| Que vaya más rápido (o no tienes GPU) | `WHISPERFLOW_MODEL_SIZE=small` |
| Dictar en otro idioma | `WHISPERFLOW_LANGUAGE=en` |
| Que el micrófono no quede siempre abierto | `WHISPERFLOW_MIC_ALWAYS_ON=0` |
| Cambiar los atajos | `WHISPERFLOW_PTT_KEYS=super,ctrl` |

Después de editar `.env` hay que **cerrar y volver a abrir la app** para que tome los
cambios.

### ¿Qué modelo me conviene?

Medido en una laptop con RTX 4050, dictando en español con vocabulario técnico:

| modelo | errores | espera por frase | memoria de video |
|---|---|---|---|
| `small` | 7.8 % | 0.48 s | 554 MB |
| `medium` | **2.3 %** | 0.94 s | 1472 MB |
| `large-v3-turbo` | 5.9 % | 0.68 s | 1574 MB |
| `large-v3` | 3.9 % | 1.41 s | 2976 MB |

`medium` es el default porque comete **tres veces menos errores que `small`** por medio
segundo más de espera. **Sin tarjeta NVIDIA la cuenta se invierte** y conviene `small`.

Puedes medirlo tú mismo, con tu voz y tu micrófono, que es lo único que decide de
verdad:

```
python scripts/bench_models.py --record --audio-dir bench_audio
```

Te va mostrando frases para leer en voz alta y después compara todos los modelos sobre
esas grabaciones.

---

## Que arranque solo al encender la computadora

**Windows:**

```
.\venv\Scripts\python.exe install_startup.py
```

Para quitarlo, lo mismo con `--remove` al final. En Mac y Linux, `install.sh` ya te lo
ofrece durante la instalación.

---

## Cuando algo no funciona

### Pulso `Ctrl` + `Win` y no pasa nada

1. **¿Está corriendo?** Busca el icono en la bandeja del sistema. Si no está, la app
   se cerró.
2. **¿Terminó de cargar el modelo?** Si el icono todavía dice "cargando modelo…", el
   dictado está bloqueado a propósito. Suena un bip grave si intentas.
3. **¿Hay otra app usando el mismo atajo?** Si tienes Wispr Flow o similar instalado,
   se pelean por `Ctrl`+`Win`. Cierra uno de los dos.

### Se cierra sola o no arranca

Lánzala desde PowerShell guardando los mensajes en un archivo, y mira qué dice:

```
.\venv\Scripts\python.exe whisperflow.py > debug.log 2> debug_err.log
```

Abre `debug_err.log`: ahí está el error real. Con `pythonw.exe` no verías nada porque
no tiene consola.

### Transcribe frases cortadas al principio

No debería pasar con el micrófono siempre armado. Si lo pusiste en
`WHISPERFLOW_MIC_ALWAYS_ON=0`, vuelve a `1`: abrir el micrófono en el momento de
pulsar cuesta más de 100 milisegundos y ahí se pierden las primeras sílabas.

### Dice "no se detectó voz" aunque hablé, o el indicador dice "sin señal del micrófono"

**Antes de tocar ningún ajuste, mide tu micrófono.** En la mayoría de los casos no es
la app: es que el micrófono entrega demasiada poca señal.

```
python scripts/diagnostico_microfono.py
```

Habla sin parar mientras corre. Mide **todas** tus entradas y te dice cuál sirve, más
el arreglo del portátil canal por canal. Buscas picos de **0.1–0.2**; por debajo de
**0.05** la transcripción empieza a fallar aunque el texto salga.

Si tu mejor micrófono no llega a ese nivel, el problema está en el sistema: revisa la
tecla de silenciar micrófono del portátil (suele ser F4 u F8), Privacidad y seguridad
→ Micrófono, el "Aumento de micrófono" en las propiedades del dispositivo, y desactiva
las mejoras de audio, que a veces se comen la voz tratándola como ruido.

Solo si el nivel es sano y aun así te rechaza el dictado, baja el umbral en `.env`:

```
WHISPERFLOW_VAD_THRESHOLD=0.004
```

### Transcribe mal, o cambia palabras que dije bien

Puede ser el diccionario trabajando en tu contra. Un término mal elegido no falla de
forma visible: **reescribe frases correctas** y parece que el modelo transcribe mal.

```
python scripts/auditar_diccionario.py
```

Prueba tu diccionario contra tu **propio historial de dictados** y te dice qué
términos estarían corrompiendo texto que ya estaba bien, con nombre y frecuencia.

La regla: los términos son para **nombres propios y jerga** que el modelo no conoce.
Para cambiar una cosa concreta por otra, usa un alias (`mal => bien`), que es exacto y
no se dispara por parecido. Nunca pongas como término una palabra corriente del
idioma — atraerá hacia sí todas las que se le parezcan.

### Escribe cosas raras cuando no hablo

Es un defecto conocido de Whisper: sobre silencio inventa texto. Si te pasa, **sube**
el umbral (`WHISPERFLOW_VAD_THRESHOLD=0.015`), que es lo contrario del caso anterior.

### Va lentísimo

Probablemente está usando el procesador en vez de la tarjeta gráfica. Míralo en
`debug.log`: debe decir `cargado en cuda/float16`. Si dice `cpu/int8`, cambia a
`WHISPERFLOW_MODEL_SIZE=small` en `.env`.

### La descarga del modelo falla con "WinError 1314"

Ya está resuelto en el código, pero si te aparece con una versión vieja: es que
Windows bloquea los enlaces simbólicos que usa la caché de modelos. Actualiza el
proyecto a la última versión.

### El texto se pega en el sitio equivocado

Pasa si al terminar de dictar no había ningún campo de texto con el foco. Para eso
está **`Ctrl` + `Alt` + `Z`**: pon el cursor donde querías y púlsalo. Si lo pulsas
varias veces seguidas va retrocediendo por los últimos 3 dictados.

---

## ¿Dudas?

Este proyecto lo mantiene la comunidad
**[Vibe Community VIP](https://www.skool.com/vibe-community-vip)**. Ahí hay soporte,
guías y novedades.

El proyecto está pensado para que lo modifiques. Si usas un agente de código como
Claude Code, la carpeta incluye un `CLAUDE.md` con todo el contexto técnico: abre una
terminal ahí, escribe `claude` y pídele el cambio que quieras en español.
