import threading

class DialogueBuffer:
    def __init__(self, max_history=8):
        """
        滑動窗口對話緩衝區
        max_history: 保留最近的這幾句話，防止 API Token 爆掉
        """
        self.buffer = []
        self.max_history = max_history
        # Thread Lock 防止面試中雙方搶話造成的資料覆蓋 Race Condition
        self.lock = threading.Lock()
        self.current_advice = "等待對話..."
        self.is_thinking = False
        
    def add_message(self, role, text):
        with self.lock:
            # 過濾空白與雜訊句子
            text = text.strip()
            if not text:
                return
            
            # 將最新句子加入緩衝區
            self.buffer.append({"role": role, "text": text})
            
            # 若超過設定上限，彈出最舊的對話（Sliding Window 機制）
            if len(self.buffer) > self.max_history:
                self.buffer.pop(0)

    def set_advice(self, advice, is_thinking=False):
        with self.lock:
            self.current_advice = advice
            self.is_thinking = is_thinking

    def get_advice(self):
        with self.lock:
            return self.current_advice, self.is_thinking

    def get_full_dialogue(self):
        """回傳目前緩衝區內所有結構化資料"""
        with self.lock:
            return list(self.buffer)
            
    def get_formatted_dialogue(self):
        """
        編譯出給 Gemini API 吃的純文字格式。
        例如:
        Manager: What is your experience with ASP?
        Bin: I have 3 years of experience.
        """
        with self.lock:
            formatted = []
            for msg in self.buffer:
                formatted.append(f"{msg['role']}: {msg['text']}")
            return "\n".join(formatted)
            
    def get_last_role(self):
        """回傳緩衝區中最後一個發言者的角色"""
        with self.lock:
            if not self.buffer:
                return None
            return self.buffer[-1]['role']

    def clear(self):
        """清空所有對話記錄，通常在面試結束時使用"""
        with self.lock:
            self.buffer.clear()
