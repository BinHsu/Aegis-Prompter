import threading
import os
import datetime

class DialogueBuffer:
    def __init__(self, max_history=15):
        """
        🛡️ Core Dialogue Buffer
        max_history: Max number of recent messages to preserve in memory.
        """
        self.max_history = max_history
        self.dialogue = []  # Stores dicts: {"role": role, "text": text, "time": timestamp}
        self.advice = "Awaiting dialogue..."
        self.is_thinking = False
        self.lock = threading.Lock()
        
        # Session state for persistent saving
        self.session_file = None
        self.session_id = None

    def start_session(self, session_id, history_dir="history"):
        """Initializes logging array and creates a local markdown file for the session."""
        if not os.path.exists(history_dir):
            os.makedirs(history_dir)
            
        self.session_id = session_id
        self.session_file = os.path.join(history_dir, f"Meeting_{session_id}.md")
        
        with open(self.session_file, "w", encoding="utf-8") as f:
            f.write(f"# 🛡️ Staff Officer Meeting Log\n\n")
            f.write(f"- **Date**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"- **Session ID**: {session_id}\n\n")
            f.write(f"---\n\n")
            f.write(f"## 📝 Transcript & Tactical Cues\n\n")

    def add_entry(self, role, text):
        """Appends a new transcription entry to memory and persists to the markdown file."""
        text = text.strip()
        if not text:
            return
            
        with self.lock:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            self.dialogue.append({"role": role, "text": text, "time": timestamp})
            
            # Sliding window logic
            if len(self.dialogue) > self.max_history:
                self.dialogue.pop(0)

            # Persist to local markdown
            if self.session_file:
                try:
                    with open(self.session_file, "a", encoding="utf-8") as f:
                        f.write(f"**[{timestamp}] {role}**: {text}\n\n")
                except:
                    pass

    def set_advice(self, advice, is_thinking=False):
        """Updates the central tactical suggestion and persists it."""
        with self.lock:
            self.advice = advice
            self.is_thinking = is_thinking
            
            # Append advice to log only when a definitive suggestion is made
            if self.session_file and not is_thinking:
                try:
                    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                    with open(self.session_file, "a", encoding="utf-8") as f:
                        f.write(f"> **💡 Staff Proposal [{timestamp}]**\n")
                        # Format as blockquote 
                        formatted_advice = advice.replace('\n', '\n> ')
                        f.write(f"> {formatted_advice}\n\n")
                        f.write(f"---\n\n")
                except:
                    pass

    def get_advice(self):
        """Returns the current advice and the thinking status flag."""
        with self.lock:
            return self.advice, self.is_thinking

    def get_full_dialogue(self):
        """Returns a snapshot of the raw dialogue dictionaries in memory."""
        with self.lock:
            return list(self.dialogue)
            
    def get_formatted_dialogue(self, max_lines=None):
        """Formats the dialogue into standard text format."""
        with self.lock:
            formatted = []
            
            # Slice window if max_lines is enforced (e.g. for Prompter Auto-Scroll UI)
            target_list = self.dialogue[-max_lines:] if max_lines else self.dialogue
            
            for msg in target_list:
                formatted.append(f"{msg['role']}: {msg['text']}")
            return "\n".join(formatted)

    def get_last_role(self):
        """Retrieves the caller role of the most recent message."""
        with self.lock:
            if not self.dialogue:
                return None
            return self.dialogue[-1]['role']

    def clear(self):
        """Purges memory buffers."""
        with self.lock:
            self.dialogue.clear()
            self.advice = "Awaiting dialogue..."
            self.is_thinking = False
