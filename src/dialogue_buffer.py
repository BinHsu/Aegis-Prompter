import threading
import os
import datetime

from advisors import ADVICE_SOURCES, SOURCE_GENERATED, SOURCE_OVERRIDE, SOURCE_RETRIEVED

# What the log calls each kind. The archived transcript is read after the meeting, often by
# someone who was not in it, so the distinction R30 draws on screen has to survive into the file
# -- a generated line quoted back a week later is exactly the case where "which of these was
# pre-written?" stops being obvious.
LOG_LABELS = {
    SOURCE_OVERRIDE: "⚡ Staff override",
    SOURCE_RETRIEVED: "🛡️ Retrieved cue (pre-written)",
    SOURCE_GENERATED: "🤖 Generated — UNVERIFIED",
}


def _empty_slot():
    return {"text": "", "vendor": "", "score": None, "time": "", "is_thinking": False}


class DialogueBuffer:
    def __init__(self, max_history=15):
        """
        🛡️ Core Dialogue Buffer
        max_history: Max number of recent messages to preserve in memory.
        """
        self.max_history = max_history
        self.dialogue = []  # Stores dicts: {"role": role, "text": text, "time": timestamp}

        # One slot per kind of advisor output, never one shared slot (V24). A single
        # `self.advice` string meant a remote LLM reply arriving seconds later reliably
        # overwrote an already-displayed retrieved cue -- the speaker reads a safe pre-written
        # answer and it is swapped for generated text mid-glance. The merge policy is now
        # explicit and it is "they do not merge": each kind holds its own slot and the renderer
        # shows all of them, labelled (R29, R30, R42).
        self.advice_slots = {source: _empty_slot() for source in ADVICE_SOURCES}
        self.lock = threading.Lock()

        # Session state for persistent saving
        self.session_file = None
        self.session_id = None

    def start_session(self, session_id, history_dir="history", retention=None):
        """Initializes logging array and creates a local markdown file for the session.

        `retention` states whether audio is being kept and where. It is written into the header
        **at Start**, not at Stop, because R45's distinction has to survive a session that ends
        badly: without it, "recorded and later deleted" and "never recorded" are the same file,
        and R4 makes deletion a normal event rather than an anomaly.

        The header also carries the session start to the millisecond. `docs/decisions/0001`
        requires it: a transcript timestamp is only convertible into an offset into a WAV
        against a precise origin, and "jump to this moment" is the whole point of keeping one.
        """
        if not os.path.exists(history_dir):
            os.makedirs(history_dir)

        self.session_id = session_id
        self.session_file = os.path.join(history_dir, f"Meeting_{session_id}.md")

        started = datetime.datetime.now()
        with open(self.session_file, "w", encoding="utf-8") as f:
            f.write(f"# 🛡️ Staff Officer Meeting Log\n\n")
            f.write(f"- **Date**: {started.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"- **Session start (precise)**: "
                    f"{started.isoformat(timespec='milliseconds')}\n")
            f.write(f"- **Session ID**: {session_id}\n")
            if retention and retention.get("armed"):
                f.write(f"- **Audio retained**: yes — `{retention.get('directory', '')}`\n")
                for track, path in (retention.get("tracks") or {}).items():
                    f.write(f"  - {track}: `{path}`\n")
            else:
                f.write("- **Audio retained**: no — nothing the transcript dropped can be "
                        "recovered from this session\n")
            f.write("\n---\n\n")
            f.write(f"## 📝 Transcript & Tactical Cues\n\n")

    def finish_session(self, archive_summary=None, prompt_block=""):
        """Close the record: what the archive produced, then the post-meeting prompt.

        Separate from the header on purpose: the header states the *intent* while it can still
        be written, and this states the *outcome* -- durations, and any blocks the writer could
        not keep up with. A session that dies without reaching here still says it was armed.

        `prompt_block` is appended last and unconditionally. It costs nothing, sends nothing and
        loads nothing -- writing an instruction into a file is not post-processing, which is why
        it happens without being armed while the work it describes does not happen at all (R15).
        """
        if not self.session_file:
            return
        if not archive_summary:
            self._append(prompt_block)
            return
        try:
            with open(self.session_file, "a", encoding="utf-8") as f:
                f.write("\n---\n\n## 🎧 Audio archive\n\n")
                for track, info in archive_summary.items():
                    f.write(f"- **{track}** — `{info.get('path', '')}`\n")
                    f.write(f"  - started {info.get('started_at') or 'never (no frames)'}, "
                            f"{info.get('seconds', 0):.1f} s, "
                            f"{info.get('bytes', 0) / 1_048_576:.1f} MB\n")
                    if info.get("dropped_blocks"):
                        f.write(f"  - ⚠️ **{info['dropped_blocks']} blocks dropped** — this file "
                                f"is not the whole session\n")
                    if info.get("error"):
                        f.write(f"  - ❌ {info['error']}\n")
                f.write("\n")
        except Exception:
            pass
        self._append(prompt_block)

    def _append(self, text):
        """Write a trailing block, or nothing when there is none. Never raises."""
        if not text or not self.session_file:
            return
        try:
            with open(self.session_file, "a", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass

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

    def set_advice(self, advice, source=SOURCE_OVERRIDE, vendor="", score=None,
                   is_thinking=False):
        """Fill one advisor slot and persist it, labelled with what produced it.

        `source` must be one of `advisors.ADVICE_SOURCES`; an unknown one is a programming
        error and raises rather than quietly landing somewhere. `is_thinking` marks the slot
        in-flight -- it updates the display and deliberately skips the session log (V25),
        because a pending state is not a proposal anyone made.
        """
        if source not in self.advice_slots:
            raise ValueError(f"unknown advice source: {source!r}")
        with self.lock:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            self.advice_slots[source] = {
                "text": advice,
                "vendor": vendor,
                "score": score,
                "time": timestamp,
                "is_thinking": is_thinking,
            }

            # Append advice to log only when a definitive suggestion is made
            if self.session_file and not is_thinking:
                try:
                    label = LOG_LABELS.get(source, source)
                    with open(self.session_file, "a", encoding="utf-8") as f:
                        f.write(f"> **{label} [{timestamp}]**\n")
                        # Format as blockquote
                        formatted_advice = advice.replace('\n', '\n> ')
                        f.write(f"> {formatted_advice}\n\n")
                        f.write(f"---\n\n")
                except:
                    pass

    def get_advice_slots(self):
        """Snapshot of every advisor slot, keyed by source. Empty slots are present and blank."""
        with self.lock:
            return {source: dict(slot) for source, slot in self.advice_slots.items()}

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
            self.advice_slots = {source: _empty_slot() for source in ADVICE_SOURCES}
