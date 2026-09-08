# -*- coding: utf-8 -*-
"""Diagnóstico del micrófono: ¿cuál de tus entradas te escucha de verdad?

Para qué sirve: si WhisperFlow dice "no se detectó voz" aunque hablaste, casi
siempre el problema no es la app sino que el micrófono entrega una señal
demasiado débil. Este script mide **todas** las entradas del sistema con la misma
voz y dice cuál sirve, para poder cambiar la predeterminada de Windows con
criterio en vez de a ciegas.

Uso::

    python scripts/diagnostico_microfono.py

Habla en voz normal, sin parar, mientras corre. Cada entrada se mide 5 segundos.

Referencia de niveles (pico, sobre 1.0):
  >= 0.05   dictado sano
  >= 0.008  apenas pasa el filtro de voz; el dictado fallará casi siempre
  <  0.008  la app lo descarta (es el umbral WHISPERFLOW_VAD_THRESHOLD)

El arreglo de micrófonos del portátil se mide además en TODOS sus canales, por si
la mezcla a mono cae sobre un canal mudo y los otros sí tienen señal.
"""
import sys
import time

import numpy as np
import sounddevice as sd

SEGUNDOS = 5.0
UMBRAL_VAD = 0.008
UMBRAL_SANO = 0.05


def medir(idx, canales):
    bloques = []
    try:
        with sd.InputStream(device=idx, samplerate=16000, channels=canales,
                            dtype="float32",
                            callback=lambda d, f, t, s: bloques.append(d.copy())):
            time.sleep(SEGUNDOS)
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:70]}"
    if not bloques:
        return None, "no entregó audio"
    a = np.concatenate(bloques)
    if canales == 1:
        return [float(np.abs(a).max())], None
    return [float(np.abs(a[:, c]).max()) for c in range(canales)], None


def veredicto(pico):
    if pico >= UMBRAL_SANO:
        return "SIRVE"
    if pico >= UMBRAL_VAD:
        return "flojo"
    return "MUDO"


def main():
    entradas, vistos = [], set()
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] < 1:
            continue
        api = sd.query_hostapis(d["hostapi"])["name"]
        if api not in ("MME", "Windows WASAPI"):
            continue          # DirectSound y WDM-KS duplican los mismos micrófonos
        clave = (d["name"].split("(")[0].strip().lower(), api)
        if clave in vistos:
            continue
        vistos.add(clave)
        entradas.append((i, d, api))

    if not entradas:
        sys.exit("No se encontró ninguna entrada de audio.")

    total = SEGUNDOS * (len(entradas) + 1)
    print(f"\nVoy a medir {len(entradas)} entradas, {SEGUNDOS:.0f} s cada una "
          f"(~{total:.0f} s en total).")
    print("HABLA EN VOZ NORMAL, SIN PARAR, hasta que diga FIN.\n")
    for aviso in (3, 2, 1):
        print(f"  empezando en {aviso}...", flush=True)
        time.sleep(1)
    print()

    resultados = []
    for i, d, api in entradas:
        nombre = d["name"].strip()[:38]
        print(f"  midiendo [{i:2}] {nombre:38} {api:14} ... ", end="", flush=True)
        picos, err = medir(i, 1)
        if err:
            print(f"ERROR ({err})")
            continue
        print(f"pico {picos[0]:.4f}  {veredicto(picos[0])}")
        resultados.append((picos[0], i, nombre, api))

    # El arreglo del portátil, canal por canal.
    for i, d, api in entradas:
        if d["max_input_channels"] > 1:
            n = d["max_input_channels"]
            nombre = d["name"].strip()[:38]
            print(f"\n  canales nativos de [{i}] {nombre} ({n} canales):", flush=True)
            picos, err = medir(i, n)
            if err:
                print(f"    ERROR ({err})")
            else:
                for c, p in enumerate(picos):
                    print(f"    canal {c}: pico {p:.4f}  {veredicto(p)}")
            break

    print("\nFIN.\n")
    resultados.sort(reverse=True)
    print("=" * 62)
    if not resultados:
        print("Ninguna entrada devolvió audio.")
        return
    mejor, idx, nombre, api = resultados[0]
    if mejor >= UMBRAL_SANO:
        print(f"El mejor micrófono es: [{idx}] {nombre} ({api})")
        print(f"pico {mejor:.4f} — sirve para dictar.")
        print("\nSi ese NO es tu micrófono predeterminado en Windows, cambialo:")
        print("  Configuración > Sistema > Sonido > Entrada")
        print("y reiniciá WhisperFlow.")
    else:
        print(f"NINGUNA entrada llegó a nivel de dictado (el mejor fue {mejor:.4f},")
        print(f"y hace falta {UMBRAL_SANO}). Eso apunta al sistema, no a la app:")
        print("  1. ¿Tiene el portátil una tecla de silenciar micrófono (suele ser F4")
        print("     o F8, con un icono de micrófono tachado)? Revisá que no esté activa.")
        print("  2. Configuración > Privacidad y seguridad > Micrófono: que esté")
        print("     permitido para aplicaciones de escritorio.")
        print("  3. Panel de control > Sonido > Grabar > tu micrófono > Propiedades >")
        print("     Niveles: subí el volumen y el 'Aumento de micrófono' si aparece.")
        print("  4. En la pestaña 'Avanzado' o 'Mejoras', desactivá las mejoras de")
        print("     audio: la supresión de ruido puede estar comiéndose tu voz.")
        print("  5. Probá un micrófono USB o unos audífonos con micro para descartar")
        print("     un fallo del micrófono integrado.")


if __name__ == "__main__":
    main()
