"""Voice separation: which lines share a speaker, and a proposal for who they are.

**Two things, deliberately kept apart** — the split is the operator's design, 2026-08-17, and it
is what makes this safe to ship at all:

| | what it is | who asserts it |
|---|---|---|
| `與會者2` on a line | an **acoustic fact** — these lines share a voice | the machine, from the audio |
| 與會者2 = 王委員 | an **identity guess** | proposed here, **applied by the operator** |

So the transcript body carries only what the acoustics support. The naming is a table at the end,
with the evidence beside each row, and **this application never applies it** — the operator reads
it, decides, and does a find-and-replace themselves. A wrong guess is therefore visible before it
is written anywhere, and imperfect separation is recoverable rather than permanent.

⚠️ **"`pyannote.audio` is not in `requirements.txt` and never will be" was true here until
2026-08-18, and it is not any more.** `docs/decisions/0013` put a voice-activity gate in the
**live** path — the only measure that moves **R37** without destroying real speech (**V80**,
**V82**) — and a gate every session loads is a package every session loads. The paragraph below is
kept rather than deleted because its reasoning is still the reasoning; what changed is which side
of it won.

**What that costs, and it is a real loss:** the 47 packages, the telemetry exporter and the cloud
SDK are now present in every process, so **R15** stops being *checkable by reading the dependency
list*. Nothing transmits unconfigured — that was true when this module accepted them and is still
true — but a promise you can verify and a promise you must trust are different promises, and this
one moved.

**What survives, and it is not nothing:** the *weights* are still fetched only when someone asks
for labels. Importing this module still loads nothing.

**Nothing here was installed until the operator pressed the button**, and that was the design:
it kept **R15**'s offline guarantee *structurally* true for anyone who never pressed it — there is
no telemetry exporter and no cloud SDK in a process that never installed them. After they press,
it is their explicit act, which is the same shape as every other door out of this application.

**What pressing it costs, stated because it is not obvious:** 47 packages, most of them a research
lab's training and evaluation apparatus (`lightning`, `optuna`, `matplotlib`) rather than anything
inference needs; a Hugging Face account and token, because the weights are gated; and
`opentelemetry-*` plus `pyannoteai-sdk` — a telemetry framework and a cloud SDK — which
`pyannote-audio` declares as **core requirements, not optional extras**. Neither transmits
anything unconfigured. What changes is that the offline promise stops being checkable by reading
the dependency list.
"""
import json
import logging
import os
import re
import subprocess
import sys

logger = logging.getLogger("Diarize")

# Installed on demand, never declared. `pyannote.audio` pulls the rest.
INSTALL_TARGET = "pyannote.audio"

# The default. **A settings field owns the real value** -- `DIARIZE_MODEL` -- because every model
# id in this product is a field and not a constant, for the reason `model_search.py` sets out:
# whatever is pinned today eventually stops being downloadable. This one was a constant for three
# hours and that was an inconsistency, not a decision.
DEFAULT_MODEL_ID = "pyannote/speaker-diarization-community-1"

# A path that needs no Hugging Face token -- **and on `pyannote.audio` 4.0.7 it does not deliver
# that** (**V93**). The three repositories below are all still ungated and all three are in the
# cache; the pipeline still refuses to load, because v4's `SpeakerDiarization` defaults its `plda`
# parameter to `pyannote/speaker-diarization-community-1`, which is gated and answers 401 without a
# token, and `get_plda` has no "no calibration" option. Nothing in this repo names that repository:
# the requirement belongs to the installed library, which is exactly what verifying the *repos*
# against the Hub on 2026-08-17 could not have caught. Offering this id as the way to avoid a token
# is wrong until either a token exists or `pyannote.audio` is pinned to 3.x -- and pinning moves the
# version the voice gate runs on, which every measurement from V82 onward was taken with.
# Every piece named here is ungated: the pipeline (MIT), `ivrit-ai/pyannote-segmentation-3.0`, and
# pyannote's own `wespeaker-voxceleb-resnet34-LM` embedding model. It is a **third party re-hosting** the 3.1
# weights, which MIT permits and which is a supply-chain judgement rather than a free lunch --
# the same shape `docs/decisions/0008` accepted deliberately for the ASR port.
UNGATED_ALTERNATIVE = "ivrit-ai/pyannote-speaker-diarization-3.1"

# Pipelines that run in somebody else's datacentre. `pyannote/speaker-diarization-precision-2` is
# **not gated and has no weights at all** -- its `config.yaml` is
# `name: pyannote.audio.pipelines.pyannoteai.sdk.SDK`, so "using" it uploads the meeting. It looks
# like the free option to anyone browsing the Hub for one, which is exactly why it is refused
# here by name rather than left to be discovered.
CLOUD_PIPELINE_MARKERS = ("pyannoteai", "sdk.SDK")

# The label put on a line. Numbered and anonymous on purpose -- it is the acoustic fact and
# nothing more. `1`-based because the operator reads it, not because anything indexes on it.
LABEL_PREFIX = "與會者"


def label_for(index):
    """`與會者1`, `與會者2`, … from a zero-based cluster index."""
    return f"{LABEL_PREFIX}{index + 1}"


def available():
    """Whether the operator has already installed it. Never raises, never imports it."""
    import importlib.util
    try:
        return importlib.util.find_spec("pyannote.audio") is not None
    except Exception:
        return False


def install(timeout=1800):
    """Install it into this interpreter's environment. Returns `""` or the failure.

    Synchronous and bounded: its only caller is a button the operator pressed and is watching.
    `sys.executable -m pip` rather than a bare `pip`, so it lands in the environment actually
    running rather than whichever one is first on `PATH`.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", INSTALL_TARGET],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"installing {INSTALL_TARGET} timed out after {timeout}s"
    except Exception as exc:
        return f"could not run pip: {type(exc).__name__}: {exc}"
    if result.returncode != 0:
        return (result.stderr or result.stdout or "").strip()[-400:] or "pip failed"
    return ""


def is_cloud_pipeline(model_id, token=""):
    """Whether this pipeline would send the audio somewhere. Returns `(is_cloud, detail)`.

    Reads the repository's `config.yaml` and looks at which pipeline class it names. A product
    whose premise is that meeting audio stays put cannot let an id in a settings field silently
    turn re-listening into an upload -- and the one that would is *ungated*, so it is the one an
    operator avoiding the token is most likely to reach for.
    """
    try:
        from huggingface_hub import hf_hub_download
        path = hf_hub_download(model_id, "config.yaml", token=(token or None))
        config = open(path, encoding="utf-8").read()
    except Exception:
        # Unreadable is not proof of anything, and refusing on a failed download would block a
        # perfectly good local model whenever the network is down.
        return False, ""
    for marker in CLOUD_PIPELINE_MARKERS:
        if marker in config:
            return True, (f"`{model_id}` is not a local model: its pipeline is "
                          f"`pyannoteai.sdk.SDK`, which uploads the audio to pyannoteAI's API. "
                          f"That is why it is not gated — there are no weights to gate.")
    return False, ""


# The pinned interpreter that can diarize without a token (**V93**). Absent on a machine that
# never built it, which is why `run` treats it as a preference and not a requirement.
# Half real time on CPU, measured 2026-08-19: 83 s for a 180 s clip. An hour of meeting is
# therefore about half an hour of clustering, and the cap has to clear that with room to spare or
# it turns a slow success into a reported failure.
DIARIZE_TIMEOUT_S = 3600

PINNED_VENV = ".venv-diarize"
PINNED_RUNNER = "tools/diarize_runner.py"


def _pinned_python():
    """Path to the pinned interpreter, or `""` when it has not been built here."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidate = os.path.join(root, PINNED_VENV, "bin", "python")
    runner = os.path.join(root, PINNED_RUNNER)
    return candidate if (os.path.exists(candidate) and os.path.exists(runner)) else ""


def _run_pinned(python, wav_path, model_id, num_speakers, min_speakers, max_speakers):
    """Diarize in the pinned venv. Returns `(turns, error)` in `run`'s own vocabulary.

    Kept deliberately dumb: one subprocess, JSON on stdout, no shell. The audio path is passed as
    an argument rather than piped, and **nothing from stderr is returned to the caller** -- these
    are the operator's meeting recordings and pyannote is chatty about what it reads.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    hf_home = os.environ.get("HF_HOME", "")
    cmd = [python, os.path.join(root, PINNED_RUNNER), wav_path, "--model", model_id,
           "--min-speakers", str(int(min_speakers)), "--max-speakers", str(int(max_speakers))]
    if num_speakers:
        cmd += ["--num-speakers", str(int(num_speakers))]
    if hf_home:
        cmd += ["--hf-home", hf_home]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=DIARIZE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return [], (f"diarization timed out after {DIARIZE_TIMEOUT_S}s. It runs at roughly half "
                    f"real time on CPU, so an hour of audio needs about half an hour.")
    except Exception as exc:
        return [], f"could not start the pinned diarizer: {type(exc).__name__}: {exc}"
    try:
        payload = json.loads((done.stdout or "").strip().splitlines()[-1])
    except Exception:
        return [], (f"the pinned diarizer wrote no JSON (exit {done.returncode}). Its stderr is "
                    f"not repeated here because it names the audio file.")
    if "error" in payload:
        return [], payload["error"]
    order, turns = {}, []
    for turn in payload.get("turns", []):
        label = turn["speaker"]
        order.setdefault(label, len(order))
        turns.append((float(turn["start"]), float(turn["end"]), order[label]))
    turns.sort()
    return turns, ""


def run(wav_path, model_id=None, token="", num_speakers=None, min_speakers=1, max_speakers=8):
    """Cluster one track by voice. Returns `(turns, error)`; never raises.

    `turns` is `[(start_second, end_second, cluster_index)]`, sorted. It carries no identities and
    no names -- clustering is all it knows.

    **Prefers the pinned venv when it exists** (**V93**): on the `pyannote.audio` 4.x installed
    beside the product, `SpeakerDiarization` loads gated PLDA weights unconditionally, so the
    in-process path below needs a Hugging Face token no matter which model id it is given. The
    pinned 3.3.2 has no PLDA stage and runs from ungated weights. The in-process path is kept for
    the machine that never built the venv, and for an operator who *does* have a token.
    """
    model_id = (model_id or "").strip() or DEFAULT_MODEL_ID

    pinned = _pinned_python()
    if pinned and not token:
        turns, error = _run_pinned(pinned, wav_path, model_id, num_speakers,
                                   min_speakers, max_speakers)
        if not error:
            return turns, ""
        logger.warning("[Diarize] pinned runner failed (%s); trying in-process.", error)

    if not available():
        return [], f"{INSTALL_TARGET} is not installed"

    cloud, detail = is_cloud_pipeline(model_id, token)
    if cloud:
        return [], detail

    try:
        from pyannote.audio import Pipeline
    except Exception as exc:
        return [], f"{INSTALL_TARGET} would not import: {type(exc).__name__}: {exc}"

    try:
        pipeline = Pipeline.from_pretrained(model_id, token=(token or None))
    except TypeError:
        # Older signatures spell the argument differently. Tried rather than assumed, because a
        # wrong keyword here reads as an authentication failure.
        try:
            pipeline = Pipeline.from_pretrained(model_id, use_auth_token=(token or None))
        except Exception as exc:
            return [], _auth_hint(exc, model_id)
    except Exception as exc:
        return [], _auth_hint(exc, model_id)

    if pipeline is None:
        return [], (f"{model_id} could not be loaded. If it is gated, accept its terms on the "
                    f"model page with the account your token belongs to — or use "
                    f"`{UNGATED_ALTERNATIVE}`, which needs no token.")

    kwargs = {}
    if num_speakers:
        kwargs["num_speakers"] = int(num_speakers)
    else:
        kwargs["min_speakers"] = int(min_speakers)
        kwargs["max_speakers"] = int(max_speakers)
    try:
        output = pipeline(wav_path, **kwargs)
    except Exception as exc:
        return [], f"diarization failed: {type(exc).__name__}: {exc}"

    annotation = _annotation_from(output)
    if annotation is None:
        return [], f"{INSTALL_TARGET} returned {type(output).__name__}, which has no diarization"

    order, turns = {}, []
    for segment, _track, speaker in annotation.itertracks(yield_label=True):
        if speaker not in order:
            order[speaker] = len(order)
        turns.append((float(segment.start), float(segment.end), order[speaker]))
    turns.sort()
    logger.info("🗣️ [Diarize] %s: %d turns, %d voices", os.path.basename(wav_path),
                len(turns), len(order))
    return turns, ""


def _annotation_from(output):
    """Pull the diarization out of whatever the pipeline returned. `None` if there is none.

    **Read from `pyannote_audio-4.0.7`'s own source rather than guessed**, after an earlier
    version of this function called `itertracks` on the return value directly and would have
    raised `AttributeError` on the operator's very first press. 4.x returns a `DiarizeOutput`
    dataclass; 3.x returned an `Annotation`.

    `exclusive_speaker_diarization` is preferred, and its own comment is why: *"speaker
    diarization adapted to downstream transcription (does not contain overlapping speech
    turns)"*. That is exactly this use — attaching one label to one transcribed line. The
    plain `speaker_diarization` field keeps overlaps, which would give a single line two
    competing speakers with nothing to arbitrate between them.
    """
    for attribute in ("exclusive_speaker_diarization", "speaker_diarization"):
        annotation = getattr(output, attribute, None)
        if annotation is not None and hasattr(annotation, "itertracks"):
            return annotation
    return output if hasattr(output, "itertracks") else None


def _auth_hint(exc, model_id=DEFAULT_MODEL_ID):
    text = f"{type(exc).__name__}: {exc}"
    if "401" in text or "403" in text or "gated" in text.lower() or "token" in text.lower():
        return (f"{model_id} is gated. Accept its terms on the Hugging Face model page with the "
                f"account your token belongs to and paste that token into Settings — or set the "
                f"model to `{UNGATED_ALTERNATIVE}`, which needs no token at all. ({text})")
    return text


def speaker_at(turns, second, tolerance=0.5):
    """Which cluster owns `second`, or `None`. Nearest-overlap, then nearest-start within
    `tolerance` -- a transcript line's timestamp is the start of its *segment*, which need not
    coincide with a diarization boundary."""
    best, best_gap = None, None
    for start, end, index in turns:
        if start - tolerance <= second <= end + tolerance:
            gap = 0.0 if start <= second <= end else min(abs(second - start), abs(second - end))
            if best_gap is None or gap < best_gap:
                best, best_gap = index, gap
    return best


# ===== The identity guess, kept out of the transcript =====

# Titles a Taiwan hearing actually uses, plus a surname or given name in front of or behind them.
# Deliberately narrow: a wide net produces a table nobody can check, and the point of the table is
# that it *is* checkable.
# **A surname list rather than "any one to three characters".** The greedy version matched
# `那李主席` — it absorbed the preceding particle into the name — and a table with `那李主席` in
# it is a table the operator stops trusting. Anchoring on a real surname means a name this list
# does not know produces **no guess** rather than a wrong one, which is the safe direction: an
# empty row asks a question, a wrong row answers one.
_SURNAMES = (
    "王李張劉陳楊黃趙吳周徐孫馬朱胡郭何高林羅鄭梁謝宋唐許韓馮鄧曹彭曾蕭田董袁潘於蔣蔡余杜葉"
    "程蘇魏呂丁任沈姚盧姜崔鍾譚陸汪范金石廖賈夏韋付方白鄒孟熊秦邱江尹薛閻段雷侯龍史陶黎賀顧"
    "毛郝龔邵萬錢嚴賴覃洪武莫孔湯向常溫康施文牛樊葛邢安齊易喬伍龐顏倪莊聶章魯岳翟殷詹申歐耿"
)
_COMPOUND_SURNAMES = ("歐陽", "司馬", "諸葛", "上官", "夏侯", "皇甫", "端木", "東方", "獨孤")
_TITLES = ("委員", "主席", "部長", "署長", "司長", "處長", "局長", "次長", "議員", "市長",
           "縣長", "理事長", "執行長", "總經理", "教授", "律師", "檢察官", "法官")
_TITLE_RE = re.compile(
    "(" + "|".join(_COMPOUND_SURNAMES) + "|[" + _SURNAMES + "])"
    + "(" + "|".join(_TITLES) + ")")
_LATIN_NAME_RE = re.compile(r"\b(?:Mr|Ms|Mrs|Dr|Professor|Prof)\.?\s+([A-Z][a-z]+)")


def candidate_names(text):
    """Titles and names the transcript actually contains. Ordered, deduplicated."""
    found, seen = [], set()
    for match in _TITLE_RE.finditer(text or ""):
        name = match.group(0)
        if name not in seen:
            seen.add(name)
            found.append(name)
    for match in _LATIN_NAME_RE.finditer(text or ""):
        name = match.group(0)
        if name not in seen:
            seen.add(name)
            found.append(name)
    return found


def propose_titles(lines):
    """Guess who each label is, from who was addressed just before they spoke.

    `lines` is `[(second, label, text)]` in order. The evidence is deliberate: a title spoken in
    the line *immediately before* a speaker's first turns is usually someone handing over to them
    — "王委員請問" — and that is a fact the operator can check against the timestamp in seconds.

    Returns `[{label, guess, evidence, second}]`, one row per label, `guess` empty when nothing
    supports one. **It proposes; nothing here rewrites a transcript.**
    """
    rows, seen = [], []
    for index, (second, label, _text) in enumerate(lines):
        if label in seen:
            continue
        seen.append(label)
        guess, evidence, at = "", "", None
        # Look back over the preceding few turns for a title said by somebody else.
        for back in range(index - 1, max(index - 4, -1), -1):
            prev_second, prev_label, prev_text = lines[back]
            if prev_label == label:
                continue
            names = candidate_names(prev_text)
            if names:
                guess, evidence, at = names[-1], prev_text.strip()[:60], prev_second
                break
        rows.append({"label": label, "guess": guess, "evidence": evidence, "second": at})
    return rows


def render_table(rows, unmatched=()):
    """The proposal, as Markdown the operator reads and then applies themselves."""
    out = ["## 🗣️ Who is who — a guess, for you to confirm", ""]
    out.append("**Nothing below has been applied.** The transcript above carries only what the "
               "audio supports: lines that share a voice share a label. Matching a label to a "
               "person is an inference this application is not entitled to make on your behalf.")
    out.append("")
    out.append("Check each row, then do the replacement yourself — a find-and-replace over this "
               "file is enough, and it is reversible because the original label is still what the "
               "audio said.")
    out.append("")
    out.append("| Label | Guess | Why | When |")
    out.append("|---|---|---|---|")
    for row in rows:
        import datetime
        when = (str(datetime.timedelta(seconds=int(row["second"])))
                if row["second"] is not None else "—")
        guess = row["guess"] or "— nothing in the transcript suggests one"
        why = f"“{row['evidence']}”" if row["evidence"] else "—"
        out.append(f"| `{row['label']}` | {guess} | {why} | {when} |")
    if unmatched:
        out += ["", "**Named in the transcript but not matched to a voice**: "
                    + ", ".join(unmatched)
                    + ". Somebody was addressed by these titles; which voice they belong to is "
                      "not something the evidence above settles."]
    return "\n".join(out)
