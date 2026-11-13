"""Re-transcribe a retained meeting from its audio, and fill in what the live path dropped.

**The one post-meeting job an outside agent cannot do.** The review pass is a prompt in the
transcript because any agent can read text; this reads *audio*, with this application's model and
this application's timebase, and neither is available to anything else.

What it recovers is specific, and it is exactly what the live path is documented as discarding:

- **whole sentences instead of fragments.** Live capture closes a segment after 0.4 s of silence
  (**V66**) because the speaker is waiting; here nobody is, so segments are cut only where the
  audio is genuinely quiet for longer, and a sentence spoken with a pause in the middle arrives
  as one line;
- **the material VAD judged non-speech.** The archive is written from the raw callback, upstream
  of voice detection (**R3**, **R45**), so it still contains what the transcript never saw;
- **rare proper nouns.** Decoder biasing from the live transcript's own vocabulary. **V59**
  measured this on the previous backend's `context=` argument — 1 recovered of 11 became 9 of 11 —
  and that argument no longer exists: `docs/decisions/0012` replaced the backend, and Whisper's
  equivalent is `initial_prompt`, which is **not the same mechanism**. `context=` conditioned the
  model on a vocabulary list; `initial_prompt` prepends text the decoder may also copy out
  verbatim. Re-measured here by `tools/measure_biasing.py` rather than assumed to
  carry over.

  Biasing lives in this pass and not the live one for the reason it always did: it is text the
  decoder can emit, so it can invent, and this is the pass an operator reads before anyone acts
  on it (**R37**, **R38**). An external file has no transcript to harvest, so the caller passes
  the terms. Either source is printed in the output, because a reader who meets one of those
  words has to be able to see that it was suggested (**V74**).

**Speaker separation is optional and installed on demand.** `src/diarize.py` owns it, nothing is
in `requirements.txt`, and the first re-listen that asks for labels is what fetches it — so a
process that never asks contains no telemetry exporter and no cloud SDK, and **R15** stays
structurally true for it. The labels it produces are **anonymous and numbered** (`與會者1`,
`與會者2`); who those people are is a separate table at the end that the operator applies
themselves. See `diarize.py` for why those two are kept apart.

**Nothing here runs on its own.** It is a button in Archive Mode, pressed after a meeting, and a
command (`tools/relisten_file.py`) for a recording this application never captured. Either way it
loads the model when asked rather than at page load — the same rule the whole product follows
since 2026-08-14: only an explicit action costs anything.
"""
import datetime
import logging
import os
import wave

logger = logging.getLogger("Relisten")

# Longer than the live path's 0.4 s (V66) and for the opposite reason. There, a segment closes
# early because the speaker is waiting for it; here nobody is waiting, so the only thing a short
# flush buys is more fragments to rejoin. 1.5 s was measured as harmful *live* -- the median
# segment lands on the 15 s cap and cuts happen on a clock rather than at silence -- but that
# measurement was about latency and segment length, and the cap below is what guards against it.
SILENCE_FLUSH_S = 1.2

# Hard ceiling on one segment, as in the live path. A cut on a clock is worse than a cut at
# silence, so this exists only to stop unbroken speech growing without bound.
MAX_SEGMENT_S = 20.0

# Below this a segment is noise rather than an utterance, matching the live path's own floor.
MIN_SEGMENT_S = 0.3

RELISTEN_SUFFIX = "_relistened"


def default_model():
    """The shipped ASR default, read from the settings schema rather than repeated here.

    This pass gets a model id from the caller in every real invocation; the fallback exists for
    direct calls and tests. It is a lookup and not a constant because a second copy of the
    default is a copy that goes stale silently -- the id changed on 2026-08-17
    (`docs/decisions/0012`) and a hardcoded literal here would still be naming the old one.
    """
    import bootstrap
    return bootstrap.FIELDS_BY_KEY["ASR_MODEL"].default


def relistened_path(transcript_path):
    """Where the re-listened transcript goes. A new file; the others are never touched."""
    base, extension = os.path.splitext(transcript_path)
    return f"{base}{RELISTEN_SUFFIX}{extension or '.md'}"


def read_wav_mono_int16(path):
    """`(samples, sample_rate)` from a mono 16-bit WAV, or `(None, 0)`. Never raises.

    Deliberately narrow: this reads back exactly what `audio_archive.TrackWriter` writes, and a
    file that is not that shape is a fault to report rather than something to convert quietly.
    """
    try:
        import numpy as np
        with wave.open(path, "rb") as handle:
            if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
                return None, 0
            rate = handle.getframerate()
            raw = handle.readframes(handle.getnframes())
        return np.frombuffer(raw, dtype=np.int16), rate
    except Exception as exc:
        logger.error("❌ [Relisten] %s could not be read: %s", path, exc)
        return None, 0


def segment(samples, rate, vad, flush_s=SILENCE_FLUSH_S, max_s=MAX_SEGMENT_S,
            min_s=MIN_SEGMENT_S):
    """Cut the track into utterances at silence. Yields `(start_second, samples)`.

    The same voice-detection frames the live path uses, with a longer silence flush -- the whole
    difference between this pass and the live one is that nobody is waiting for it, so a sentence
    is allowed to finish before its segment closes.
    """
    frame = int(rate * 0.03)
    if frame <= 0 or samples is None or len(samples) < frame:
        return
    flush_frames = max(1, int(flush_s / 0.03))
    max_frames = max(1, int(max_s / 0.03))

    # `spoken` counts frames VAD called speech, and the minimum duration is measured against
    # **that**, not against the buffer. A segment carries its trailing silence -- that is what
    # makes the flush audible as a pause rather than a cut -- so measuring the buffer would let a
    # 0.1 s cough padded with 1.2 s of silence pass a 0.3 s floor. Caught by the test for exactly
    # that case, 2026-08-14.
    buffer, silence, start, spoken = [], 0, 0, 0
    for index in range(0, len(samples) - frame + 1, frame):
        block = samples[index:index + frame]
        try:
            speech = vad.is_speech(block.tobytes(), rate)
        except Exception:
            speech = False

        if speech:
            if not buffer:
                start = index
            buffer.append(block)
            spoken += 1
            silence = 0
        elif buffer:
            buffer.append(block)
            silence += 1

        if buffer and (silence >= flush_frames or len(buffer) >= max_frames):
            if spoken * frame >= rate * min_s:
                yield start / float(rate), _join(buffer)
            buffer, silence, spoken = [], 0, 0

    if buffer and spoken * frame >= rate * min_s:
        yield start / float(rate), _join(buffer)


def _join(blocks):
    import numpy as np
    return np.concatenate(blocks)


def vocabulary_from(transcript_path, limit=40):
    """Terms to bias recognition toward, taken from the transcript being re-listened to.

    **Scoped to this meeting, not to the whole knowledge base** -- that is the one source of
    terms guaranteed to be about this hearing. `context=` recovers rare proper nouns (**V59**)
    and the words the live pass already got right are the best available guess at what the words
    it got wrong sound like.
    """
    try:
        with open(transcript_path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except Exception:
        return ""
    import re
    body = text.split("## 📝", 1)[-1].split("<!-- aegis:", 1)[0]
    # Capitalised runs and CJK runs of 2-6 characters: names, places, organisations.
    terms = re.findall(r"[A-Z][A-Za-z0-9&.\-]{2,}(?:\s+[A-Z][A-Za-z0-9&.\-]{2,})*", body)
    terms += re.findall(r"[一-鿿]{2,6}", body)
    seen, ordered = set(), []
    for term in terms:
        key = term.strip()
        if key and key not in seen:
            seen.add(key)
            ordered.append(key)
        if len(ordered) >= limit:
            break
    return ", ".join(ordered)


# `- **Speaker (You)** — `path`` then `  - started 2026-08-14T10:15:00.123, 3600.0 s, ...`
_STARTED_RE = None


def track_starts(transcript_path):
    """Each track's first-frame instant, read back from the transcript's audio section.

    **The branch's offline merge assumed a shared `t=0` that nothing established**
    (`docs/decisions/0006`). Retention records each track's own first-frame wall clock precisely
    so that assumption is not needed. When the section is missing -- an older session, or one
    that never stopped cleanly -- this returns `{}` and the caller **says so in the output**
    rather than quietly aligning them anyway.
    """
    global _STARTED_RE
    import re
    if _STARTED_RE is None:
        _STARTED_RE = re.compile(
            r"^- \*\*(?P<label>[^*]+)\*\* — `(?P<path>[^`]+)`\s*\n\s*- started (?P<started>[^,]+),",
            re.MULTILINE)
    try:
        with open(transcript_path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except Exception:
        return {}
    starts = {}
    for match in _STARTED_RE.finditer(text):
        stamp = match.group("started").strip()
        try:
            starts[match.group("label").strip()] = datetime.datetime.fromisoformat(stamp)
        except Exception:
            continue
    return starts


def normalize_vocabulary(vocabulary):
    """A caller's term list as the same comma-separated text `vocabulary_from` produces.

    Accepts a string (`"Datadog, JSON,TrueWatch"`) or an iterable of terms. Empty entries and
    repeats are dropped and order is kept, because the order the operator typed is the only
    priority signal there is.
    """
    if not vocabulary:
        return ""
    items = vocabulary.split(",") if isinstance(vocabulary, str) else list(vocabulary)
    seen, ordered = set(), []
    for item in items:
        term = " ".join(str(item).split())
        if term and term not in seen:
            seen.add(term)
            ordered.append(term)
    return ", ".join(ordered)


def run(transcript_path, tracks, model_path=None, use_context=True, on_progress=None,
        diarize=False, hf_token="", diarize_model="", speaker_track="Participant",
        vocabulary=None, out_path=None, source=None):
    """Re-transcribe the retained audio and write `<transcript>_relistened.md`.

    `tracks` maps a role label to a WAV path. Returns a dict; never raises -- this runs after a
    meeting with the real record already safely on disk, so a failure must say so and change
    nothing else.

    **An external recording** is the same pass with `transcript_path=None`: a file this
    application never captured (`tools/relisten_file.py`). There is then no live transcript to
    harvest vocabulary from and no recorded timebase, and the output says so instead of
    describing two tracks that do not exist. `source` names the original file for the header,
    since the WAV in `tracks` is usually a temporary conversion of it; `out_path` is required
    in that mode because there is no transcript to sit beside.

    `vocabulary`, when given, replaces the harvested one -- the operator knows the domain terms
    of a recording better than any regex over it. It feeds the same `initial_prompt` either way.
    """
    external = not transcript_path
    result = {"output": "", "error": "", "segments": 0, "tracks": {}, "aligned": False,
              "diarized": False, "voices": 0, "diarize_error": "", "external": external,
              "vocabulary": "", "vocabulary_source": ""}
    if not tracks:
        result["error"] = "no retained audio for this session"
        return result
    if external and not out_path:
        result["error"] = "an external recording needs an explicit output path"
        return result

    try:
        import webrtcvad
        import numpy as np
        import transcriber as tr
    except Exception as exc:
        result["error"] = f"the audio stack is unavailable: {type(exc).__name__}: {exc}"
        return result

    model = (model_path or "").strip() or None
    explicit = normalize_vocabulary(vocabulary)
    if explicit:
        context, result["vocabulary_source"] = explicit, "operator"
    elif use_context and not external:
        context = vocabulary_from(transcript_path)
        result["vocabulary_source"] = "transcript" if context else ""
    else:
        context = ""
    result["vocabulary"] = context
    # The prompt is bound into the backend here rather than passed per call: `resolve_backend`
    # closes over it, so every segment in this pass is biased identically and no call site can
    # forget. The live path builds its backend with no prompt at all.
    try:
        kind, transcribe = tr.resolve_backend(model or default_model(),
                                              initial_prompt=context or None)
    except Exception as exc:
        # A refused or unloadable model id. Reported, because this function promises not to raise.
        result["error"] = f"the model could not be loaded: {type(exc).__name__}: {exc}"
        return result

    starts = {} if external else track_starts(transcript_path)
    result["aligned"] = len(starts) >= len(tracks)
    origin = min(starts.values()) if starts else None

    lines = []
    for label, path in sorted(tracks.items()):
        if on_progress:
            on_progress(f"reading {os.path.basename(path)}")
        samples, rate = read_wav_mono_int16(path)
        if samples is None:
            result["tracks"][label] = {"path": path, "error": "unreadable or not mono 16-bit"}
            continue

        offset = 0.0
        if origin is not None and label in starts:
            offset = (starts[label] - origin).total_seconds()

        # Only the far-side track is clustered. The microphone is the operator by construction
        # (R2), so splitting it would be inventing a second person at the desk. A microphone
        # shared with a room would need the same treatment and does not get it here.
        turns = []
        if diarize and label == speaker_track:
            import diarize as diarizer
            if on_progress:
                on_progress(f"{label}: separating voices")
            turns, diar_error = diarizer.run(path, model_id=diarize_model, token=hf_token)
            if diar_error:
                # Reported, never fatal: a transcript without speaker labels is still the
                # recovery pass working, and saying so beats a file that quietly has one label.
                result["diarize_error"] = diar_error
                logger.warning("⚠️ [Relisten] speaker separation unavailable: %s", diar_error)
            else:
                result["diarized"] = True
                result["voices"] = len({index for _s, _e, index in turns})

        vad = webrtcvad.Vad(3)
        spoken = 0
        for index, (second, block) in enumerate(segment(samples, rate, vad), start=1):
            if on_progress:
                on_progress(f"{label}: segment {index}")
            audio = (block.astype(np.float32) / 32767.0)
            try:
                # `NPU_LOCK` for the same reason the live path takes it: one accelerator, and a
                # guard that costs nothing measurable is kept rather than argued about (V57).
                with tr.NPU_LOCK:
                    text = transcribe(audio)
            except Exception as exc:
                result["error"] = f"{label} segment {index} failed: {type(exc).__name__}: {exc}"
                break
            if text:
                line_label = label
                if turns:
                    import diarize as diarizer
                    # The midpoint, not the start: a segment opens at the first speech frame and
                    # a diarization boundary sits wherever the voice actually changed.
                    who = diarizer.speaker_at(turns, second + len(block) / (2.0 * rate))
                    if who is not None:
                        line_label = diarizer.label_for(who)
                lines.append((second + offset, line_label, text))
                spoken += 1
        result["tracks"][label] = {"path": path, "segments": spoken,
                                   "seconds": len(samples) / float(rate) if rate else 0.0}

    lines.sort(key=lambda row: row[0])
    result["segments"] = len(lines)
    out_path = out_path or relistened_path(transcript_path)
    try:
        with open(out_path, "w", encoding="utf-8") as handle:
            handle.write(_render(transcript_path, tracks, lines, result, context, model, kind,
                                 source=source))
    except Exception as exc:
        result["error"] = ((result["error"] + "; ") if result["error"] else "") + \
                          f"could not write {out_path}: {type(exc).__name__}: {exc}"
        return result

    result["output"] = out_path
    logger.info("🎧 [Relisten] %s written: %d lines from %d tracks",
                out_path, len(lines), len(tracks))
    return result


def _render(transcript_path, tracks, lines, result, context, model, kind, source=None):
    import postmeeting

    external = result.get("external")
    single = len(tracks) == 1
    out = ["# 🎧 Re-listened transcript", ""]
    if external:
        name = os.path.basename(source) if source else \
            ", ".join(sorted(os.path.basename(p) for p in tracks.values()))
        supplied = "one file" if single else "files"
        out.append(f"- **Source recording**: `{name}` — {supplied} supplied from outside this "
                   f"application, so there is no live transcript and no recorded timebase")
    else:
        out.append(f"- **Source audio**: "
                   f"{', '.join(sorted(os.path.basename(p) for p in tracks.values()))}")
        out.append(f"- **Live transcript**: `{os.path.basename(transcript_path)}` — unchanged; "
                   f"this is a second reading of the same hour, not a correction of that one")
    out.append(f"- **Model**: `{model or 'default'}` ({kind}), segments closed after "
               f"{SILENCE_FLUSH_S} s of silence instead of the live path's 0.4 s")
    # The terms are printed, not merely acknowledged: `initial_prompt` is text the decoder may
    # copy out verbatim (V74), so a reader who meets one of these words below has to be able to
    # see that it was suggested before deciding it was heard.
    if context:
        origin = ("supplied by the operator" if result.get("vocabulary_source") == "operator"
                  else "harvested from this meeting’s own transcript")
        out.append(f"- **Vocabulary bias** ({origin}): `{context}` — the recogniser was primed "
                   f"with these words and can echo them, so a term from this list in the text "
                   f"below was suggested as well as heard")
    else:
        out.append("- **Vocabulary bias**: off")
    if external and single:
        # R2 is a property of audio this application captured. A file from outside has one
        # stream, and a call in it is already mixed — saying "two tracks" here would be the
        # retained-session header describing a recording that was never two files.
        out.append("- **Tracks**: one. If this recording captured a call, both sides are "
                   "**mixed** in it, so a line's label says nothing about which side spoke "
                   "(R2 holds only for audio this application captured itself).")
    elif external:
        out.append("- ⚠️ **Timebase**: these files were not captured here, so no first-frame "
                   "instant was recorded. They are aligned as if they began together. "
                   "**They may not have.** Treat cross-file ordering as approximate.")
    elif result["aligned"]:
        out.append("- **Timebase**: both tracks aligned on their own recorded first-frame "
                   "instants")
    else:
        # The branch's merge assumed this silently. It is stated instead.
        out.append("- ⚠️ **Timebase**: the per-track start times were not found in the live "
                   "transcript, so the two tracks are aligned as if they began together. "
                   "**They did not.** Treat cross-track ordering as approximate.")
    where = "in this recording" if external else "on the far side"
    everyone = ("Every line carries the same label, whoever spoke." if external else
                "Everything from the far side is one label, however many people spoke.")
    if result.get("diarized"):
        out.append(f"- **Voices separated**: {result['voices']} {where}, labelled "
                   f"`與會者1`… by **sound alone**. The labels say which lines share a voice and "
                   f"nothing more — who those people are is the table at the end, and this file "
                   f"has not applied it (R12, R13).")
    elif result.get("diarize_error"):
        out.append(f"- ⚠️ **Voices not separated**: {result['diarize_error']} {everyone}")
    else:
        out.append(f"- **Speaker attribution**: not performed. {everyone} (R12)")
    for label, info in sorted(result["tracks"].items()):
        if info.get("error"):
            out.append(f"- ❌ **{label}**: {info['error']}")
        else:
            out.append(f"- **{label}**: {info['segments']} segments over "
                       f"{info.get('seconds', 0) / 60:.1f} min")
    if result["error"]:
        out.append(f"- ⚠️ **Incomplete**: {result['error']}")
    out += ["", "---", "", "## 📝 Transcript", ""]

    for second, label, text in lines:
        stamp = str(datetime.timedelta(seconds=int(second)))
        out.append(f"**[{stamp}] {label}**: {text}")
        out.append("")

    if result.get("diarized"):
        import diarize as diarizer
        proposals = diarizer.propose_titles(lines)
        named = {row["guess"] for row in proposals if row["guess"]}
        everything = " ".join(text for _s, _l, text in lines)
        unmatched = [n for n in diarizer.candidate_names(everything) if n not in named]
        out += ["---", "", diarizer.render_table(proposals, unmatched), ""]

    # A prompt for *this* file, not the live one. Attaching the live briefing here told an agent
    # to rejoin fragments from a 0.4 s flush that never happened and to look for advisor lines
    # that do not exist -- while the header above said the flush was 1.2 s. Found 2026-08-17.
    if external:
        label = sorted(tracks)[0] if single else "Recording"
        # The original path, when we have it: the WAV in `tracks` is usually a temporary
        # conversion and will be gone by the time anyone reads this file.
        audio = {label: source} if (single and source) else dict(tracks)
        out.append(postmeeting.render_block(
            kind=postmeeting.EXTERNAL, flush_s=SILENCE_FLUSH_S, audio=audio,
            roles=(label, label), speakers_separated=bool(result.get("diarized"))))
    else:
        out.append(postmeeting.render_block(kind=postmeeting.RELISTENED,
                                            flush_s=SILENCE_FLUSH_S))
    return "\n".join(out)
