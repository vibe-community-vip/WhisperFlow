# WhisperFlow local

Dictado por voz local, offline y gratis (sin suscripción) para Windows — un
reemplazo casero de Wispr Flow. Transcribe con IA (faster-whisper) corriendo
en tu propia máquina y pega el texto donde tengas el cursor.

Este proyecto es **código fuente editable a propósito**, no un instalador
cerrado. Está pensado para que lo sigas ajustando a tu gusto — a mano, o
pidiéndole los cambios a un agente de código como Claude Code (ver más abajo).

## Requisitos

- Windows 10/11.
- Python 3.12 (https://www.python.org/downloads/ — marca "Add python.exe to PATH" al instalar).
- Opcional: GPU NVIDIA (transcribe más rápido). Sin GPU, usa CPU automáticamente.
- Opcional: una API key de OpenAI (https://platform.openai.com/api-keys) si quieres
  usar los "perfiles de tono" (ver abajo). Sin ella, todo lo demás funciona igual.

## Instalación

1. Copia esta carpeta completa a tu computadora.
2. Clic derecho sobre `setup.ps1` → "Ejecutar con PowerShell" (o desde una
   terminal: `.\setup.ps1`). Esto crea un entorno virtual (`venv\`) e instala
   todo lo necesario. La primera vez tarda varios minutos.
3. (Opcional) Define tu API key de OpenAI como variable de entorno de usuario
   `OPENAI_API_KEY` (Panel de control → Variables de entorno), si quieres los
   perfiles de tono.
4. Corre la app:
   ```
   .\venv\Scripts\python.exe whisperflow.py
   ```
   La primera vez descarga el modelo de Whisper (~500 MB), tarda un poco.
5. (Opcional) Para que arranque solo al iniciar sesión en Windows, en segundo
   plano y sin ventana de consola:
   ```
   .\venv\Scripts\python.exe install_startup.py
   ```
   Para desinstalar ese arranque automático: agrega `--remove` al final.

## Uso

- **Ctrl + Win** — push-to-talk: habla mientras sostienes ambas teclas; al
  soltar cualquiera, transcribe y pega el texto donde tengas el cursor.
- **Ctrl + Win + Espacio** — modo "manos libres": sigue grabando aunque
  sueltes las teclas. Para detener y transcribir, vuelve a presionar
  Ctrl+Win (ya no hace falta tocar Espacio de nuevo), o repite
  Ctrl+Win+Espacio.
- **Ctrl + Alt + Z** — vuelve a pegar el último texto transcrito (útil si no
  había ningún campo de texto con foco cuando dictaste).

Mientras grabas (push-to-talk o manos libres), puedes tocar una vez (sin
soltar nada más) alguna de estas teclas para que el texto pase por un LLM
(OpenAI) antes de pegarse, cambiándole el tono:

- **,** → "Amigable": más cálido, con algún emoji.
- **.** → "Profesional": quita muletillas, directo y técnico.
- **-** → "Normal": cancela el perfil elegido, pega tal cual.

Requiere `OPENAI_API_KEY`; si no está configurada, se pega el texto normal.

Un indicador flotante aparece abajo al centro de la pantalla mientras grabas
o mientras se procesa, con un mini-ecualizador que reacciona al volumen de
tu voz.

## Personalización

- **`dictionary.txt`** — vocabulario propio (nombres, herramientas, jerga)
  para que Whisper transcriba mejor esos términos. Se relee en cada dictado,
  edítalo libremente sin reiniciar la app. Las instrucciones están dentro
  del archivo.
- **Ícono en la bandeja del sistema** — clic derecho → "Salir" para cerrar
  la app.
- Casi cualquier otro comportamiento (atajos, colores del indicador,
  duración mínima de grabación, modelo de Whisper, etc.) es una constante o
  función corta en `whisperflow.py`.

## Editar este proyecto con un agente de código (Claude Code, etc.)

Esta carpeta incluye un archivo `CLAUDE.md` con el contexto técnico del
proyecto (arquitectura, decisiones no obvias, cómo probar cambios). Si tienes
Claude Code instalado, solo abre una terminal en esta carpeta y corre:

```
claude
```

y pídele en español lo que quieras cambiar o agregar (nuevos atajos, otro
idioma, otra voz de indicador, etc.) — el agente ya tiene el contexto
necesario para trabajar sobre el código con seguridad.
