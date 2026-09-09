"""The post-meeting prompt appended to every session transcript.

**This application does no post-processing.** It writes an instruction at the end of
`history/Meeting_<id>.md` and stops there. The operator copies it into whatever agent they use,
or writes their own script to lift it out and pipe it somewhere. Nothing here runs a subprocess,
loads a model, or reaches the network -- which is what makes **R15**'s "no runtime code path in
the application may depend on it, and the offline guarantee must remain intact" true without
qualification rather than true-by-default-and-broken-by-a-switch.

**Why the prompt lives in the file rather than in a settings field or an environment variable.**
Every agent CLI takes an instruction differently, and the operator may not use a CLI at all --
they may paste it into a chat window. A block of text at a known marker inside a file the
operator already opens is the one delivery mechanism that works for all of those, needs no
contract, and survives being emailed to someone else.

**What the prompt has to carry, and why this module exists rather than a constant somewhere.**
A foreign agent reading `Meeting_2026-08-13_101500.md` cold knows none of this:

- the line format, and that the two roles are two *separate audio tracks* that were never mixed;
- that the transcript is lossy in specific, known ways -- sentences cut at pauses, non-speech
  occasionally rendered as words -- so a fragment is usually a segmentation artefact rather than
  something a person said oddly;
- that nobody has attributed individual speakers, so `Participant` may be several people;
- where the retained audio is, when there is any, since that is the only thing that can settle a
  question the text cannot.

Getting an agent to produce a usable report without that context means it invents the missing
half. Everything in the briefing below is a fact this repository measured; nothing is aspiration.
"""
import os

# A stable, greppable boundary so a script can lift the prompt out -- `sed -n '/<marker>/,$p'` --
# without parsing Markdown. It is also the line a human scrolls to.
MARKER_TOKEN = "aegis:post-meeting-prompt"
MARKER = f"<!-- {MARKER_TOKEN} -->"
HEADING = "## ✂︎ Post-meeting prompt — copy everything below into your own agent"


# Which transcript the prompt is being attached to. **They are not interchangeable and attaching
# the wrong one is worse than attaching none**: on 2026-08-17 the re-listened transcript carried
# the live briefing, which told an agent to rejoin fragments from a 0.4 s flush that never
# happened, to look for advisor lines that do not exist there, and to read offsets as wall clock
# — while the file's own header, two lines above, said the flush was 1.2 s. A document
# contradicting itself is read as one of the two being a typo.
LIVE = "live"
RELISTENED = "relistened"


def build_prompt(session_id="", audio=None, roles=("Speaker (You)", "Participant"),
                 kind=LIVE, flush_s=None):
    """The briefing an outside agent needs, plus the three deliverables. Pure: no I/O.

    `audio` is the `{track: path}` mapping retention produced, or empty when the operator did not
    keep any. It is named rather than described, because "there is a recording somewhere" is not
    something anyone can act on.

    `kind` selects which file is being described. Every claim below has to be true of the file it
    is appended to, and the two files differ in four specifics -- timestamps, advisor lines, the
    silence flush, and whether the audio is a separate artefact or the thing this was made from.
    """
    speaker, participant = roles
    relistened = kind == RELISTENED
    lines = [
        "You are given the transcript of a live hearing above. Produce three things, in this "
        "order, and nothing else.",
        "",
        "1. **Report** — what the meeting was about, what was decided, what was left open, and "
        "what anyone was asked to do. For someone who was not in the room.",
        "2. **Meeting sections** — the meeting divided into its topics in order, each with a "
        "short title and two or three lines on what happened in it.",
        "3. **Proofread transcript** — the whole transcript, readable: punctuation and sentence "
        "boundaries restored, Chinese normalised to Traditional characters, recogniser artefacts "
        "dropped. Same turns, same order, same speakers.",
        "",
        "Write in the language the meeting was conducted in. Do not translate it.",
        "",
        "### How this file is written",
        "",
        ("- Every turn is one line: `**[H:MM:SS] Role**: text`. The timestamp is an **offset from "
         "the start of the recording**, not a clock time — this transcript was produced by "
         "re-reading the audio, so its origin is the first frame rather than a wall clock."
         if relistened else
         "- Every turn is one line: `**[HH:MM:SS] Role**: text`. The timestamp is wall clock, and "
         "the file header carries the session start to the millisecond."),
        f"- There are exactly two roles. `{speaker}` is the operator's own microphone. "
        f"`{participant}` is everything the machine played — the remote parties, and anything "
        "else audible from the computer.",
        "- **They are two separate audio tracks and were never mixed.** A line's role is "
        "therefore reliable: it is which device the audio came from, not a guess from the words.",
        ("- There are no advisor lines here. This file is speech and nothing else."
         if relistened else
         "- Lines beginning `> **⚡ Staff override**`, `> **🛡️ Retrieved cue**` or "
         "`> **🤖 Generated — UNVERIFIED**` are prompts shown to the speaker during the meeting, "
         "**not things anyone said**. Leave them out of the proofread transcript, and treat the "
         "generated ones as unverified if you use them at all."),
        "",
        "### What the transcript is missing, and how it is wrong",
        "",
        "This is automatic speech recognition, captured live. The failures are known and "
        "specific, so read a defect as a defect rather than as something a person did:",
        "",
        (f"- **Sentences are mostly whole.** A segment closes after {flush_s or 1.2} s of "
         "silence here, three times the live path's, because nobody was waiting for this one. "
         "There is less rejoining to do than in the live transcript — but check rather than "
         "assume."
         if relistened else
         "- **Sentences are cut at pauses.** A segment closes after 0.4 s of silence, so one "
         "spoken sentence often arrives as two or three lines. Rejoining them is most of the "
         "proofreading."),
        "- **Non-speech sometimes becomes words.** Laughter, coughing and room tone occasionally "
        "produce a plausible short sentence — measured at 23 of 253 non-speech recordings. A "
        "short, oddly-placed line with no relation to its neighbours is probably this.",
        "- **Nothing was filtered out for you.** Short noise reaches the transcript on purpose, "
        "so that genuine one-word answers are never lost. Removing it is your job here.",
        "- **Individual speakers were never separated.** Everything from the far side is labelled "
        f"`{participant}`, however many people were talking. **Do not invent names, do not split "
        "the label, and do not relabel a line** — not even where you are confident. The names "
        "you collect for the report are names that were *spoken*; which line belongs to whom is "
        "a different question and nothing here can answer it.",
        ("- **This is the recovery pass, so less was discarded than in the live transcript** — "
         "it was read from audio captured before voice detection ran. What voice detection still "
         "rejects here is gone all the same."
         if relistened else
         "- **Whatever the recogniser discarded is not here.** Silence judgements and minimum "
         "duration filters drop material, and none of it can be recovered from the text."),
    ]
    if relistened:
        lines.append("- **The recogniser emits Simplified characters.** Normalising them to "
                     "Traditional is part of what is being asked for above; it is not a sign "
                     "that anything went wrong.")

    if audio:
        lines += [
            "",
            "### The audio was kept",
            "",
            "Two lossless 16 kHz mono WAVs, one per track, recorded before voice detection — so "
            "they contain what the transcript above dropped:",
            "",
        ]
        lines += [f"- `{track}`: `{path}`" for track, path in sorted(audio.items())]
        lines += [
            "",
            "If a passage matters and the text is unreadable, the audio can settle it. Timestamps "
            "in the transcript are wall clock; each file's own start instant is recorded in the "
            "audio section of this document.",
        ]
    else:
        lines += [
            "",
            "### No audio was kept",
            "",
            "Retention was off for this session, so this transcript is the only record. Anything "
            "unclear stays unclear — **say so rather than reconstructing it**.",
        ]

    lines += [
        "",
        "### Rules",
        "",
        "- Never invent a figure, date, name, statute or citation that is not in the text above.",
        "- Do not answer the questions in the transcript, and do not take a side in it. You are "
        "producing a record, not participating.",
        "- Where the transcript is unclear or cuts off, say so in one clause and move on. A gap "
        "marked as a gap is worth more than a plausible sentence nobody said.",
    ]
    if session_id:
        lines += ["", f"_Session `{session_id}`._"]
    return "\n".join(lines)


def render_block(session_id="", audio=None, kind=LIVE, flush_s=None):
    """The whole appendix, marker included, ready to write at the end of the transcript.

    `kind` must match the file this is appended to. See `build_prompt`.
    """
    return "\n".join([
        "",
        "---",
        "",
        MARKER,
        HEADING,
        "",
        build_prompt(session_id=session_id, audio=audio, kind=kind, flush_s=flush_s),
        "",
    ])


def extract(markdown):
    """Everything after the marker, for a script that wants only the prompt. `""` if absent.

    The counterpart to `MARKER` being stable: `sed -n '/aegis:post-meeting-prompt/,$p' file` does
    the same job in one line, and this exists so the repository's own tests use the same
    definition the documentation gives operators.
    """
    index = markdown.find(MARKER)
    if index == -1:
        return ""
    return markdown[index + len(MARKER):].strip()


def audio_paths(archive_dir, session_id):
    """Retained tracks for this session, if they are there (R44, R45).

    Resolved from `session_id` plus the configured archive directory -- never by assuming the
    WAVs sit beside the transcript, which is a layout the retention item deliberately does not
    use.
    """
    if not archive_dir or not session_id:
        return {}
    found = {}
    for track in ("mic", "system"):
        path = os.path.join(archive_dir, f"Meeting_{session_id}_{track}.wav")
        if os.path.exists(path):
            found[track] = path
    return found


def list_sessions(history_dir="history"):
    """Past sessions, newest first, with what exists alongside each. Never raises.

    Reads only its own output: the transcripts this application wrote. Cheap enough to run on a
    screen that must open without loading anything -- a stat and a substring search per file, no
    parsing, no model, no network.
    """
    try:
        names = [n for n in os.listdir(history_dir)
                 if n.startswith("Meeting_") and n.endswith(".md")]
    except Exception:
        return []

    sessions = []
    for name in names:
        path = os.path.join(history_dir, name)
        session_id = name[len("Meeting_"):-len(".md")]
        try:
            modified = os.path.getmtime(path)
            size = os.path.getsize(path)
        except Exception:
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                has_prompt = MARKER in handle.read()
        except Exception:
            has_prompt = False
        sessions.append({
            "session_id": session_id,
            "path": path,
            "modified": modified,
            "bytes": size,
            "has_prompt": has_prompt,
        })
    return sorted(sessions, key=lambda s: s["modified"], reverse=True)


def read_prompt(path):
    """The prompt block from one transcript, or `""`. Never raises."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return extract(handle.read())
    except Exception:
        return ""
