import webrtcvad
import numpy as np
import sounddevice as sd
import queue
import threading
import mlx_whisper
import datetime

# Global NPU inference lock to prevent background threads from crashing Apple Metal
# when dual microphones capture voice streams simultaneously.
NPU_LOCK = threading.Lock()

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

    def __init__(self, device_idx, role, buffer_instance, model_path="mlx-community/distil-whisper-large-v3"):
        self.device_idx = device_idx
        self.role = role
        self.buffer = buffer_instance
        self.model_path = model_path
        
        # WebRTCVAD requires 16000Hz, blocks must be 10, 20, or 30ms
        self.sample_rate = 16000
        self.block_size = int(self.sample_rate * 0.03) # 480 frames = 30ms

        # Neural Voice Filter: 0-3 severity. 3 is strictest (filters out typing/ambient noise).
        self.vad = webrtcvad.Vad(3)
        self.audio_queue = queue.Queue()
        self.is_running = False
        self.last_rms = 0.0 # UI volume indicator
        
        # Pre-load the MLX model safely into the NPU
        with NPU_LOCK:
            print(f"[{self.role}] Preloading Whisper model into NPU...")
            # Trigger NPU memory allocation using a dummy float array
            mlx_whisper.transcribe(np.zeros(16000, dtype=np.float32), path_or_hf_repo=self.model_path)
        
        print(f"[{self.role}] NPU Preloading complete. Ready to transcribe.")
        
    def _audio_callback(self, indata, frames, time_info, status):
        """High-speed non-blocking audio stream callback."""
        if not self.is_running:
            return
            
        # Convert to WebRTCVAD 16-bit PCM Mono
        audio_int16 = (indata[:, 0] * 32767).astype(np.int16)
        
        # Calculate RMS for UI visualizer
        rms = np.sqrt(np.mean(indata**2))
        self.last_rms = float(rms)
        
        try:
            # Check for human frequencies
            is_speech = self.vad.is_speech(audio_int16.tobytes(), self.sample_rate)
        except Exception:
            is_speech = False
            
        self.audio_queue.put((audio_int16, is_speech))

    def get_rms(self):
        """Retrieves latest audio strength (0.0 ~ 1.0)"""
        return self.last_rms

    def _processing_thread(self):
        """Background worker: groups VAD speech frames and delegates to Whisper NPU."""
        speech_buffer = []
        silence_frames = 0
        
        # Balance threshold: Flush to whisper if 0.4 seconds of total silence is met
        silence_flush_limit = int(0.4 / 0.03) 
        
        while self.is_running:
            try:
                chunk, is_speech = self.audio_queue.get(timeout=0.1)
                
                if is_speech:
                    speech_buffer.append(chunk)
                    silence_frames = 0
                else:
                    silence_frames += 1
                    
                if silence_frames >= silence_flush_limit and len(speech_buffer) > 0:
                    
                    # Pack 16-bit frames and convert to float32 for Whisper
                    audio_data = np.concatenate(speech_buffer)
                    audio_float32 = audio_data.astype(np.float32) / 32767.0
                    
                    speech_buffer = []
                    silence_frames = 0
                    
                    # Discard extremely short mechanical noises (< 0.3s)
                    if len(audio_float32) < self.sample_rate * 0.3:
                        continue
                        
                    # ======== Core Apple M4 NPU execution ========
                    with NPU_LOCK:
                        result = mlx_whisper.transcribe(
                            audio_float32, 
                            path_or_hf_repo=self.model_path,
                            fp16=True, 
                            no_speech_threshold=0.6,
                            condition_on_previous_text=False
                        )
                    
                    text = result.get("text", "").strip()
                    
                    if text and len(text) > 1:
                        # Anti-Hallucination mechanism (common Whisper ghosts)
                        hallucinations = ["字幕", "Subtitles", "Amara.org", "Thank you.", "謝謝", "請訂閱"]
                        if not any(h in text for h in hallucinations):
                            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                            print(f"[{timestamp}] 💬 [{self.role}]: {text}", flush=True)
                            self.buffer.add_entry(self.role, text)

            except queue.Empty:
                continue

    def start(self):
        """Ignites the audio worker thread and microphone stream."""
        self.is_running = True
        self.thread = threading.Thread(target=self._processing_thread, daemon=True)
        self.thread.start()
        
        self.stream = sd.InputStream(
            device=self.device_idx,
            channels=1,
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            dtype=np.float32,
            callback=self._audio_callback
        )
        self.stream.start()

    def stop(self):
        """Safely tears down the pipeline."""
        self.is_running = False
        if hasattr(self, 'stream'):
            self.stream.stop()
            self.stream.close()
