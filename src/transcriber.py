import webrtcvad
import numpy as np
import sounddevice as sd
import queue
import threading
import mlx_whisper
import datetime

# 加入全域的 NPU 推論鎖，防止雙麥克風同時講話時，兩個跑在背景的 Thread 同時搶用 MLX 資源，導致 Apple Metal 底層崩潰 (Segmentation fault)
NPU_LOCK = threading.Lock()

class Transcriber:
    @staticmethod
    def find_device_index(keywords, fallback_to_default=True):
        """自動偵測音訊設備編號：根據關鍵字順序進行匹配"""
        import sounddevice as sd
        devices = sd.query_devices()
        
        # 1. 精確權重匹配
        for kw in keywords:
            for i, dev in enumerate(devices):
                if kw.lower() in dev['name'].lower() and dev['max_input_channels'] > 0:
                    return i, dev['name']
        
        # 2. 備案：如果都沒找到，且 fallback 為真，則使用系統預設輸入
        if fallback_to_default:
            default_input = sd.default.device[0]
            if default_input >= 0:
                dev_info = sd.query_devices(default_input)
                return default_input, f"{dev_info['name']} (System Default)"
                
        return None, "Not Found"

    def __init__(self, device_idx, role, buffer_instance, model_path="mlx-community/whisper-large-v3-turbo"):
        self.device_idx = device_idx
        self.role = role
        self.buffer = buffer_instance
        self.model_path = model_path
        
        # WebRTCVAD 要求 16000 採樣率，且一次 block 為 10, 20 或 30毫秒
        self.sample_rate = 16000
        self.block_size = int(self.sample_rate * 0.03) # 480 frames = 30ms

        # 初始化神經網路人聲過濾器: 0-3，3 為最嚴格，用來過濾打字聲與工程聲音
        self.vad = webrtcvad.Vad(3)
        self.audio_queue = queue.Queue()
        self.is_running = False
        
        # 關鍵修正：預載模型時必須加鎖，防止兩個 Thread 同時搶用 NPU 導致死鎖
        with NPU_LOCK:
            print(f"[{self.role}] 預載 Whisper 模型... (這可能需要幾秒鐘，依賴外接硬碟讀寫)")
            # 此處會載入模型到 NPU (mlx-whisper 特定行為)
            # 使用 Dummy 固定資料長度來觸發 NPU 權限與模型載入建置
            mlx_whisper.transcribe(np.zeros(16000, dtype=np.float32), path_or_hf_repo=self.model_path)
        
        print(f"[{self.role}] NPU 模型預載完畢！隨時可以錄音。")
        
    def _audio_callback(self, indata, frames, time_info, status):
        """核心錄音回呼函數：此處只做超輕量的 VAD 判定，不可阻塞"""
        if not self.is_running:
            return
            
        # 轉換為 WebRTCVAD 需要的 16-bit PCM Mono
        audio_int16 = (indata[:, 0] * 32767).astype(np.int16)
        
        try:
            # 判斷這 30 毫秒內有沒有人類聲音的頻率
            is_speech = self.vad.is_speech(audio_int16.tobytes(), self.sample_rate)
        except Exception:
            is_speech = False
            
        # 將判斷結果與聲音片段排入隊列，交給背後的轉譯 Thread 處理
        self.audio_queue.put((audio_int16, is_speech))

    def _processing_thread(self):
        """背景工作線程：收集 VAD 篩選過的句子片段，並送給 Whisper 解析"""
        speech_buffer = []
        silence_frames = 0
        
        # 設定「斷句門檻」：連遇 0.45 秒無人聲，就認定一句話講完了 (原本 0.6s)
        silence_flush_limit = int(0.45 / 0.03) 
        
        while self.is_running:
            try:
                # 配合 timeout，避免 stop() 被這行卡死
                chunk, is_speech = self.audio_queue.get(timeout=0.1)
                
                if is_speech:
                    speech_buffer.append(chunk)
                    silence_frames = 0 # 遇人聲，歸零沉默計數器
                else:
                    silence_frames += 1
                    
                # 條件：有一段話存在 buffer，而且我們遇到了明顯的停頓點 (silence_frames 達標)
                if silence_frames >= silence_flush_limit and len(speech_buffer) > 0:
                    
                    # 將整段收集的 int16 陣列合體，轉成正規的 float32 給 Whisper
                    audio_data = np.concatenate(speech_buffer)
                    audio_float32 = audio_data.astype(np.float32) / 32767.0
                    
                    # 重置變數以迎接下一句話
                    speech_buffer = []
                    silence_frames = 0
                    
                    # 太短的聲音大概只是咳嗽或單一雜音敲擊，直接拋棄
                    if len(audio_float32) < self.sample_rate * 0.3:
                        continue
                        
                    # ======== 核心：透過 Apple M4 NPU 進行光速轉譯 ========
                    # 確保同時間只有一個執行緒在使用 NPU
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
                        # [防幻覺機制]: 如果 Whisper 無中生有生出這些雜訊，濾掉
                        hallucinations = ["字幕", "Subtitles", "Amara.org", "Thank you.", "謝謝", "請訂閱"]
                        if not any(h in text for h in hallucinations):
                            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                            print(f"[{timestamp}] 💬 [{self.role}]: {text}", flush=True)
                            self.buffer.add_message(self.role, text)

            except queue.Empty:
                continue

    def start(self):
        """啟動聲音擷取與轉譯執行緒"""
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
        """安全終止所有串流與背景執行緒"""
        self.is_running = False
        if hasattr(self, 'stream'):
            self.stream.stop()
            self.stream.close()
