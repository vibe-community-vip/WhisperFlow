# -*- coding: utf-8 -*-
"""Compara modelos locales de Whisper en ESTA máquina: exactitud (WER) y latencia.

Para qué sirve: elegir el modelo con evidencia en vez de por fama. El modelo más
grande no siempre conviene — si tarda 4 s en una frase de 5 s, el dictado deja de
sentirse instantáneo. Este script mide las dos cosas sobre el mismo audio.

Uso
---
1) Con audio propio (**lo más fiable**: es tu voz, tu micrófono, tu cuarto)::

       python scripts/bench_models.py --record --audio-dir bench_audio

   Va mostrando frases para que las leas en voz alta; Enter empieza a grabar,
   Enter otra vez corta. Queda todo en ``--audio-dir`` y se puede reutilizar
   después sin volver a grabar (omitiendo ``--record``).

2) Con audio ya grabado::

       python scripts/bench_models.py --audio-dir bench_audio

   La carpeta necesita ``frases.txt`` (una frase de referencia por línea) y los
   WAV ``frase_00.wav``, ``frase_01.wav``, … en el mismo orden.

Opciones útiles::

    --models small,medium,large-v3,large-v3-turbo   # qué comparar
    --noise 0.004      # suma ruido blanco: separa a los modelos mucho más que el
                       # audio limpio, y se parece más a dictar con ventilador/aire
    --repeat 2         # promedia la latencia sobre varias corridas

Notas
-----
* La primera vez que aparece un modelo nuevo, se descarga de Hugging Face.
* El WER se calcula sobre texto normalizado (minúsculas, sin puntuación) pero
  **con acentos**: en español la tilde es parte de la palabra.
* El diccionario del proyecto se pasa como ``initial_prompt``, igual que en la
  app, para que la comparación refleje el uso real.
"""
import argparse
import gc
import os
import sys
import time
import unicodedata
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from whisperflow.core.dictionary import load_dictionary, build_initial_prompt  # noqa: E402

SAMPLE_RATE = 16000
DEFAULT_MODELS = ["small", "medium", "large-v3", "large-v3-turbo"]


# --- WER -------------------------------------------------------------------
def normalize(text):
    """Minúsculas, sin puntuación, espacios colapsados. Los acentos SE MANTIENEN."""
    text = text.lower().strip()
    out = []
    for ch in text:
        if ch.isalnum() or ch.isspace():
            out.append(ch)
        elif unicodedata.category(ch).startswith("P"):
            out.append(" ")
        else:
            out.append(ch)
    return " ".join("".join(out).split())


def wer(reference, hypothesis):
    """Word Error Rate = (sustituciones + inserciones + borrados) / palabras de referencia."""
    ref = normalize(reference).split()
    hyp = normalize(hypothesis).split()
    if not ref:
        return 0.0 if not hyp else 1.0
    # Distancia de edición por palabras (Levenshtein, una fila a la vez).
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i]
        for j, h in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1,          # borrado
                           cur[j - 1] + 1,        # inserción
                           prev[j - 1] + (r != h)))  # sustitución
        prev = cur
    return prev[-1] / len(ref)


# --- audio -----------------------------------------------------------------
def read_wav(path):
    """Lee un WAV a float32 mono 16 kHz (remuestreo lineal si hace falta)."""
    with wave.open(path, "rb") as wf:
        n_ch, width, rate, n = wf.getnchannels(), wf.getsampwidth(), wf.getframerate(), wf.getnframes()
        raw = wf.readframes(n)
    dtype = {1: np.uint8, 2: np.int16, 4: np.int32}[width]
    audio = np.frombuffer(raw, dtype=dtype).astype(np.float32)
    audio /= float(2 ** (8 * width - 1))
    if width == 1:
        audio -= 1.0
    if n_ch > 1:
        audio = audio.reshape(-1, n_ch).mean(axis=1)
    if rate != SAMPLE_RATE:
        idx = np.linspace(0, len(audio) - 1, int(len(audio) * SAMPLE_RATE / rate))
        audio = np.interp(idx, np.arange(len(audio)), audio).astype(np.float32)
    return audio


def write_wav(path, audio):
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())


def record_dataset(audio_dir, phrases):
    """Graba cada frase leída en voz alta. Enter para empezar, Enter para cortar."""
    import sounddevice as sd
    import threading

    print("\nGrabación: se muestra una frase, Enter empieza, Enter corta.\n")
    for i, phrase in enumerate(phrases):
        path = os.path.join(audio_dir, "frase_%02d.wav" % i)
        print(f"\n[{i + 1}/{len(phrases)}] {phrase}")
        input("    Enter para grabar... ")
        frames = []
        stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                callback=lambda d, f, t, s: frames.append(d.copy()))
        stream.start()
        stop = threading.Event()
        threading.Thread(target=lambda: (input("    grabando — Enter para cortar... "),
                                         stop.set()), daemon=True).start()
        while not stop.is_set():
            time.sleep(0.05)
        stream.stop()
        stream.close()
        audio = np.concatenate(frames, axis=0).flatten() if frames else np.zeros(1, "float32")
        write_wav(path, audio)
        print(f"    guardado {path} ({len(audio) / SAMPLE_RATE:.1f} s)")


# --- benchmark -------------------------------------------------------------
def gpu_mem_mb():
    try:
        import subprocess
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5)
        return int(out.stdout.strip().splitlines()[0])
    except Exception:
        return None


def bench_model(name, clips, initial_prompt, repeat, device, compute_type):
    from faster_whisper import WhisperModel

    base_mem = gpu_mem_mb()
    t0 = time.perf_counter()
    model = WhisperModel(name, device=device, compute_type=compute_type)
    load_s = time.perf_counter() - t0

    # Una pasada de calentamiento: la primera inferencia paga la construcción de
    # kernels CUDA y falsearía la latencia de la primera frase.
    model.transcribe(clips[0][1], language="es", beam_size=5)
    peak_mem = gpu_mem_mb()

    rows = []
    for ref, audio in clips:
        best_text, times = None, []
        for _ in range(repeat):
            t0 = time.perf_counter()
            segments, _ = model.transcribe(audio, language="es", beam_size=5,
                                           vad_filter=True, condition_on_previous_text=False,
                                           initial_prompt=initial_prompt)
            text = "".join(s.text for s in segments).strip()
            times.append(time.perf_counter() - t0)
            best_text = text
        rows.append({"ref": ref, "hyp": best_text, "wer": wer(ref, best_text),
                     "sec": float(np.median(times)),
                     "audio_sec": len(audio) / SAMPLE_RATE})

    del model
    gc.collect()
    return {"load_s": load_s, "rows": rows,
            "vram_mb": (peak_mem - base_mem) if (peak_mem and base_mem) else None}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audio-dir", default="bench_audio")
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS))
    ap.add_argument("--record", action="store_true", help="grabar las frases con tu voz")
    ap.add_argument("--noise", type=float, default=0.0, help="ruido blanco añadido (RMS, ej. 0.004)")
    ap.add_argument("--repeat", type=int, default=1, help="corridas por frase (mediana de latencia)")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--compute-type", default="float16")
    ap.add_argument("--show-text", action="store_true", help="imprimir cada transcripción")
    args = ap.parse_args()

    audio_dir = os.path.abspath(args.audio_dir)
    phrases_path = os.path.join(audio_dir, "frases.txt")
    if not os.path.exists(phrases_path):
        sys.exit(f"falta {phrases_path} (una frase de referencia por línea)")
    with open(phrases_path, encoding="utf-8") as f:
        phrases = [l.strip() for l in f if l.strip()]

    if args.record:
        os.makedirs(audio_dir, exist_ok=True)
        record_dataset(audio_dir, phrases)

    clips = []
    rng = np.random.default_rng(0)
    for i, phrase in enumerate(phrases):
        path = os.path.join(audio_dir, "frase_%02d.wav" % i)
        if not os.path.exists(path):
            sys.exit(f"falta {path} — corré con --record o generá el audio antes")
        audio = read_wav(path)
        if args.noise > 0:
            audio = np.clip(audio + rng.normal(0, args.noise, len(audio)).astype(np.float32), -1, 1)
        clips.append((phrase, audio))

    terms, _ = load_dictionary()
    initial_prompt = build_initial_prompt(terms)
    total_audio = sum(len(a) for _, a in clips) / SAMPLE_RATE
    print(f"{len(clips)} frases · {total_audio:.1f} s de audio · ruido={args.noise} · "
          f"{args.device}/{args.compute_type} · diccionario: {len(terms)} términos\n")

    results = {}
    for name in [m.strip() for m in args.models.split(",") if m.strip()]:
        print(f"--- {name} ---", flush=True)
        try:
            res = bench_model(name, clips, initial_prompt, args.repeat,
                              args.device, args.compute_type)
        except Exception as e:
            print(f"    FALLÓ: {str(e)[:200]}\n", flush=True)
            continue
        results[name] = res
        wers = [r["wer"] for r in res["rows"]]
        secs = [r["sec"] for r in res["rows"]]
        rtf = sum(secs) / total_audio
        print(f"    WER medio {100 * np.mean(wers):5.2f}%   peor frase {100 * max(wers):5.2f}%   "
              f"frases perfectas {sum(1 for w in wers if w == 0)}/{len(wers)}")
        print(f"    latencia mediana {np.median(secs):.2f} s   p90 {np.percentile(secs, 90):.2f} s   "
              f"x tiempo real {rtf:.2f}   carga {res['load_s']:.1f} s   VRAM ~{res['vram_mb']} MB\n",
              flush=True)
        if args.show_text:
            for r in res["rows"]:
                if r["wer"] > 0:
                    print(f"      ref: {r['ref']}")
                    print(f"      hyp: {r['hyp']}   (WER {100 * r['wer']:.1f}%)\n")

    if len(results) > 1:
        print("=" * 78)
        print(f"{'modelo':<20}{'WER':>9}{'latencia med':>15}{'p90':>9}{'VRAM':>10}")
        print("-" * 78)
        for name, res in results.items():
            wers = [r["wer"] for r in res["rows"]]
            secs = [r["sec"] for r in res["rows"]]
            print(f"{name:<20}{100 * np.mean(wers):8.2f}%{np.median(secs):14.2f}s"
                  f"{np.percentile(secs, 90):8.2f}s{str(res['vram_mb']) + ' MB':>10}")
        best = min(results.items(), key=lambda kv: np.mean([r["wer"] for r in kv[1]["rows"]]))
        print(f"\nmenor WER: {best[0]}")


if __name__ == "__main__":
    main()
