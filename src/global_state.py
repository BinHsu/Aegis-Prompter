import threading
import time
import logging
import os
from dialogue_buffer import DialogueBuffer
from local_advisor import LocalAdvisor
from transcriber import Transcriber, resolve_default_model

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
        """Global Singleton Initialization"""
        import os
        from dotenv import load_dotenv
        load_dotenv()
        
        self.buffer = DialogueBuffer(max_history=15)
        
        self.enable_rag = os.environ.get("ENABLE_LOCAL_RAG", "true").lower() == "true"
        self.advisor = LocalAdvisor() if self.enable_rag else None
        if not self.enable_rag:
            logger.warning("🛑 [Config] Local RAG Disabled. Running in Pure Transcription Mode.")

        # Whisper engine knobs (empty values fall back to sensible defaults).
        # IMPORTANT: both mics must share one model_path — mlx caches a single model per process.
        # WHISPER_MODEL wins if set; otherwise fanless Macs (Air) auto-select the lighter FANLESS_MODEL.
        self.whisper_model = resolve_default_model(os.environ.get("WHISPER_MODEL"))
        self.whisper_language = os.environ.get("WHISPER_LANGUAGE", "").strip() or None  # None = autodetect
        self.speaker_mode = os.environ.get("TRANSCRIBE_MODE", "window").strip() or "window"
        
        self.is_running = False
        self.transcriber_me = None
        self.transcriber_other = None

        # Path of the current session's durable-capture directory. cleanup_resources() reads this
        # to spawn the detached offline transcribe+summarize job on exit. _summary_spawned guards
        # against a double-spawn (atexit can fire alongside an explicit stop).
        self.recordings_dir = None
        self._summary_spawned = False
        
        # Audio Device states
        self.me_name = "Not detected"
        self.other_name = "Not detected"
        
        # Background worker for RAG matching
        self.worker_thread = None
        self.last_dialogue = ""
        self.last_hint_entry = ""
        
    def start_recording(self):
        """Ignites the audio transcription engines (Thread-safe)"""
        with self._lock:
            if self.is_running:
                return False
                
            me_idx, me_name = Transcriber.find_device_index(["MacBook Air Microphone", "Built-in Microphone"], fallback_to_default=True)
            other_idx, other_name = Transcriber.find_device_index(["BlackHole 2ch", "BlackHole"], fallback_to_default=False)
            
            self.me_name = me_name
            self.other_name = other_name
            
            # Start new session
            session_id = time.strftime("%Y-%m-%d_%H%M%S")
            self.buffer.start_session(session_id)

            # Per-session directory for durable raw-audio capture (one WAV per track). This path is
            # lossless: the offline retranscribe.py rebuilds a complete transcript from it even if
            # the live ring dropped audio under load.
            recordings_dir = os.path.join(base_dir, "recordings", session_id)
            os.makedirs(recordings_dir, exist_ok=True)
            self.recordings_dir = recordings_dir
            
            # Participant runs LocalAgreement (incremental commit) ONLY when RAG is on, so cues fire
            # within ~2s even mid-monologue. With RAG off there is nothing to feed, so it stays in
            # clean whole-utterance mode like the Speaker mic.
            participant_mode = "localagreement" if self.enable_rag else "window"

            # Ignite transcribers (both share whisper_model — single-slot mlx cache).
            self.transcriber_me = Transcriber(
                role="Speaker (You)", device_idx=me_idx, buffer_instance=self.buffer,
                model_path=self.whisper_model, language=self.whisper_language, mode=self.speaker_mode,
                capture_path=os.path.join(recordings_dir, Transcriber.slug_track_name("Speaker (You)") + ".wav"))
            self.transcriber_me.start()

            if other_idx is not None:
                self.transcriber_other = Transcriber(
                    role="Participant", device_idx=other_idx, buffer_instance=self.buffer,
                    model_path=self.whisper_model, language=self.whisper_language, mode=participant_mode,
                    capture_path=os.path.join(recordings_dir, Transcriber.slug_track_name("Participant") + ".wav"))
                self.transcriber_other.start()
            else:
                self.transcriber_other = None
                
            self.is_running = True
            
            # Ignite local vector matching loop
            if not self.worker_thread or not self.worker_thread.is_alive():
                self.worker_thread = threading.Thread(target=self._local_rag_worker_loop, daemon=True)
                self.worker_thread.start()
            
            return True
            
    def stop_recording(self, flush=True):
        """Gracefully shuts down transcription engines (Thread-safe).

        flush=False (SIGINT/atexit path) finalizes the durable WAVs fast and skips the residual
        Whisper decode, so Ctrl+C returns in seconds. flush=True keeps the live final flush."""
        with self._lock:
            if not self.is_running:
                return False

            self.is_running = False

            if self.transcriber_me:
                self.transcriber_me.stop(flush=flush)
            if self.transcriber_other:
                self.transcriber_other.stop(flush=flush)

            return True

    def _local_rag_worker_loop(self):
        """
        Background patrol checking for incoming dialogue to trigger local RAG hints.
        Completely isolated from network APIs. Zero latency strategy.
        """
        while self.is_running:
            full_dialogue = self.buffer.get_full_dialogue()
            
            if full_dialogue:
                last_entry = full_dialogue[-1]
                
                # We primarily want to trigger defensive hints when the OPPONENT speaks
                if last_entry['role'] == "Participant" and self.advisor:
                    # Only process new lines to avoid flooding
                    if self.last_hint_entry != last_entry['text']:
                        self.last_hint_entry = last_entry['text']
                        
                        # Trigger Vector Similarity Search
                        hint = self.advisor.analyze_dialogue(last_entry['text'])
                        
                        if hint:
                            self.buffer.set_advice(f"🛡️ [Aegis Triggered]\n\n{hint}", is_thinking=False)
                            logger.info(f"🛡️ [Aegis Strike]:\n{hint}")

            # Rest briefly to save CPU cycles (0.1s keeps RAG cue latency inside the ~2s budget)
            time.sleep(0.1)

# Expose singleton getter for streamlit caching
import streamlit as st

@st.cache_resource
def get_global_state():
    return GlobalState()
