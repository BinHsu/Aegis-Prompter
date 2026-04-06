import threading
import os
import datetime

class DialogueBuffer:
    def __init__(self, max_history=15):
        """
        🛡️ 旗艦版對話緩衝區
        max_history: 保留最近的對話條數
        """
        self.max_history = max_history
        self.dialogue = []  # 存儲 (role, text, timestamp)
        self.advice = "等待對話..."
        self.is_thinking = False
        self.lock = threading.Lock()
        
        # 存檔專用
        self.session_file = None
        self.session_id = None

    def start_session(self, session_id, history_dir="history"):
        """初始化存檔 Session：建立資料夾並寫入標題"""
        if not os.path.exists(history_dir):
            os.makedirs(history_dir)
            
        self.session_id = session_id
        self.session_file = os.path.join(history_dir, f"Meeting_{session_id}.md")
        
        with open(self.session_file, "w", encoding="utf-8") as f:
            f.write(f"# 🛡️ Staff Officer 會議紀錄\n\n")
            f.write(f"- **日期**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"- **Session ID**: {session_id}\n\n")
            f.write(f"---\n\n")
            f.write(f"## 📝 對話劇本與參謀小抄\n\n")

    def add_entry(self, role, text):
        """新增一條對話紀錄，並同步寫入本地 Markdown"""
        text = text.strip()
        if not text:
            return
            
        with self.lock:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            self.dialogue.append({"role": role, "text": text, "time": timestamp})
            
            # 滑動窗口機制
            if len(self.dialogue) > self.max_history:
                self.dialogue.pop(0)

            # 同步寫入本地 Markdown 檔
            if self.session_file:
                try:
                    with open(self.session_file, "a", encoding="utf-8") as f:
                        f.write(f"**[{timestamp}] {role}**: {text}\n\n")
                except:
                    pass

    def set_advice(self, advice, is_thinking=False):
        """更新 AI 建議，並同步存檔"""
        with self.lock:
            self.advice = advice
            self.is_thinking = is_thinking
            
            # 同步將建議寫入存檔 (僅在非「思考中」狀態時寫入)
            if self.session_file and not is_thinking:
                try:
                    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                    with open(self.session_file, "a", encoding="utf-8") as f:
                        f.write(f"> **💡 參謀建議 [{timestamp}]**\n")
                        # 讓建議部分也符合 Markdown 引用格式
                        formatted_advice = advice.replace('\n', '\n> ')
                        f.write(f"> {formatted_advice}\n\n")
                        f.write(f"---\n\n")
                except:
                    pass

    def get_advice(self):
        with self.lock:
            return self.advice, self.is_thinking

    def get_full_dialogue(self):
        """回傳目前緩衝區內所有資料"""
        with self.lock:
            return list(self.dialogue)
            
    def get_formatted_dialogue(self):
        """格式化為 Gemini API 提示詞專用格式"""
        with self.lock:
            formatted = []
            for msg in self.dialogue:
                formatted.append(f"{msg['role']}: {msg['text']}")
            return "\n".join(formatted)

    def get_last_role(self):
        """回傳緩衝區中最後一個發言者的角色"""
        with self.lock:
            if not self.dialogue:
                return None
            return self.dialogue[-1]['role']

    def clear(self):
        """清空對話紀錄"""
        with self.lock:
            self.dialogue.clear()
            self.advice = "等待對話..."
            self.is_thinking = False
