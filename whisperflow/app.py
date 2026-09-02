# -*- coding: utf-8 -*-
"""Orquestador de WhisperFlow: cablea backends + servicios y corre la bandeja.

La máquina de estados (cuándo grabar/transcribir) vive aquí y es **configurable**
vía ``.env`` (``WHISPERFLOW_PTT_KEYS``/``HANDSFREE_KEY``/``REPASTE_KEYS``). Usa
nombres canónicos de teclas: ``super`` (Win en Win/Linux, Cmd en Mac), ``ctrl``,
``alt``, ``shift``, ``space`` o un carácter. Así una misma configuración sirve en
todos los SO.

El dictado es **uno solo y sin modos**: lo que se dicta es lo que se pega. (Hubo
perfiles de tono "amigable"/"profesional" que reescribían el texto con un LLM; se
quitaron junto con todo el backend de reescritura.)
"""
import os
import sys
import threading

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from whisperflow.core import asr, config, hallucinations, history, recall, tray, vad
from whisperflow.core.recorder import Recorder
from whisperflow.core.config import SAMPLE_RATE
from whisperflow.core.dictionary import (
    load_dictionary, build_initial_prompt, apply_aliases, apply_dictionary_corrections,
)
from whisperflow.backends._selector import select_backends


class Application:
    def __init__(self, backends):
        self.beep = backends["beep"]()
        self.overlay = backends["overlay"]()
        self.hotkey = backends["hotkey"]()
        self.paste = backends["paste"](self.hotkey, self.beep)
        self.recorder = Recorder()
        self.icon = None

        # Atajos configurables (canonical names).
        self.ptt_keys = set(config.PTT_KEYS)
        self.hf_key = config.HANDSFREE_KEY
        self.repaste_keys = list(config.REPASTE_KEYS)

        # Estado de la máquina de grabación.
        self._held = set()                 # teclas ptt actualmente abajo
        self._hf_key_held = False          # evita auto-repetición de la tecla manos-libres
        self._recording_active = False
        self._hands_free = False
        self._state_lock = threading.Lock()

        self.debug = config.DEBUG

        if not self.ptt_keys:
            print("[whisperflow] AVISO: WHISPERFLOW_PTT_KEYS vacío -> no hay push-to-talk.",
                  flush=True)

        self.overlay.start()

    # --- registro de hotkeys ---
    def setup_hotkeys(self):
        self.hotkey.start(self.on_event)
        self.hotkey.register_hotkey(self.repaste_keys, self.recover_last_text)

    # Los backends reportan el nombre de la tecla en el IDIOMA DEL SISTEMA: en un
    # Windows en español, Shift llega como "mayusculas" (verificado con
    # WHISPERFLOW_DEBUG=1). Sin estos alias, WHISPERFLOW_PTT_KEYS=shift no
    # funcionaba fuera de un sistema en inglés.
    _SHIFT_ALIASES = ("shift", "mayus", "mayús", "maiusc", "umschalt", "maj")
    _SUPER_ALIASES = ("windows", "super", "cmd", "command", "ventana")

    @classmethod
    def _normalize(cls, name):
        """Nombre canónico de tecla: super/ctrl/alt/shift/space o el carácter tal cual."""
        n = (name or "").lower().strip()
        if "ctrl" in n or "control" in n:
            return "ctrl"
        if any(a in n for a in cls._SUPER_ALIASES):
            return "super"
        if "alt" in n or "option" in n or "opción" in n:
            return "alt"
        if any(a in n for a in cls._SHIFT_ALIASES):
            return "shift"
        if n in ("space", "espacio", "barra espaciadora"):
            return "space"
        return n

    # --- máquina de estados (PTT + manos libres, config-driven) ---
    def on_event(self, event):
        key = self._normalize(event.name)
        if self.debug:
            print(f"[debug] raw={event.name!r} canonical={key!r} type={event.event_type} "
                  f"held={self._held}", flush=True)
        # Solo procesamos los modificadores del PTT y la tecla de manos libres.
        if key not in self.ptt_keys and key != self.hf_key:
            return

        with self._state_lock:
            if key in self.ptt_keys:
                if event.event_type == "down":
                    self._held.add(key)
                    if self.ptt_keys <= self._held:
                        if not self._recording_active:
                            self._begin_recording("push-to-talk")
                        elif self._hands_free:
                            # Re-presionar los modificadores detiene manos libres.
                            self._stop_and_transcribe()
                else:  # up
                    self._held.discard(key)
                    if self._recording_active and not self._hands_free \
                            and not (self.ptt_keys <= self._held):
                        self._stop_and_transcribe()
                return

            # key == hf_key
            if event.event_type == "down":
                if self._hf_key_held:
                    return  # auto-repetición
                self._hf_key_held = True
                if not (self.ptt_keys <= self._held):
                    return  # la tecla sola no hace nada
                if not self._recording_active and not self._begin_recording("manos libres"):
                    return
                if self._hands_free:
                    self._stop_and_transcribe()
                else:
                    self._hands_free = True
                    # Un solo tono, distinto al de PTT: cancela el bip de inicio si
                    # todavía estaba diferido (ver core/beep_base.py).
                    self.beep.hands_free_on()
                    self.overlay.show("hands_free")
                    print("[whisperflow] modo manos libres activado (atajo de nuevo para detener)",
                          flush=True)
            else:  # up
                self._hf_key_held = False

    def _begin_recording(self, motivo):
        """Arranca la captura. Llamado bajo self._state_lock. Devuelve False si el
        modelo todavía no está listo (el dictado se bloquea hasta entonces)."""
        if not asr.is_loaded():
            self.overlay.show("loading")
            self.beep.no_speech()
            return False
        rescued_ms = self.recorder.start()
        self._recording_active = True
        self.beep.recording_start()
        self.overlay.show("recording")
        print(f"[whisperflow] grabando ({motivo}, pre-roll {rescued_ms:.0f} ms)...", flush=True)
        return True

    def _stop_and_transcribe(self):
        # Llamado bajo self._state_lock.
        audio = self.recorder.stop()
        self._recording_active = False
        self._hands_free = False
        self.overlay.show("processing")
        self.start_transcription(audio)

    def start_transcription(self, audio):
        print("[whisperflow] transcribiendo...", flush=True)
        threading.Thread(target=self.transcribe_and_paste, args=(audio,), daemon=True).start()

    def transcribe_and_paste(self, audio):
        try:
            duration = len(audio) / SAMPLE_RATE
            if duration < 0.25:
                print("[whisperflow] grabación demasiado corta, se ignora", flush=True)
                self.beep.no_speech()
                return
            # VAD por energía: descarta capturas mudas ANTES de transcribir, para
            # evitar que Whisper alucine texto repetido sobre silencio.
            v = vad.evaluate(audio)
            if not v["speech"]:
                print(f"[whisperflow] no se detectó voz (VAD: peak={v['peak']:.4f} "
                      f"umbral={v['threshold']:.4f} tramas_activas={v['active']}/{v['n_frames']})",
                      flush=True)
                self.beep.no_speech()
                return
            terms, aliases = load_dictionary()
            initial_prompt = build_initial_prompt(terms)
            text = asr.transcribe(audio, initial_prompt=initial_prompt)
            # Última red contra el crédito de Amara.org que Whisper alucina sobre
            # audio casi mudo (ver core/hallucinations.py).
            text = hallucinations.strip_known_hallucinations(text)
            if not text:
                print("[whisperflow] no se detectó voz", flush=True)
                self.beep.no_speech()
                return
            text = apply_aliases(text, aliases)
            text = apply_dictionary_corrections(text, terms)

            recall.remember(text)
            history.append(text)
            self.paste.paste(text)
            print(f"[whisperflow] pegado: {text}", flush=True)
        finally:
            self.overlay.hide()

    def recover_last_text(self):
        """Ctrl+Alt+Z: pega la grabación más reciente. Presionado varias veces
        seguidas SIN dictar nada nuevo en medio, retrocede a la anterior (hasta las
        últimas ``recall.MAX_RECALL``). Dictar algo nuevo reinicia el ciclo a la más
        reciente (ver ``transcribe_and_paste`` -> ``recall.remember``)."""
        text, idx, total = recall.recall_next()
        if not text:
            self.beep.no_speech()
            print("[whisperflow] no hay texto previo que recuperar", flush=True)
            return
        self.paste.paste(text)
        print(f"[whisperflow] recuperado ({idx}/{total}): {text}", flush=True)

    def _load_model_in_background(self):
        try:
            asr.ensure_loaded()
        except Exception as e:
            print(f"[whisperflow] FALLO la carga del modelo: {e}. "
                  "El dictado no estará disponible hasta resolverlo.", flush=True)
            return
        if self.icon is not None:
            self.icon.title = f"WhisperFlow local (Ctrl+Win) · {config.MODEL_SIZE}"
            try:
                self.icon.update_menu()
            except Exception:
                pass
        print("[whisperflow] modelo listo.", flush=True)

    def on_quit(self, icon, item):
        # os._exit(0) es intencional (ver CLAUDE.md).
        try:
            self.recorder.close()
        except Exception:
            pass
        try:
            icon.stop()
        except Exception:
            pass
        os._exit(0)

    def run(self):
        self.setup_hotkeys()
        # Micrófono armado desde ya: abrirlo al pulsar el atajo cuesta ~120 ms de
        # audio perdido (ver core/recorder.py).
        self.recorder.arm()
        self.icon = tray.build_icon("WhisperFlow local (cargando modelo…)", self.on_quit)
        if sys.platform == "darwin":
            # macOS: el overlay ya creó Tk en el hilo principal; pystray va detached y el
            # hilo principal queda en el mainloop de Tk (si pystray inicializa NSApplication
            # antes que Tk, este crashea).
            try:
                self.icon.run_detached()
            except Exception as e:
                print(f"[whisperflow] no se pudo iniciar la bandeja en Mac: {e}", flush=True)
        threading.Thread(target=self._load_model_in_background, daemon=True).start()
        print(f"[whisperflow] listo. PTT={'+'.join(sorted(self.ptt_keys))} "
              f"manos-libres=+{self.hf_key} re-pegar={'+'.join(self.repaste_keys)} "
              f"(motor ASR: {config.ASR_ENGINE}, modelo: {config.MODEL_SIZE})", flush=True)
        if sys.platform == "darwin":
            self.overlay.run_mainloop()
        else:
            tray.run_icon(self.icon)


def main():
    backends = select_backends()
    backends["startup_init"]()
    app = Application(backends)
    app.run()
