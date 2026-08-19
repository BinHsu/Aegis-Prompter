"""Whether a configured model still exists, and a prompt for finding a replacement.

**Every model id in this product is a settings field with a default, never a constant.** The
reason is not preference, it is arithmetic: whatever is pinned today eventually stops being
downloadable. `docs/decisions/0008` wrote half of this for the *package* -- *"'we do not need
updates' only holds while the artefact still exists"* -- and assumed weights were the safer half
because they are the vendor's own repositories. That assumption is too optimistic. A vendor
repository does not have to disappear to become unusable; it can simply acquire a gate, which is
what `pyannote/speaker-diarization-community-1` (`gated: auto`) demonstrates today.

So the default is a **dated suggestion, not a promise**, and this module exists to make that
honest in two ways:

1. **Say whether it is still there.** Cache first, Hub second -- a model already downloaded works
   forever regardless of what the Hub does, and that is the most useful answer when it applies.
2. **When it is not, hand the operator a prompt rather than a list.** Their agent does the
   searching. This app does not enumerate, rank or recommend models, for the same reason it does
   not run post-processing: it would be committing to maintain a judgement that goes stale.

**Why not a dropdown, when the numbers looked good.** A family-scoped query is small and official
-- `author="mlx-community", search="whisper"` returns a usable set. But **the metadata cannot tell
you which members load**: MLX conversions and transformers-format repositories of the same model
report the same `architectures` and the same `model_type`, and only the file list separates them.
What a replacement must satisfy is knowable *here*, from the backend's own requirements -- so this
module states those requirements and lets a search engine with judgement apply them.

**A replacement must also clear a criterion this module cannot check.** **R50** rules out
PRC-origin weights and PRC-origin loader packages, and no Hub field expresses that. Anything
proposed here has to be judged on provenance by whoever reads the prompt below, which is why the
prompt asks for it explicitly rather than leaving it to be inferred.
"""
# One entry per branch `transcriber.resolve_backend` can dispatch to. `prefix` is the dispatch
# rule itself, so the two cannot drift: `resolve_backend` imports this table rather than
# repeating the test.
#
# **There is one entry, and the shape is kept anyway.** A second family lived here until
# 2026-08-17 (`docs/decisions/0012`), and the table is what let it be removed in one place
# instead of hunted through the tree. Collapsing this to a constant would save a dozen lines and
# cost that.
#
# `requires` is what makes a repository loadable and is **not** visible in Hub metadata. Read from
# `mlx_whisper/load_models.py` on 2026-08-17, not guessed: it opens `config.json`, then loads
# `weights.safetensors` and falls back to `weights.npz`. The tokenizer needs nothing from the
# repository -- `mlx_whisper/tokenizer.py` reads its `.tiktoken` vocabularies from the package's
# own `assets/` directory. So a transformers-format Whisper repository, which ships
# `model.safetensors` and a `tokenizer.json`, will NOT load however correct its tags look.
FAMILIES = [
    {
        "id": "whisper",
        "prefix": "",
        "package": "mlx-whisper",
        "example": "mlx-community/whisper-large-v3-turbo",
        "search": {"author": "mlx-community", "search": "whisper"},
        "requires": ("config.json", "weights.safetensors"),
        "notes": "MLX-converted repositories only. `weights.npz` is accepted in place of "
                 "`weights.safetensors`; a repository shipping `model.safetensors` is the "
                 "transformers format and will not load. Verified against "
                 "`mlx_whisper/load_models.py`, 2026-08-17 — and the `npz` half is not "
                 "hypothetical: `mlx-community/whisper-large-v3-mlx` ships exactly that, so a "
                 "`requires` naming only `weights.safetensors` would reject a working model.",
    },
]


# Families this product used to dispatch to and now refuses. Kept as data rather than deleted
# outright for one reason, found by testing the upgrade path on 2026-08-17: `.env` is written by
# the app and **survives a version change**, so an operator who configured `Qwen/Qwen3-ASR-0.6B`
# still has that id in their settings after the model was removed. Without this, the weights are
# still in their cache, the settings screen reports the model as `cached`, and pressing Start
# fails inside MLX with `ModelDimensions.__init__() got an unexpected keyword argument
# 'architectures'` — which says nothing about what actually happened or what to do.
DISQUALIFIED_PREFIXES = {
    "qwen": "R50 — PRC-origin weights and loader package. Removed from this product on "
            "2026-08-17; see docs/decisions/0012.",
}


def disqualified_reason(model_id):
    """Why this id is refused, or `None` if it is not. Provenance, never quality."""
    head = (model_id or "").split("/", 1)[0].lower()
    for prefix, reason in DISQUALIFIED_PREFIXES.items():
        if head.startswith(prefix):
            return reason
    return None


def family_for(model_id):
    """Which backend would load this id. Same rule `resolve_backend` dispatches on.

    A disqualified id still resolves to a family here -- this answers "which loader would try",
    not "may it". `resolve_backend` is where the refusal lives, because that is the point where
    something is about to be loaded.
    """
    head = (model_id or "").split("/", 1)[0].lower()
    for family in FAMILIES:
        if family["prefix"] and head.startswith(family["prefix"]):
            return family
    return FAMILIES[-1]


# Availability states. `cached` outranks everything: a model on disk works whatever the Hub does,
# which is the whole point of the fixed cache layout under a storage root (R48, V47).
CACHED = "cached"
AVAILABLE = "available"
GATED = "gated"
MISSING = "missing"
UNKNOWN = "unknown"


def availability(model_id, allow_network=True):
    """Whether `model_id` can still be obtained. Returns a dict; never raises.

    Cache first and without touching the network, because "you already have it" is both the most
    common answer and the only one that stays true offline. The Hub is consulted only when the
    cache misses and the caller permits it.
    """
    result = {"model": model_id, "state": UNKNOWN, "detail": "", "gated": False}
    if not (model_id or "").strip():
        return dict(result, detail="no model configured")

    try:
        import bootstrap
        if bootstrap.weights_present(model_id):
            return dict(result, state=CACHED,
                        detail="already downloaded — this machine keeps working whatever the "
                               "Hub does")
    except Exception:
        pass

    if not allow_network:
        return dict(result, detail="not downloaded, and availability was not checked")

    try:
        from huggingface_hub import HfApi
        info = HfApi().model_info(model_id, expand=["gated", "downloads"])
    except Exception as exc:
        name = type(exc).__name__
        if "RepositoryNotFound" in name or "EntryNotFound" in name or "404" in str(exc):
            return dict(result, state=MISSING, detail="the Hub has no such repository")
        if "Gated" in name or "401" in str(exc) or "403" in str(exc):
            return dict(result, state=GATED, detail=f"{name}: access is restricted")
        return dict(result, detail=f"could not be checked ({name})")

    gated = bool(getattr(info, "gated", False))
    if gated:
        return dict(result, state=GATED, gated=True,
                    detail="the vendor gates this repository — it needs a Hugging Face account, "
                           "accepted terms and a token, none of which this app has")
    return dict(result, state=AVAILABLE,
                detail=f"on the Hub, {getattr(info, 'downloads', 0) or 0} downloads")


def build_search_prompt(model_id):
    """A prompt for the operator's own agent to find a replacement. Pure: no I/O.

    It states requirements rather than naming candidates. Naming candidates would mean this
    project maintaining a judgement about models, which is the thing that goes stale and the
    thing the operator has said repeatedly they do not want the app doing.
    """
    family = family_for(model_id)
    requires = ", ".join(f"`{name}`" for name in family["requires"])
    lines = [
        f"Find me a speech-recognition model on Hugging Face that can replace "
        f"`{model_id or family['example']}`, which I can no longer download.",
        "",
        "It has to satisfy all of these, and the last one is the trap:",
        "",
        f"- loadable by the Python package **{family['package']}**;",
        f"- the repository must actually contain {requires} — this is not visible in the Hub's "
        f"metadata, so check the file list, not the tags;",
        "- transcribes Mandarin and English, including sentences that switch between them "
        "mid-utterance;",
        "- small enough to run on Apple Silicon through MLX — roughly 0.6B to 2B parameters;",
        "- must not be gated: I need to download it without a token or accepting terms;",
        "- **neither the weights nor the loader package may originate from a PRC vendor or "
        "maintainer.** This is a procurement constraint, not a quality judgement, and no Hub "
        "field expresses it — say who published the weights and who maintains the Python "
        "package, and how you established it.",
        "",
        f"Note: {family['notes']}",
        "",
        f"A search that finds the right family is roughly "
        f"`{family['search']}` against the Hub API, but do not trust it to be complete — the "
        "weights may live under the vendor's own account rather than under a porting org.",
        "",
        "Give me repository ids and, for each, say which of the requirements above you actually "
        "verified and which you assumed. Do not recommend one you have not checked the file list "
        "for.",
    ]
    return "\n".join(lines)


def replacement_advice():
    """Where the durable answer to "which model now" lives. Not a list, a method."""
    return (
        "The lasting answer is not a list. `docs/decisions/0012` records why the current default "
        "is what it is — a supply-chain constraint (R50) applied on top of the four-candidate "
        "comparison in `docs/decisions/0009` — and `tools/asr_bakeoff.py` still runs against the "
        "fixtures, so a replacement can be judged the same way this one was rather than by "
        "popularity. R11 requires the choice to be re-examined rather than inherited; a default "
        "that stops downloading is that re-examination arriving on its own schedule. Judge "
        "provenance first: it disqualifies candidates no measurement would reject."
    )
