# Notas de la versión 1.0.0 — WhisperFlow

**Fecha:** 20 de julio de 2026
**Tag:** [`v1.0.0`](https://github.com/vibe-community-vip/WhisperFlow/releases/tag/v1.0.0)
**Licencia:** MIT

Primera release de **WhisperFlow**: dictado por voz **local/offline**
(faster-whisper / MLX), push-to-talk y modo manos libres por atajo global,
indicador flotante animado y reescritura opcional de tono vía LLM
(**Ollama local u OpenAI**).

A partir del monolito original (Windows-only), esta versión lo convierte en una
herramienta **multiplataforma: Windows, macOS y Linux**.

## Novedades destacadas

- **Multiplataforma** — Windows, macOS (Apple Silicon con GPU vía MLX) y Linux
  (X11; Wayland *best-effort*).
- **GPU Apple Silicon** — motor MLX con el modelo
  `mlx-community/whisper-large-v3-mlx-4bit` y fallback automático a CPU si falla.
- **VAD por energía** — descarta el audio mudo antes de transcribir para que
  Whisper no alucine texto repetido sobre silencio
  (p. ej. `"arrendamos arrendamos…"`).
- **Reescritura de tono con LLM** — Ollama local (auto-detección), OpenAI o
  ninguno, con degradación elegante al texto original si la reescritura falla.
- **Configuración por `.env`** — un único `.env` sirve en los 3 SO; prioridad
  variable del SO > `.env` > defaults históricos.
- **Historial Markdown** de las transcripciones (activo por defecto).
- **Carga perezosa del modelo** — la bandeja aparece al instante y avisa mientras
  carga el modelo en segundo plano.

## Instalación rápida

**macOS / Linux** (Python 3.11–3.13):

```bash
bash install.sh
./venv-mac/bin/python whisperflow.py      # macOS
./venv-linux/bin/python whisperflow.py    # Linux
```

**Windows** (PowerShell, Python 3.12):

```powershell
.\setup.ps1
.\venv\Scripts\python.exe whisperflow.py
```

El instalador crea el venv, instala dependencias, pregunta por el backend de
tono (Ollama / OpenAI / ninguno), escribe el `.env` y configura el arranque
automático opcional.

## Atajos (defaults; todos configurables vía `.env`)

| Plataforma        | Push-to-talk   | Manos libres           | Re-pegar     | Cambiar perfil |
| ----------------- | -------------- | ---------------------- | ------------ | -------------- |
| Windows / Linux (X11) | `Ctrl+Win`  | `Ctrl+Win+Espacio`     | `Ctrl+Alt+Z` | `,`  `.`  `-`  |
| macOS             | `Cmd+Ctrl`     | `Cmd+Ctrl+Espacio`     | `Ctrl+Alt+Z` | `,`  `.`  `-`  |

En macOS las tone-keys (`,`/`.`/`-`) se **suprimen** al escribir (backend
`cgevent` por defecto).

## Requisitos por SO

- **macOS**: permisos de **Accesibilidad** y **Supervisión de entrada**; `pyobjc`.
- **Linux (X11)**: `xclip` + `xdotool`; grupo `input`/udev para `/dev/uinput`.
- **Windows**: sin requisitos adicionales (CUDA opcional para faster-whisper).

## Limitaciones conocidas

- **Wayland** es *best-effort* (hotkeys globales e inyección de `Ctrl+V`
  restringidos por el compositor).
- El **VAD por energía** no separa voz de ruido sostenido (música, ventilador).
- El pegado restaura solo contenido **textual** del portapapeles (no imágenes).
- Sin tests automatizados ni CI: la verificación es manual (ver `CLAUDE.md`).

## Historial completo de cambios

Ver [`CHANGELOG.md`](./CHANGELOG.md).
