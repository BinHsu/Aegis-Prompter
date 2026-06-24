import numpy as np
import sounddevice as sd
import collections
import threading
import torch
import mlx_whisper
import logging
import time
from silero_vad import load_silero_vad, get_speech_timestamps

logger = logging.getLogger("Transcriber")

# Global NPU inference lock to prevent background threads from crashing Apple Metal
# when dual microphones run Whisper encoder passes simultaneously.
NPU_LOCK = threading.Lock()

# Default model: large-v3-turbo is multilingual (zh+en code-switching) and fast on Apple Silicon.
# mlx ModelHolder is a process-global single-slot cache keyed on path, so BOTH live Transcriber
# instances must use the SAME model_path at runtime (A/B = restart, not concurrent).
DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"

# Short bilingual seed steers Whisper toward zh/en code-switching instead of flip-flopping languages.
DEFAULT_BILINGUAL_PROMPT = "以下是一段中英文混合的對話。The following is a bilingual conversation."

# Whisper ghost phrases that appear on silence/music; filtered before they reach the transcript.
HALLUCINATIONS = ["字幕", "Subtitles", "Amara.org", "Thank you.", "謝謝", "請訂閱"]


class Transcriber:
    @staticmethod
    def find_device_index(keywords, fallback_to_default=True):
        """Auto-detects the hardware audio device index based on keywords."""
        import sounddevice as sd
        devices = sd.query_devices()

        # 1. Exact priority match
        for kw in keywords:
            for i, dev in enumerate(devices):
                if kw.lower() in dev['name'].lower() and dev['max_input_channels'] > 0:
                    return i, dev['name']

        # 2. Fallback to system default input if allowed
        if fallback_to_default:
            default_input = sd.default.device[0]
            if default_input >= 0:
                dev_info = sd.query_devices(default_input)
                return default_input, f"{dev_info['name']} (System Default)"

        return None, "Not Found"

    def __init__(self, device_idx, role, buffer_instance, model_path=DEFAULT_MODEL,
                 language=None, mode="window", window_cap_s=28.0, min_chunk_s=1.0,
                 pause_s=0.5, bilingual_prompt=DEFAULT_BILINGUAL_PROMPT):
        self.device_idx = device_idx
        self.role = role
        self.buffer = buffer_instance
        self.model_path = model_path
        self.language = language          # None = autodetect (once per transcribe() call)
        self.mode = mode                  # "window" (whole-utterance) | "localagreement" (incremental)
        self.bilingual_prompt = bilingual_prompt or ""

        # Whisper runs a fixed 30s-shaped encoder pass; cap the buffer just under 30s so a single
        # transcribe() call never costs more than one encoder pass.
        self.window_cap_s = window_cap_s
        # Minimum new audio (or a detected pause) before re-running in LocalAgreement mode.
        self.min_chunk_s = min_chunk_s
        # Trailing-silence gap that marks an utterance end and triggers a commit.
        self.pause_s = pause_s

        self.sample_rate = 16000
        self.block_size = int(self.sample_rate * 0.03)  # 30ms callback blocks

        # Bounded ring buffer: newest audio wins, oldest is dropped on overflow (no unbounded backlog).
        ring_frames = int(self.window_cap_s * 1.5 / 0.03)
        self.ring = collections.deque(maxlen=ring_frames)

        self.is_running = False
        self.last_rms = 0.0               # UI volume indicator

        # Streaming state (owned by the worker thread)
        self.audio_buffer = np.zeros(0, dtype=np.float32)
        self.committed_text = ""          # tail carried into initial_prompt for context
        self.prev_words = []              # previous hypothesis, for LocalAgreement-2 prefix agreement
        self.committed_count = 0          # words already emitted from the current buffer (LA mode)

        # Silero VAD: one tiny (~2MB) torch model per instance avoids cross-thread contention.
        self.vad_model = load_silero_vad()

        # Pre-load the MLX model into the NPU so the first real utterance isn't slow.
        with NPU_LOCK:
            logger.info(f"[{self.role}] Preloading Whisper model '{self.model_path}' into NPU...")
            mlx_whisper.transcribe(np.zeros(self.sample_rate, dtype=np.float32),
                                   path_or_hf_repo=self.model_path)

        logger.info(f"[{self.role}] NPU preloading complete (mode={self.mode}). Ready to transcribe.")

    def _audio_callback(self, indata, frames, time_info, status):
        """High-speed non-blocking audio stream callback. Only buffers audio; no inference here."""
        if not self.is_running:
            return

        mono = indata[:, 0]
        # RMS for the UI visualizer
        self.last_rms = float(np.sqrt(np.mean(mono ** 2)))

        # Copy: sounddevice reuses indata after the callback returns.
        self.ring.append(mono.astype(np.float32).copy())

    def get_rms(self):
        """Retrieves latest audio strength (0.0 ~ 1.0)"""
        return self.last_rms

    # ---------- helpers ----------

    @staticmethod
    def _join_words(words):
        """Reconstruct text from Whisper word tokens. Latin tokens carry leading spaces; CJK tokens
        do not. Never insert spaces manually — that would break Chinese."""
        return "".join(w.get("word", "") for w in words).strip()

    @staticmethod
    def _norm(word):
        return word.get("word", "").strip().lower()

    def _common_prefix_len(self, prev, curr):
        """LocalAgreement-2: how many leading words agree across two consecutive hypotheses."""
        n = 0
        for a, b in zip(prev, curr):
            na = self._norm(a)
            if na and na == self._norm(b):
                n += 1
            else:
                break
        return n

    def _acceptable(self, text):
        """Drop empty/one-char noise and known Whisper hallucination phrases."""
        if not text or len(text) <= 1:
            return False
        return not any(h in text for h in HALLUCINATIONS)

    def _emit(self, text, elapsed_ms, kind):
        if self._acceptable(text):
            logger.info(f"[{self.role}] {kind} in {elapsed_ms:.0f}ms: {text}")
            self.buffer.add_entry(self.role, text)
            self.committed_text = (self.committed_text + " " + text)[-500:]

    def _emit_window(self, result, elapsed_ms):
        """Whole-utterance commit: emit the full hypothesis once, on a pause or the cap."""
        self._emit(result.get("text", "").strip(), elapsed_ms, "Window commit")

    def _emit_localagreement(self, words, flush, elapsed_ms):
        """Incremental commit. Confirms the longest word prefix that agrees across two consecutive
        hypotheses; on flush (pause/cap) commits the remainder."""
        if flush:
            self._emit(self._join_words(words[self.committed_count:]), elapsed_ms, "LA flush")
            return

        n = self._common_prefix_len(self.prev_words, words)
        if n > self.committed_count:
            self._emit(self._join_words(words[self.committed_count:n]), elapsed_ms, "LA commit")
            self.committed_count = n
        self.prev_words = words

    def _reset_window(self):
        self.audio_buffer = np.zeros(0, dtype=np.float32)
        self.prev_words = []
        self.committed_count = 0

    # ---------- worker ----------

    def _stream_worker(self):
        """Single background worker: accumulates audio, segments with Silero, and runs Whisper over
        coherent windows (replaces the old VAD-fragment + separate-inference-queue design)."""
        sr = self.sample_rate
        last_decision_s = 0.0  # buffer length (s) at the previous transcription

        while self.is_running:
            # 1. Drain newly captured frames into the working buffer.
            drained = []
            while True:
                try:
                    drained.append(self.ring.popleft())
                except IndexError:
                    break
            if drained:
                self.audio_buffer = np.concatenate([self.audio_buffer, *drained])

            buf = self.audio_buffer
            buf_dur = len(buf) / sr
            if buf_dur < self.min_chunk_s:
                time.sleep(0.05)
                continue

            # 2. Segment with Silero VAD (used only to trim silence + detect utterance-end pause;
            #    interior audio is never dropped, so Whisper sees continuous speech).
            try:
                speech = get_speech_timestamps(torch.from_numpy(buf), self.vad_model,
                                               sampling_rate=sr, threshold=0.5)
            except Exception as e:
                logger.error(f"[{self.role}] Silero VAD error: {e}")
                time.sleep(0.1)
                continue

            if not speech:
                # Pure silence — discard so the buffer stays bounded, keep listening.
                if buf_dur >= self.pause_s:
                    self._reset_window()
                    last_decision_s = 0.0
                time.sleep(0.05)
                continue

            # Trim leading silence and re-base the segment offsets.
            lead = speech[0]['start']
            if lead > 0:
                self.audio_buffer = buf = buf[lead:]
                speech = [{'start': s['start'] - lead, 'end': s['end'] - lead} for s in speech]
                buf_dur = len(buf) / sr
                last_decision_s = max(0.0, last_decision_s - lead / sr)

            trailing_s = (len(buf) - speech[-1]['end']) / sr
            pause = trailing_s >= self.pause_s
            cap = buf_dur >= self.window_cap_s
            flush = pause or cap

            # 3. Cadence gate. Window mode only transcribes on a flush; LA mode also re-runs every
            #    min_chunk_s of new audio to confirm an incremental prefix.
            new_audio_s = buf_dur - last_decision_s
            if self.mode == "window":
                should_run = flush
            else:
                should_run = flush or new_audio_s >= self.min_chunk_s
            if not should_run:
                time.sleep(0.05)
                continue
            last_decision_s = buf_dur

            # 4. One encoder pass over the whole (capped) buffer.
            context = (self.bilingual_prompt + " " + self.committed_text[-200:]).strip()
            t0 = time.time()
            try:
                with NPU_LOCK:
                    result = mlx_whisper.transcribe(
                        buf,
                        path_or_hf_repo=self.model_path,
                        word_timestamps=True,
                        language=self.language,
                        initial_prompt=context or None,
                        condition_on_previous_text=False,
                        no_speech_threshold=0.6,
                        hallucination_silence_threshold=2.0,
                        fp16=True,
                    )
            except Exception as e:
                logger.error(f"[{self.role}] Inference error: {e}. Recovering in 0.5s...")
                time.sleep(0.5)
                continue
            elapsed_ms = (time.time() - t0) * 1000

            # 5. Commit.
            if self.mode == "localagreement":
                words = [w for seg in result.get("segments", []) for w in seg.get("words", [])]
                self._emit_localagreement(words, flush, elapsed_ms)
            else:
                self._emit_window(result, elapsed_ms)

            if flush:
                self._reset_window()
                last_decision_s = 0.0

    def start(self):
        """Ignites the stream worker and the microphone stream."""
        self.is_running = True
        self.worker = threading.Thread(target=self._stream_worker, daemon=True)
        self.worker.start()

        self.stream = sd.InputStream(
            device=self.device_idx,
            channels=1,
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            dtype=np.float32,
            callback=self._audio_callback,
        )
        self.stream.start()

    def stop(self):
        """Safely tears down the pipeline."""
        self.is_running = False
        if hasattr(self, 'stream'):
            self.stream.stop()
            self.stream.close()
