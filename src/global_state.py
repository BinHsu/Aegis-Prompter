import atexit
import threading
import time
import logging
import os
import advisors
import audio_archive
import postmeeting
from dialogue_buffer import DialogueBuffer
import system_audio
from audio_devices import SYSTEM_DEFAULT_INPUT
from transcriber import Transcriber, release_models

# ===== Configure Global Logging =====
base_dir = os.path.dirname(os.path.dirname(__file__))
log_dir = os.path.join(base_dir, "logs")
os.makedirs(log_dir, exist_ok=True)

# Generate a unique timestamped log file per startup segment
startup_timestamp = time.strftime("%Y-%m-%d_%H%M%S")
log_filename = f"aegis_engine_{startup_timestamp}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(log_dir, log_filename), mode='a')
    ]
)
logger = logging.getLogger("GlobalState")

class GlobalState:
    """
    ⚡️ Thread-Safe Singleton Global State Manager
    Ensures all connected devices/browser sessions access the same audio stream
    and shared memory buffer for zero-latency synchronization.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if not cls._instance:
                cls._instance = super(GlobalState, cls).__new__(cls)
                cls._instance._init_once()
            return cls._instance
            
    def _init_once(self):
        """Global Singleton Initialization.

        Deliberately cheap: no model is loaded and no device is opened here. The environment
        this process runs under was already applied by `bootstrap` before this module was
        imported, so nothing here re-reads `.env`.
        """
        # Distinct from the class-level `_lock`, which `__new__` holds to serialize singleton
        # construction. Warm-up loads models and can run for minutes (V33); holding the
        # construction lock across it would block every other thread calling `GlobalState()` --
        # including the Streamlit script thread, which would freeze the UI exactly while the
        # download and warm-up progress is the only thing worth showing (R23, R39).
        self._state_lock = threading.Lock()

        self.buffer = DialogueBuffer(max_history=15)

        # Which advisor slots this session armed, and the pipeline routing between them (R28).
        # `_retriever` outlives a session on purpose -- it owns the embedding model, and a second
        # meeting must not pay that load again -- while the pipeline is rebuilt per session
        # because arming is a per-meeting choice (R27, R33).
        self.enable_rag = False
        self.enable_llm = False
        self.advisor = None
        self._retriever = None

        self.is_running = False
        self.is_warm = False
        self.transcriber_me = None
        self.transcriber_other = None

        # Audio Device states. `mic_device` is the operator's stored *preference* -- a device
        # name, or SYSTEM_DEFAULT_INPUT for "ask the OS". `me_name` is what that resolved to on
        # this run, which is what the UI shows and what may differ from the preference when the
        # chosen device is unplugged.
        self.mic_device = SYSTEM_DEFAULT_INPUT
        self.me_name = "Not detected"
        self.other_name = "Not detected"

        # Which backend produces the Participant track, decided from capability at warm-up and
        # possibly corrected at Start if the helper then fails (R7, R39). `tap` owns a subprocess;
        # the others own nothing.
        self.audio_backend = system_audio.BACKEND_NONE
        self.audio_backend_detail = ""
        self._tap = None

        # Durable capture for the current session (R16). `archive_dir` is derived from the
        # storage root, so retention can never be "unconfigured" -- only unarmed (R44, R48).
        self.archive_audio = False
        self.archive_dir = ""
        self.archive_paths = {}
        self.session_id = ""


        # Background worker for RAG matching
        self.worker_thread = None
        self.last_dialogue = ""
        self.last_hint_entry = ""

        atexit.register(self._atexit_stop)

    def warm_up(self, asr_model=None, mic_device=None, gate=None):
        """Load the ASR models into the NPU. Touches no audio device, opens no stream.

        Split out of `start_recording` on purpose. Warm-up is minutes for a multilingual model,
        serialized across both instances under `NPU_LOCK` (V33) -- leaving it fused to Start
        would put the whole wait after the operator has already committed to starting. What Start
        still gates is the part that carries the guarantee: opening the streams (R24, R25).
        """
        with self._state_lock:
            if self.is_warm:
                return False

            # The microphone is resolved by name, from the operator's stored preference or --
            # when they have never expressed one -- from whatever macOS calls the default input
            # right now (R26). This replaced a hardcoded `["MacBook Air Microphone",
            # "Built-in Microphone"]`, which matched neither on a MacBook Pro and only worked
            # because the fallback caught it.
            self.mic_device = mic_device or SYSTEM_DEFAULT_INPUT
            me_idx, me_name = Transcriber.resolve_input_device(self.mic_device)
            if me_idx is None:
                logger.warning(
                    "⚠️ [Audio] No input device resolved for %r; the Speaker track will be silent.",
                    self.mic_device,
                )
                me_name = "Not detected"
            # The Participant backend is decided by *capability*, not by looking for its device:
            # the tap's device exists only while the helper runs, and the helper must not run
            # before Start (R25). So warm-up picks the backend and preloads the model for it, and
            # the device is resolved when the stream opens.
            self.audio_backend, self.audio_backend_detail = system_audio.available_backend()
            if self.audio_backend == system_audio.BACKEND_TAP:
                other_idx, other_name = None, system_audio.TAP_DEVICE_NAME
                other_device_name = system_audio.TAP_DEVICE_NAME
            elif self.audio_backend == system_audio.BACKEND_BLACKHOLE:
                other_idx, other_name = system_audio.blackhole_device()
                other_device_name = other_name
            else:
                other_idx, other_name, other_device_name = None, "Not detected", None

            self.me_name = me_name
            self.other_name = other_name

            kwargs = {"model_path": asr_model} if asr_model else {}
            # `(enabled, model_id, min_speech_s)` from `voice_gate.settings_from`, or `None` for
            # the pre-2026-08-18 behaviour of transcribing every segment. Resolved by the caller
            # so `Transcriber` reads no configuration of its own (R32).
            kwargs["gate"] = gate

            # Constructing a Transcriber is what preloads the model into the NPU.
            self.transcriber_me = Transcriber(role="Speaker (You)", device_idx=me_idx,
                                              device_name=self.mic_device,
                                              buffer_instance=self.buffer, **kwargs)

            # Built whenever a backend exists, even though the tap's device does not yet: the
            # constructor's job is to preload the model (V33), and `start()` re-resolves the
            # device by name. Deferring construction to Start would move minutes of NPU work to
            # after the operator has committed.
            if other_device_name is not None:
                self.transcriber_other = Transcriber(role="Participant", device_idx=other_idx,
                                                     device_name=other_device_name,
                                                     buffer_instance=self.buffer, **kwargs)
            else:
                self.transcriber_other = None
                logger.warning("⚠️ [Audio] No system-audio backend available (%s). "
                               "The Participant track will be silent.", self.audio_backend_detail)

            self.is_warm = True
            return True

    def set_microphone(self, mic_device):
        """Change which input feeds the Speaker track. Does not reload the model.

        Separated from warm-up because they have nothing in common but timing: warm-up costs
        minutes of NPU work (V33), and this costs two assignments (`Transcriber.set_device`).
        A dropdown that rebuilt the transcriber would make every glance at the device list
        expensive enough to avoid.

        Returns the resolved device name, which may differ from what was asked for -- the stored
        preference is matched by substring, and `""` means "whatever the OS calls default right
        now". Returns `""` when nothing matched, and the caller is expected to show that rather
        than let the panel keep naming a device that is not there.
        """
        with self._state_lock:
            if self.is_running:
                raise RuntimeError("set_microphone() while capture is running")
            self.mic_device = mic_device or SYSTEM_DEFAULT_INPUT
            if self.transcriber_me is None:
                # Chosen before warm-up finished; `warm_up` will resolve it.
                return ""
            _, resolved = self.transcriber_me.set_device(self.mic_device)
            self.me_name = resolved or "Not detected"
            return resolved

    def start_recording(self, enable_rag=True, enable_llm=False, archive_audio=False,
                        archive_dir=""):
        """Opens the audio streams and begins a session (Thread-safe).

        Requires `warm_up()` to have run -- this is the explicit operator action, and it is the
        only thing that may open a device (R25).
        """
        with self._state_lock:
            if self.is_running:
                return False
            if not self.is_warm:
                raise RuntimeError("start_recording() called before warm_up() completed")

            # Both advisor slots are per-session choices made on the pre-flight panel (R27), so
            # the pipeline is built here rather than at import. The retrieval backend is
            # constructed on first arming and kept, because it owns the embedding model.
            self.enable_rag = bool(enable_rag)
            self.enable_llm = bool(enable_llm)
            if self.enable_rag:
                if self._retriever is None:
                    from local_advisor import LocalAdvisor
                    self._retriever = LocalAdvisor()
                else:
                    # Reopened rather than rebuilt: `stop_recording` released the collection's
                    # exclusive lock so the panel and `build_index.py` could reach it between
                    # meetings, but the embedding model -- the part that costs -- is still loaded.
                    self._retriever.open()
            if self.advisor is not None:
                self.advisor.shutdown()
            self.advisor = advisors.build_advisor(
                settings=os.environ,
                enable_rag=self.enable_rag,
                enable_llm=self.enable_llm,
                on_advice=self._publish_advice,
                retriever=self._retriever if self.enable_rag else None,
            )
            if self.advisor is None:
                logger.warning("🛑 [Config] No advisor armed for this session. "
                               "Pure transcription mode.")

            # Retention is decided before the streams open, so the writers are configured once
            # at Start rather than being attachable to a running capture (R16, R27).
            self.archive_audio = bool(archive_audio) and bool(archive_dir)
            self.archive_dir = archive_dir if self.archive_audio else ""
            if archive_audio and not archive_dir:
                logger.error("❌ [Archive] Retention was armed but no archive directory was "
                             "given; this session is NOT being recorded.")

            # Start new session
            session_id = time.strftime("%Y-%m-%d_%H%M%S")
            self.session_id = session_id
            self.archive_paths = {}
            if self.archive_audio:
                self.archive_paths = {
                    audio_archive.TRACK_MIC: audio_archive.track_path(
                        self.archive_dir, session_id, audio_archive.TRACK_MIC),
                    audio_archive.TRACK_SYSTEM: audio_archive.track_path(
                        self.archive_dir, session_id, audio_archive.TRACK_SYSTEM),
                }
            self.buffer.start_session(session_id, retention={
                "armed": self.archive_audio,
                "directory": self.archive_dir,
                "tracks": self.archive_paths,
            })

            # The system-audio tap starts here and nowhere else: creating a tap *is* capture
            # (R25), and this is the explicit operator action. It must also happen before any
            # stream is opened -- publishing the device re-initialises PortAudio, which destroys
            # open streams (V61).
            self._start_system_audio()

            # Lab feed: AEGIS_V52_FEED=/path/to.wav injects into the Speaker track without
            # speaker→mic acoustics (V52 / 7.3). Production Start leaves the env unset.
            v52_feed = (os.environ.get("AEGIS_V52_FEED") or "").strip()
            # Each track gets its own file and they are never mixed (R2). The lab WAV feed
            # bypasses the audio callback entirely, so a V52 run archives nothing -- correct,
            # since the source file already exists on disk.
            self.transcriber_me.start(
                open_input_stream=not bool(v52_feed),
                archive_path=self.archive_paths.get(audio_archive.TRACK_MIC),
            )
            if self.transcriber_other is not None:
                self.transcriber_other.start(
                    archive_path=self.archive_paths.get(audio_archive.TRACK_SYSTEM))
                if self.transcriber_other.device_idx is None:
                    logger.warning("⚠️ [Audio] Participant device %r did not resolve; that track "
                                   "is silent for this session.", self.transcriber_other.device_name)
                    self.other_name = "Not detected"
                else:
                    self.other_name = self.transcriber_other.device_name

            self.is_running = True

            # Ignite local vector matching loop
            if not self.worker_thread or not self.worker_thread.is_alive():
                self.worker_thread = threading.Thread(target=self._local_rag_worker_loop, daemon=True)
                self.worker_thread.start()

            if v52_feed and self.transcriber_me is not None:
                feed_path = v52_feed
                me = self.transcriber_me

                def _v52_feed():
                    try:
                        me.feed_wav(feed_path, realtime=True)
                    except Exception as exc:
                        logger.error(f"V52 WAV feed failed: {exc}")

                threading.Thread(target=_v52_feed, daemon=True, name="v52-feed").start()
                logger.info(f"V52 feed thread armed for {feed_path}")

            return True


    def _start_system_audio(self):
        """Bring up the Participant source. Caller holds `_state_lock`.

        A helper that fails here is a **runtime failure with a visible message** (R39), not a
        reason to abandon the session: the operator is mid-Start and the Speaker track still
        works. So it degrades in one step -- tap, then BlackHole if that machine has it, then a
        silent Participant track that says it is silent. What it must never do is continue while
        claiming the tap is live.
        """
        if self.audio_backend != system_audio.BACKEND_TAP:
            return

        tap = system_audio.SystemAudioTap()
        try:
            tap.start()
            self._tap = tap
            return
        except Exception as exc:
            logger.error("❌ [Audio] System-audio tap failed to start: %s", exc)

        index, name = system_audio.blackhole_device()
        if index is not None and self.transcriber_other is not None:
            self.audio_backend = system_audio.BACKEND_BLACKHOLE
            self.audio_backend_detail = f"{name} (tap failed at Start)"
            self.transcriber_other.set_device(name)
            self.other_name = name
            logger.warning("⚠️ [Audio] Falling back to %s for this session.", name)
            return

        self.audio_backend = system_audio.BACKEND_NONE
        self.audio_backend_detail = "tap failed at Start and BlackHole is not installed"
        self.transcriber_other = None
        self.other_name = "Not detected"

    def _stop_system_audio(self):
        """Tear the helper down. Idempotent, and safe to call when there never was one."""
        if self._tap is not None:
            self._tap.stop()
            self._tap = None

    def stop_recording(self):
        """Gracefully shuts down transcription engines (Thread-safe)"""
        with self._state_lock:
            if not self.is_running:
                return False

            self.is_running = False

            # `Transcriber.stop` finalises its own WAV before waiting on anything slow, so the
            # header is rewritten with its final length even if the process is killed a moment
            # later (R45).
            if self.transcriber_me:
                self.transcriber_me.stop()
            if self.transcriber_other:
                self.transcriber_other.stop()

            self._close_session_record()

            # The advisor's worker may be blocked on a remote host that is not answering, so it
            # is torn down with a bounded join rather than left to a daemon thread: a reply that
            # lands after Stop would write advice into a session that has ended.
            if self.advisor is not None:
                self.advisor.shutdown()

            # Release the knowledge collection's exclusive lock. Held for a session, not for a
            # process -- otherwise the pre-flight panel cannot read its own chunk count after the
            # first meeting, and rebuilding the index means quitting the app.
            if self._retriever is not None:
                self._retriever.close()

            # After the streams, not before: the helper owns the device they were reading from,
            # and destroying it underneath an open stream is how PortAudio is made to hang.
            self._stop_system_audio()

            return True

    def release_engine(self):
        """退駕 — drop the models when the session ends. Returns MB freed.

        The operator's lifecycle rule, 2026-08-14: nothing of ours is in memory except during a
        capture. Stopping does not release anything on its own, because the weights live in the
        ASR package's process-local cache rather than in these objects (measured; see
        `transcriber.release_models`). So the release is explicit, and `is_warm` goes back to
        false so the next Start warms again — 2.3 s from a warm weight cache, paid inside the
        press the operator already committed to.
        """
        with self._state_lock:
            if self.is_running:
                raise RuntimeError("release_engine() while capture is running")
            self.transcriber_me = None
            self.transcriber_other = None
            self.is_warm = False
            return release_models()

    def _close_session_record(self):
        """Finish the transcript: what the archive produced, then the post-meeting prompt.

        Caller holds `_state_lock`, and both writers are already closed. The archive half is
        reported per track including the dropped-block count -- a file that is 40 minutes of a
        60-minute hearing is worse than no file if nothing says so (R45).

        The prompt half is written for **every** session, armed or not. It is an instruction, not
        an action: nothing is executed, no model is loaded and nothing leaves the machine, which
        is exactly why it needs no toggle and no warning.
        """
        summary = {}
        if self.archive_audio:
            for label, transcriber in (("Speaker (You)", self.transcriber_me),
                                       ("Participant", self.transcriber_other)):
                archive = getattr(transcriber, "archive", None) if transcriber else None
                if archive is not None:
                    summary[label] = archive.summary()
            if not summary:
                logger.error("❌ [Archive] Retention was armed but no track was written.")
            for label, info in summary.items():
                logger.info("💾 [Archive] %s: %.1f s at %s (%d dropped)", label,
                            info["seconds"], info["path"], info["dropped_blocks"])

        audio = postmeeting.audio_paths(self.archive_dir, self.session_id)
        self.buffer.finish_session(
            summary or None,
            prompt_block=postmeeting.render_block(session_id=self.session_id, audio=audio),
        )

    def _atexit_stop(self):
        """Best-effort stop so Streamlit/process exit does not tear down MLX mid-callback."""
        try:
            if self.is_running:
                logger.info("atexit: stopping capture before interpreter exit")
                self.stop_recording()
        except Exception as exc:
            logger.warning(f"atexit stop failed: {exc}")
        try:
            # Unconditionally, and after the above: `stop_recording` returns early when
            # `is_running` is false, which is exactly the state left behind if Start raised
            # between publishing the tap and marking the session live. The helper destroys its
            # own aggregate device when signalled, so the cost of missing this is a phantom input
            # device on the operator's Mac until they reboot.
            self._stop_system_audio()
        except Exception as exc:
            logger.warning(f"atexit tap teardown failed: {exc}")

    def _publish_advice(self, advice):
        """Write one piece of advisor output into its own slot (V24).

        Passed to the pipeline as a callback so the pipeline never touches the buffer directly:
        it is called from the poll thread for retrieved cues and from the pipeline's own worker
        thread for generated ones, and the buffer's lock is what makes that safe.
        """
        self.buffer.set_advice(advice.text, source=advice.source, vendor=advice.vendor,
                               score=advice.score)
        logger.info("💡 [Advisor] %s from %s: %s", advice.source, advice.vendor or "-",
                    advice.text)

    def _local_rag_worker_loop(self):
        """
        Background patrol checking for incoming dialogue to hand to the armed advisor slots.

        Still a 0.3 s poll and still synchronous, but only for the local retrieval query, which
        is microseconds. Anything remote is handed to the pipeline's own thread (V27) -- a
        network call inline here would stall the loop that also notices Stop.
        """
        while self.is_running:
            full_dialogue = self.buffer.get_full_dialogue()

            if full_dialogue:
                last_entry = full_dialogue[-1]

                # Advice fires only on the opponent track, and only when this session armed at
                # least one slot. `self.advisor` is rebuilt per session from the pre-flight
                # choices, so its existence *is* the per-meeting gate (R27, R33).
                if last_entry['role'] == "Participant" and self.advisor is not None:
                    # Only process new lines to avoid flooding
                    if self.last_hint_entry != last_entry['text']:
                        self.last_hint_entry = last_entry['text']
                        self.advisor.submit(
                            last_entry['text'],
                            transcript=self.buffer.get_formatted_dialogue(),
                        )

            # Rest briefly to save CPU cycles
            time.sleep(0.3)

# Expose singleton getter for streamlit caching
import streamlit as st

@st.cache_resource
def get_global_state():
    return GlobalState()
