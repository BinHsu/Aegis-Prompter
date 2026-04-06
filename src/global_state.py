import threading
import time
from dialogue_buffer import DialogueBuffer
from gemini_advisor import GeminiAdvisor
from transcriber import Transcriber

class GlobalState:
    """
    ⚡️ Thread-Safe Singleton 全域狀態管理器
    確保所有連線的裝置存取到同一個錄音器與記憶體狀態。
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
        """全局唯一初始化"""
        self.buffer = DialogueBuffer(max_history=8)
        self.advisor = GeminiAdvisor()
        
        self.is_running = False
        self.transcriber_me = None
        self.transcriber_other = None
        
        # 音訊設備狀態
        self.me_name = "未偵測"
        self.other_name = "未偵測"
        
        # 背景 API 輪詢 worker
        self.worker_thread = None
        self.last_dialogue = ""
        self.last_api_call = 0
        
    def start_recording(self):
        """發動錄音程序 (Thread-safe)"""
        with self._lock:
            if self.is_running:
                return False
                
            me_idx, me_name = Transcriber.find_device_index(["MacBook Air Microphone", "Built-in Microphone"], fallback_to_default=True)
            other_idx, other_name = Transcriber.find_device_index(["BlackHole 2ch", "BlackHole"], fallback_to_default=False)
            
            self.me_name = me_name
            self.other_name = other_name
            
            # 建立新的 Session ID 並存檔
            session_id = time.strftime("%Y-%m-%d_%H%M%S")
            self.buffer.start_session(session_id)
            
            # 啟動錄音
            self.transcriber_me = Transcriber(role="您 (Bin)", device_idx=me_idx, buffer_instance=self.buffer)
            self.transcriber_me.start()
            
            if other_idx is not None:
                self.transcriber_other = Transcriber(role="與會者 (對方)", device_idx=other_idx, buffer_instance=self.buffer)
                self.transcriber_other.start()
            else:
                self.transcriber_other = None
                
            self.is_running = True
            
            # 啟動單一 API 背景輪詢 worker
            if not self.worker_thread or not self.worker_thread.is_alive():
                self.worker_thread = threading.Thread(target=self._api_worker_loop, daemon=True)
                self.worker_thread.start()
            
            return True
            
    def stop_recording(self):
        """停止錄音程序 (Thread-safe)"""
        with self._lock:
            if not self.is_running:
                return False
                
            self.is_running = False
            
            if self.transcriber_me:
                self.transcriber_me.stop()
            if self.transcriber_other:
                self.transcriber_other.stop()
                
            return True

    def _api_worker_loop(self):
        """獨立的 API 背景輪詢巡邏者 (防競爭衝突)，取代原先綁定使用者的 app.py polling"""
        while self.is_running:
            current_dialogue = self.buffer.get_formatted_dialogue()
            _, is_thinking = self.buffer.get_advice()
            last_role = self.buffer.get_last_role()
            
            # ⚡️ [產品級優化]：實時偵測「救命小抄」 (零延遲本地匹配)
            # 因為這是全域背景常駐，所以不會漏掉任何一句話
            full_dialogue = self.buffer.get_full_dialogue()
            if full_dialogue:
                last_entry = full_dialogue[-1]
                if last_entry['role'] == "與會者 (對方)":
                    hint = self.advisor.get_local_hint(last_entry['text'])
                    if hint:
                        header, answer = hint
                        self.buffer.set_advice(f"⚡️ [救命小抄命中：{header}]\n\n{answer}", is_thinking=False)
                        print(f"\n⚡️ [小抄命中：{header}]\n{answer}\n", flush=True)
                        
                        # 重抓最新狀態，避免立刻被 Gemini API 洗掉
                        _, is_thinking = self.buffer.get_advice()

            threshold = 0.8 if last_role == "與會者 (對方)" else 1.0
            now = time.time()
            
            if not is_thinking and current_dialogue != self.last_dialogue and len(current_dialogue.strip()) > 0:
                if now - self.last_api_call >= threshold:
                    self.last_api_call = now
                    self.last_dialogue = current_dialogue
                    
                    # 標記進入 AI 思考狀態
                    advice, _ = self.buffer.get_advice()
                    self.buffer.set_advice(advice, is_thinking=True)
                    
                    try:
                        new_advice = self.advisor.analyze_dialogue_sync(current_dialogue)
                        self.buffer.set_advice(new_advice, is_thinking=False)
                        print(f"\n💡 [參謀建議更新]:\n{new_advice}\n", flush=True)
                    except Exception as e:
                        self.buffer.set_advice(f"⚠️ API 錯誤: {e}", is_thinking=False)
                        print(f"\n⚠️ [參謀 API 錯誤]: {e}\n", flush=True)
            
            # 短暫睡眠讓出資源
            time.sleep(0.1)

# ✅ 對外暴露出 @st.cache_resource 所需的簡單函式
import streamlit as st

@st.cache_resource
def get_global_state():
    return GlobalState()
