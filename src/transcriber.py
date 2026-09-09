import webrtcvad
import numpy as np
import sounddevice as sd
import queue
import threading
import datetime
import logging
import time

import audio_archive
import model_search
from audio_devices import SYSTEM_DEFAULT_INPUT, resolve_input_device  # noqa: F401
from text_filters import is_acceptable

logger = logging.getLogger("Transcriber")

# Global NPU inference lock to prevent background threads from crashing Apple Metal
# when dual microphones capture voice streams simultaneously.
NPU_LOCK = threading.Lock()

def resolve_backend(model_path, initial_prompt=None):
    """Pick the inference entry point for a model id. Returns (kind, callable(audio)->text).

    **There is one backend, and that is a supply-chain decision rather than a simplification.**
    Between 2026-08-11 and 2026-08-17 this dispatched to `mlx_qwen3_asr` as well, because
    `docs/decisions/0009` had chosen `Qwen/Qwen3-ASR-0.6B` on measurement. `docs/decisions/0012`
    withdrew that choice on **R50**: the vendor and the community port are both PRC-origin, which
    is a property no measurement on this repository's fixtures can see. The Qwen branch is gone
    rather than left dormant, because a dormant branch is a model an operator can still configure
    their way into by typing an id into the settings form.

    `NPU_LOCK` is taken at the call site, not here: the lock is the invariant, and a backend that
    acquired it internally would hide that from anyone reading the pipeline.

    **The dispatch rule lives in `model_search.FAMILIES`, not here.** That table also carries the
    files the backend needs and where its candidates are found, which is what the settings screen
    hands to an operator whose configured model has stopped downloading. The `kind` return value
    is kept even though it is now constant: `relisten.py` branches on it, and a caller that stops
    asking which family it got is a caller that will silently do the wrong thing if a second one
    ever returns.

    `initial_prompt` is Whisper's decoder biasing — the replacement for Qwen's `context=`, which
    the re-listening pass used to recover rare proper nouns (**V59**). It is `None` on the live
    path by construction: the live path has no transcript to harvest vocabulary from yet, and a
    prompt is text the decoder can copy out verbatim, which is a false-line source (**R37**).
    """
    # Refused here rather than at the settings screen, because this is the point where something
    # is about to be loaded and it is the only point every caller passes through. `.env` survives
    # a version change, so an operator who configured the removed model still has that id — and
    # its weights are still in their cache, so nothing upstream looks wrong. Measured 2026-08-17:
    # without this the failure is `TypeError: ModelDimensions.__init__() got an unexpected keyword
    # argument 'architectures'`, thrown from inside MLX, naming neither the model nor the reason.
    refusal = model_search.disqualified_reason(model_path)
    if refusal:
        raise ValueError(
            f"{model_path!r} is not usable by this product: {refusal} "
            f"Set ASR_MODEL to an MLX-converted Whisper repository — the shipped default is "
            f"{model_search.FAMILIES[-1]['example']!r}."
        )

    family = model_search.family_for(model_path)
    import mlx_whisper

    def _whisper(audio):
        result = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=model_path,
            fp16=True,
            no_speech_threshold=0.6,
            condition_on_previous_text=False,
            initial_prompt=initial_prompt,
        )
        return (result.get("text") or "").strip()

    return family["id"], _whisper


def release_models():
    """Free the ASR weights so something else can have the memory. Returns MB freed.

    **Stopping capture does not release anything, and this was measured rather than assumed.**
    `mlx_whisper` keeps the loaded model on a class attribute — `transcribe.ModelHolder.model`,
    swapped only when a *different* `path_or_hf_repo` is asked for — so the weights are held by
    the *package*, not by the `Transcriber` objects. Dropping every `Transcriber` frees nothing.

    The same holder is why a second `Transcriber` on the same model path costs +0 MB rather than
    doubling, which **V58** recorded from the outside without naming the mechanism. It is also why
    `model_path` must be cleared alongside `model`: leaving the path behind would let
    `get_model()` believe the cached model is still there and hand back `None`.

    Measured for `mlx-community/whisper-large-v3-turbo` on this machine 2026-08-17 (**V71**);
    the equivalent figure for the model this replaced was 1794.3 MB, held in a different
    package's `LRUCache` and released by the same idea.

    Reaching into a class attribute of another package is deliberate and bounded: the failure
    mode of a version that renames it is an `AttributeError` caught here, logged, and followed by
    a session that simply uses more memory. Nothing depends on this succeeding.

    **Restored 2026-08-14 on a different justification.** It was deleted the day before, when the
    second model it protected against stopped existing. The reason it is back is the operator's
    lifecycle rule: *Stop capture is 退駕* -- the model exists for the duration of a session and
    not one moment longer. The measurement below never stopped being true, which is why the
    deletion commit said the code was one revert away.

    **The trade was shown and affirmed on 2026-08-13** -- the alternative was to
    drop this and let cleanup run alongside 1.8 GB nothing is using, which costs nothing visible
    on the 32 GB machine this was measured on and is not the only machine this runs on. Do not
    remove it as a private-API tidy-up; it was chosen with that cost named.

    The weights reload from the local cache on the next inference, so this is reversible at the
    cost of a warm-up — 2.3 s from a warm weight cache. Call `Transcriber.warm_model()`
    afterwards rather
    than letting the reload land on a speaker's first sentence.
    """
    import mlx.core as mx

    before = mx.get_active_memory()
    cleared = []
    try:
        from mlx_whisper.transcribe import ModelHolder
        ModelHolder.model = None
        ModelHolder.model_path = None
        cleared.append("mlx_whisper")
    except Exception as exc:
        logger.info("[Transcriber] ASR weights not released (%s: %s); "
                    "the session simply uses more memory.", type(exc).__name__, exc)
    mx.clear_cache()
    freed = (before - mx.get_active_memory()) / (1024 * 1024)
    if cleared:
        logger.info("[Transcriber] Released %s: %.0f MB", ", ".join(cleared), freed)
    return freed


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

    # Device naming and resolution live in `audio_devices`, which carries no ASR dependency --
    # the pre-flight panel lists inputs while the model may still be downloading (R25, V19).
    resolve_input_device = staticmethod(resolve_input_device)

    def __init__(self, device_idx, role, buffer_instance,
                 model_path="mlx-community/whisper-large-v3-turbo",
                 device_name=None, gate=None):
        # `gate` is `(enabled, model_id, min_speech_s)` from `voice_gate.settings_from`, or `None`
        # for the behaviour every version before 2026-08-18 had: transcribe every segment. Passed
        # in rather than read here, because `Transcriber` reads no configuration -- `.env` is the
        # app's (R32) and a capture object that consulted it would be a second reader.
        self._gate_enabled, self._gate_model, self._gate_min_speech = gate or (False, "", None)
        self.device_idx = device_idx
        self.device_name = device_name
        self.role = role
        self.buffer = buffer_instance
        self.model_path = model_path
        
        # WebRTCVAD requires 16000Hz, blocks must be 10, 20, or 30ms
        self.sample_rate = 16000
        self.block_size = int(self.sample_rate * 0.03) # 480 frames = 30ms

        # Neural Voice Filter: 0-3 severity. 3 is strictest (filters out typing/ambient noise).
        self.vad = webrtcvad.Vad(3)
        self.audio_queue = queue.Queue(maxsize=3000) # Increased to 90 seconds buffer
        self.inference_queue = queue.Queue() # New queue for async NPU offloading
        self.is_running = False
        self.last_rms = 0.0 # UI volume indicator

        # Durable capture. `None` means retention is not armed for this session, which is the
        # default and the only state Phase 6 ever had (R16). Set by `start()` and by nothing
        # else: the choice is known before the streams open, so the writer never has to be
        # attachable to a running capture.
        self.archive = None
        
        self.backend_kind, self._transcribe = resolve_backend(self.model_path)

        # Pre-load the model safely into the NPU
        with NPU_LOCK:
            logger.info(f"[{self.role}] Preloading {self.backend_kind} model {self.model_path} into NPU...")
            # Trigger NPU memory allocation using a dummy float array
            self._transcribe(np.zeros(16000, dtype=np.float32))

        logger.info(f"[{self.role}] NPU Preloading complete. Ready to transcribe.")

    def warm_model(self):
        """Reload the weights into the NPU after `release_models()` dropped them.

        The same dummy inference `__init__` runs, and for the same reason: it is what forces the
        allocation. Without it the reload lands on the first real segment of the next session,
        which is the one moment the live path owes the speaker a timely answer (R9).
        """
        with NPU_LOCK:
            self._transcribe(np.zeros(16000, dtype=np.float32))
        logger.info(f"[{self.role}] ASR weights reloaded.")
        
    def _audio_callback(self, indata, frames, time_info, status):
        """High-speed non-blocking audio stream callback."""
        if not self.is_running:
            return

        # Convert to WebRTCVAD 16-bit PCM Mono
        audio_int16 = (indata[:, 0] * 32767).astype(np.int16)

        # Calculate RMS for UI visualizer
        rms = np.sqrt(np.mean(indata**2))
        self.last_rms = float(rms)

        # Archive from here, upstream of VAD, and hand it to a queue rather than to disk.
        # **Upstream** because `_processing_thread` discards whatever VAD calls non-speech, so
        # an archive tapped after it would be missing precisely the VAD misjudgements -- the
        # material worth going back to check (R3, R45). **A queue** because a disk write in this
        # callback drops frames, which is not a style preference (AGENTS.md).
        if self.archive is not None:
            self.archive.write(audio_int16)

        try:
            # Check for human frequencies
            is_speech = self.vad.is_speech(audio_int16.tobytes(), self.sample_rate)
        except Exception:
            is_speech = False
            
        try:
            self.audio_queue.put_nowait((audio_int16, is_speech))
        except queue.Full:
            # Emergency drop frame to avoid deadlocks
            logger.warning(f"[{self.role}] Audio queue full! Dropping frame. NPU overloaded?")

    def get_rms(self):
        """Retrieves latest audio strength (0.0 ~ 1.0)"""
        return self.last_rms

    def _processing_thread(self):
        """Background worker: groups VAD speech frames and delegates to Whisper NPU."""
        speech_buffer = []
        silence_frames = 0
        
        # 0.4 s of silence closes a segment. **Measured and chosen, not inherited** -- V66 compared
        # 0.4 / 0.8 / 1.5 s and fixed 8 s windows over ten minutes of real conversation plus 18
        # real non-speech recordings, and the operator kept this value on 2026-08-12.
        #
        # Raising it is the tempting change and it is not free. At 0.8 s the transcript is better
        # on every axis that shows up in a table -- CER 0.1718 against 0.1774, ten false lines
        # against thirteen, 19% less total inference -- and the wait for the first word goes from
        # **3.75 s to 7.84 s**, because a segment cannot be transcribed until it closes. R9 scopes
        # the live path to giving the speaker a *timely* gist, and doubling the lag is the one
        # change that attacks that directly. The table wins are what a reviewer sees; the latency
        # is what the person on the podium feels.
        #
        # Do not raise it past ~1 s in any case: at 1.5 s the median segment lands on the 15 s cap
        # below, so cuts happen on a clock rather than at silence, and CER degrades to 0.2711.
        silence_flush_limit = int(0.4 / 0.03) 
        
        while self.is_running:
            try:
                try:
                    chunk, is_speech = self.audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                
                if is_speech:
                    speech_buffer.append(chunk)
                    silence_frames = 0
                else:
                    silence_frames += 1
                    
                # Maximum length limit for a single recording segment (e.g. 15 seconds) to ensure frequent inference
                max_speech_chunks = int(15.0 / 0.03) # 15 seconds
                
                if (silence_frames >= silence_flush_limit or len(speech_buffer) >= max_speech_chunks) and len(speech_buffer) > 0:
                    
                    # Pack 16-bit frames and convert to float32 for Whisper
                    audio_data = np.concatenate(speech_buffer)
                    audio_float32 = audio_data.astype(np.float32) / 32767.0
                    
                    speech_buffer = []
                    silence_frames = 0
                    
                    # Discard extremely short mechanical noises (< 0.3s)
                    if len(audio_float32) < self.sample_rate * 0.3:
                        continue
                        
                    # **The voice gate sits here, before the queue, not before the model.**
                    # Rejected audio then costs nothing at all: no decode (2235 ms for non-speech,
                    # V75), and no place in `inference_queue` behind which a real utterance waits
                    # -- V81 measured a 3311 ms dwell over ten minutes. Screening inside
                    # `_inference_thread` would still save the decode and would leave the queue
                    # exactly as long.
                    #
                    # It is off unless configured, it fails open, and it costs 32 ms when on
                    # (V82, V83). This is not the audio callback, so a 32 ms call here is allowed;
                    # it would not be there.
                    if self._gate_enabled:
                        import voice_gate
                        if not voice_gate.has_speech(audio_float32, self._gate_model,
                                                     self._gate_min_speech, self.sample_rate):
                            logger.info(f"[{self.role}] Gate: "
                                        f"{len(audio_float32) / self.sample_rate:.2f}s not speech; "
                                        f"not transcribed.")
                            continue

                    # Send prepared audio chunk to the dedicated inference thread instantly.
                    # The timestamp rides along so the worker can report how long this segment
                    # waited: queue dwell is invisible in `Transcribed in`, which starts its clock
                    # after the worker has already picked the segment up. V67 measured contention
                    # on that figure and V66 puts it under 20% of what a speaker waits, so the
                    # remainder has to be found here. `monotonic` because this is a duration.
                    self.inference_queue.put((audio_float32, time.monotonic()))

            except Exception as e:
                logger.error(f"[{self.role}] Exception in VAD looping: {e}. Recovering in 2s...")
                time.sleep(2)
                speech_buffer = []
                silence_frames = 0

    def _inference_thread(self):
        """Dedicated background worker: Processes NPU transcription without blocking audio stream."""
        while self.is_running:
            try:
                try:
                    audio_float32, queued_at = self.inference_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                queue_wait_ms = (time.monotonic() - queued_at) * 1000

                # ======== Core Apple M4 NPU execution ========
                # Three timestamps, not two, so waiting for the accelerator is separable from using
                # it. Every contention figure in this repo -- V56's 2.00x, V67's withdrawn 1.47x,
                # the soak's 1.03x-1.55x band trend -- was *inferred* by labelling calls whose
                # timing windows overlapped, and that label means "overlapped", not "blocked": under
                # NPU_LOCK the call holding the lock is not delayed at all, only the one waiting is.
                # No amount of re-analysis separates them. `lock` measures the wait directly.
                start_time = time.monotonic()
                with NPU_LOCK:
                    lock_acquired = time.monotonic()
                    text = self._transcribe(audio_float32)
                finished = time.monotonic()
                lock_wait_ms = (lock_acquired - start_time) * 1000
                npu_ms = (finished - lock_acquired) * 1000
                # `elapsed_ms` keeps its historical meaning -- lock wait PLUS inference. Five tools
                # parse `Transcribed in <ms>ms` and every latency figure in REQUIREMENTS.md is that
                # quantity; redefining it would silently move the baseline under all of them.
                elapsed_ms = (finished - start_time) * 1000

                # A separate line on purpose: five tools parse `Transcribed in <ms>ms: <text>` with
                # regexes that would swallow anything appended to it. This one is emitted for every
                # segment, including those whose text the filter drops, so the count is the honest
                # denominator rather than the accepted-lines one.
                #
                # `lock` and `npu` are APPENDED rather than inserted. The soak's parser matches this
                # line as a prefix and stops after `inference`, so adding fields at the end leaves
                # it working while inserting between existing ones would break it.
                logger.info(f"[{self.role}] Segment {len(audio_float32) / self.sample_rate:.2f}s: "
                            f"queue {queue_wait_ms:.0f}ms, inference {elapsed_ms:.0f}ms, "
                            f"lock {lock_wait_ms:.0f}ms, npu {npu_ms:.0f}ms")

                # Anti-hallucination: whole-utterance match, never substring. See text_filters.
                if is_acceptable(text):
                    # Append latency to log
                    logger.info(f"[{self.role}] Transcribed in {elapsed_ms:.0f}ms: {text}")
                    self.buffer.add_entry(self.role, text)

            except Exception as e:
                logger.error(f"[{self.role}] Exception in inference thread: {e}")
                time.sleep(2)

    def feed_wav(self, path, realtime=True):
        """Inject a mono WAV into `audio_queue` as if it came from the mic callback.

        Used for V52 / 7.3 lab remeasurement so we do not depend on speaker→mic acoustics
        or BlackHole. Frames are 30 ms; `is_speech` still goes through WebRTC VAD so the
        rest of the pipeline matches production.
        """
        from asr_eval import load_wav_mono_float32

        samples, _sr = load_wav_mono_float32(path, target_sr=self.sample_rate)
        audio = np.asarray(samples, dtype=np.float32)
        block = self.block_size
        pad = (-len(audio)) % block
        if pad:
            audio = np.concatenate([audio, np.zeros(pad, dtype=np.float32)])

        logger.info(f"[{self.role}] Feeding WAV into pipeline: {path} ({len(audio) / self.sample_rate:.1f}s)")
        frame_s = block / float(self.sample_rate)
        # `realtime=True` used to sleep a flat `frame_s` per frame, which does not feed in real
        # time: the per-frame work (RMS, VAD, enqueue) lands on top of every sleep instead of
        # inside it, so the feed runs slow and never recovers. Measured 2026-08-12 -- 100 x
        # sleep(0.03) takes 3.38 s standalone on this machine, i.e. **0.887x**, and a `--realtime`
        # arm sat exactly there (**V67**), which was first misread as CPU starvation. Schedule
        # against a deadline and sleep only the remainder, so per-frame cost is absorbed rather
        # than added. Changed on the operator's instruction; every figure taken with the flat
        # sleep -- **V52** included -- was measured at ~0.89x of the pace it reported.
        next_deadline = time.monotonic()
        for i in range(0, len(audio), block):
            if not self.is_running:
                logger.info(f"[{self.role}] WAV feed interrupted (stopped).")
                return
            frame = audio[i : i + block]
            pcm = (frame * 32767.0).astype(np.int16)
            self.last_rms = float(np.sqrt(np.mean(frame ** 2)))
            try:
                is_speech = self.vad.is_speech(pcm.tobytes(), self.sample_rate)
            except Exception:
                is_speech = False
            try:
                self.audio_queue.put((pcm, is_speech), timeout=1.0)
            except queue.Full:
                logger.warning(f"[{self.role}] Audio queue full during WAV feed; dropping frame.")
            if realtime:
                next_deadline += frame_s
                remaining = next_deadline - time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)
                elif remaining < -1.0:
                    # More than a second behind means the process lost the CPU or the machine
                    # slept. Catching up would feed as fast as the queue accepts and silently turn
                    # a realtime arm into a saturating one -- the load shape that made every
                    # earlier dual-track figure an upper bound (**V56**). Resync and say so, so the
                    # gap appears in the log instead of inside the numbers. The lid closing cost
                    # **V67** 80 minutes and nothing in that run reported it.
                    logger.warning(f"[{self.role}] realtime feed fell {-remaining:.1f}s behind and "
                                   f"is resyncing; the feed was NOT continuous across this gap")
                    next_deadline = time.monotonic()
        logger.info(f"[{self.role}] V52 feed complete")

    def set_device(self, device_name):
        """Point this transcriber at a different input, without touching the loaded model.

        This is deliberately two assignments and nothing else. Constructing a `Transcriber` is
        what preloads the model into the NPU (V33), which takes minutes for a multilingual model,
        so the obvious implementation of "switch microphone" -- build a new one -- would make a
        dropdown change cost a full warm-up. The device is only read when a stream is opened
        (`start`), so changing it before Start needs no teardown at all.

        Refuses while running: an open `sd.InputStream` is bound to the device it was opened
        with, so a silent reassignment would leave the UI naming one microphone while the audio
        came from another.
        """
        if self.is_running:
            raise RuntimeError("set_device() while capture is running; stop the session first")
        idx, resolved = self.resolve_input_device(device_name)
        self.device_name = device_name
        self.device_idx = idx
        return idx, resolved

    def start(self, open_input_stream=True, archive_path=None):
        """Ignites the audio worker thread, inference thread, and optionally the mic stream.

        `archive_path` arms durable capture for this session (R16). It is deliberately a
        parameter of Start rather than a property of the object: retention is a per-Start
        decision the operator has already made on the pre-flight panel, and a writer that could
        be attached mid-capture would produce a file whose start time means nothing.
        """
        # Re-resolve here rather than trusting what was resolved at warm-up. Minutes can pass
        # between the two -- the operator reads the pre-flight panel, arms advisors, plugs in a
        # headset -- and PortAudio's indices are positional, so a device appearing or leaving
        # shifts every index after it. The name is the stable identity (AGENTS.md).
        if self.device_name is not None:
            idx, _ = self.resolve_input_device(self.device_name)
            if idx is not None:
                self.device_idx = idx

        # Opened before `is_running`, so no callback can fire while the file is half-built.
        # A failure here is reported and the session continues without an archive: losing the
        # recording must not lose the meeting (R39). The panel and the session record both say
        # what happened rather than implying a file exists.
        self.archive = None
        if archive_path:
            writer = audio_archive.TrackWriter(archive_path, self.sample_rate, label=self.role)
            if writer.open():
                logger.error("❌ [%s] Audio retention was armed but the file could not be "
                             "opened; this track is not being archived.", self.role)
            else:
                self.archive = writer

        self.is_running = True
        self.thread_vad = threading.Thread(target=self._processing_thread, daemon=True)
        self.thread_inference = threading.Thread(target=self._inference_thread, daemon=True)
        self.thread_vad.start()
        self.thread_inference.start()

        if not open_input_stream:
            logger.info(f"[{self.role}] Input stream skipped (lab WAV feed / no device).")
            return

        # Say what is being opened, before trying. The system-audio path logs every step of
        # publishing its device while this one logged nothing at all, so a session where the
        # microphone produced no lines could not be told apart from a session where the operator
        # simply did not speak -- observed 2026-08-12 during the first web-driven run, where that
        # ambiguity was the entire obstacle to diagnosing it.
        logger.info(f"[{self.role}] Opening input: name={self.device_name!r} "
                    f"index={self.device_idx} rate={self.sample_rate}")
        if self.device_idx is None:
            logger.error(f"[{self.role}] No device resolved for {self.device_name!r}; "
                         f"this track will be silent for the whole session.")
            return

        self.stream = sd.InputStream(
            device=self.device_idx,
            channels=1,
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            dtype=np.float32,
            callback=self._audio_callback
        )
        self.stream.start()
        opened = sd.query_devices(self.device_idx)
        logger.info(f"[{self.role}] Input stream live on [{self.device_idx}] "
                    f"{opened['name']!r} at {self.stream.samplerate:.0f} Hz")

    def stop(self):
        """Safely tears down the pipeline.

        Joins worker threads and waits for `NPU_LOCK` so MLX/Metal completion handlers are
        not still running when the interpreter exits — hard-killing mid-inference aborts with
        `mutex lock failed: Invalid argument` (observed 2026-08-11 during V52 teardown).
        """
        self.is_running = False
        if getattr(self, "stream", None) is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception as exc:
                logger.warning(f"[{self.role}] Error closing input stream: {exc}")
            self.stream = None

        # Finalise the WAV **before** waiting on the workers below, and specifically before
        # waiting on NPU_LOCK, which can hold for a whole inference. Ordering taken from the
        # streaming branch (`docs/decisions/0006`) and it is not obvious: a `wave` file whose
        # header was never rewritten with its final length is a truncated record, and under R45
        # a lost record does not come back. An impatient second Ctrl+C should find this already
        # done.
        if self.archive is not None:
            self.archive.close()

        for thread_name in ("thread_vad", "thread_inference"):
            thread = getattr(self, thread_name, None)
            if thread is not None and thread.is_alive():
                thread.join(timeout=60.0)
                if thread.is_alive():
                    logger.warning(f"[{self.role}] {thread_name} did not exit within 60s")

        # Ensure any in-flight inference finished before process teardown.
        acquired = NPU_LOCK.acquire(timeout=60.0)
        if acquired:
            NPU_LOCK.release()
        else:
            logger.warning(f"[{self.role}] NPU_LOCK still held after stop(); Metal may still be busy")
        logger.info(f"[{self.role}] Pipeline stopped.")
