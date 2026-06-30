"""Local LLM summary layer over the offline transcript.

This module turns a finished, bilingual (zh/en) meeting transcript into a grounded summary
using mlx-lm in-process on Apple Silicon — the same "no daemon, no network" posture as the
mlx-whisper transcriber. It is a pure-local sibling of retranscribe.py: load a small instruct
model, build a constrained prompt, generate, return text. Nothing leaves the machine.

Design rules that keep the no-summary paths cheap:

  - mlx_lm is imported LAZILY inside summarize(). Importing this module (e.g. for unit tests or
    the live Streamlit app) never pulls in mlx-lm and never triggers a model download.
  - build_summary_prompt() is a PURE function — no model, no I/O — so the prompt contract is unit
    testable without the heavy dependency.
  - summarize() never raises on model failure. The transcript is already on disk; a failed
    summary returns a clear error string the caller writes verbatim, so it can never corrupt the
    transcript outputs.

The model id is overridable via the SUMMARY_MODEL env var. The default is a small multilingual
Qwen2.5 Instruct (4-bit) that handles mixed Chinese/English and downloads on first use.
"""
import os
import logging

logger = logging.getLogger("Summarizer")

# Small multilingual instruct model. Qwen2.5 handles mixed zh/en well; the 4-bit MLX build keeps
# the download and memory footprint modest. Verified to resolve on Hugging Face as an
# mlx-community repo. Override with the SUMMARY_MODEL env var.
DEFAULT_SUMMARY_MODEL = "mlx-community/Qwen2.5-3B-Instruct-4bit"

# Generation cap. A meeting summary is short by design; this bounds latency and memory.
MAX_SUMMARY_TOKENS = 1024


def _auto_summarize_enabled(env_val):
    """Parse the AUTO_SUMMARIZE_ON_EXIT env value into a bool. Default ON: anything other than a
    case-insensitive "false" enables it (None/unset/empty -> True). Lives here (not app.py) so it
    is unit-testable without importing the Streamlit app, and importing it pulls in no mlx-lm."""
    if env_val is None:
        return True
    return env_val.strip().lower() != "false"


def resolve_summary_model(env_model=None):
    """Return the summary model id: explicit env value wins, else DEFAULT_SUMMARY_MODEL.

    Pure helper (no model load) so the id-resolution rule is testable. An empty/whitespace env
    value falls back to the default, matching how transcriber.resolve_default_model treats unset."""
    if env_model is None:
        env_model = os.environ.get("SUMMARY_MODEL")
    if env_model and env_model.strip():
        return env_model.strip()
    return DEFAULT_SUMMARY_MODEL


def build_summary_prompt(transcript_text):
    """Build the full instruction string for a grounded, bilingual-aware meeting summary.

    PURE function: no model, no I/O. The returned string embeds the transcript and instructs the
    model to summarize ONLY what the transcript contains — no invented facts, names, or numbers —
    and to emit four fixed sections. Any empty input still yields a valid, well-formed prompt."""
    transcript_text = "" if transcript_text is None else str(transcript_text)
    return (
        "You are a meeting minutes assistant. The transcript below is a bilingual (Chinese/English) "
        "conversation. Write a clear, faithful summary.\n"
        "\n"
        "Strict grounding rules:\n"
        "- Use ONLY information present in the transcript. Do NOT invent facts, names, numbers, "
        "dates, or decisions.\n"
        "- Preserve the original language of quoted terms; you may write the summary bilingually "
        "where it aids clarity, but never translate a fact into a different claim.\n"
        "- If a section has no supporting content in the transcript, write \"None\" under it.\n"
        "\n"
        "Produce exactly these four sections, using these headers:\n"
        "## TL;DR\n"
        "A 1-3 sentence overview.\n"
        "## Key Points\n"
        "Bulleted main topics and facts actually discussed.\n"
        "## Decisions\n"
        "Bulleted decisions that were explicitly made.\n"
        "## Action Items\n"
        "Bulleted tasks, each with its owner if the transcript states one (e.g. \"- [Owner] task\"); "
        "omit the owner only when none is stated.\n"
        "\n"
        "=== TRANSCRIPT START ===\n"
        f"{transcript_text}\n"
        "=== TRANSCRIPT END ===\n"
    )


def summarize(transcript_text, model=None):
    """Load the mlx-lm model, build the prompt, generate, and return the summary string.

    The model id is `model` if given, else the SUMMARY_MODEL env var, else DEFAULT_SUMMARY_MODEL.
    mlx_lm is imported here (lazy) so module import stays free of the heavy dependency and never
    downloads a model. On any load/generation failure this logs and returns a clear error string
    rather than raising — the transcript is already persisted and must not be put at risk."""
    model_id = model or resolve_summary_model()

    try:
        from mlx_lm import load, generate
    except Exception as e:  # mlx-lm not installed in this environment.
        logger.error("mlx-lm import failed: %s", e)
        return (
            f"[summary unavailable] mlx-lm is not installed ({e}). "
            "Install it into the venv (pip install mlx-lm) to enable summaries."
        )

    try:
        logger.info("Loading summary model: %s", model_id)
        llm, tokenizer = load(model_id)
    except Exception as e:
        logger.error("Summary model load failed (%s): %s", model_id, e)
        return f"[summary unavailable] failed to load model '{model_id}': {e}"

    try:
        prompt = build_summary_prompt(transcript_text)
        # Apply the model's chat template when available so the instruct model is prompted in the
        # format it was tuned for; fall back to the raw prompt otherwise.
        apply_template = getattr(tokenizer, "apply_chat_template", None)
        if apply_template is not None:
            try:
                prompt = apply_template(
                    [{"role": "user", "content": prompt}],
                    add_generation_prompt=True,
                    tokenize=False,
                )
            except Exception as e:
                logger.warning("Chat template unavailable, using raw prompt: %s", e)

        logger.info("Generating summary (max_tokens=%d)", MAX_SUMMARY_TOKENS)
        text = generate(llm, tokenizer, prompt, max_tokens=MAX_SUMMARY_TOKENS, verbose=False)
        return (text or "").strip() or "[summary unavailable] model returned empty output."
    except Exception as e:
        logger.error("Summary generation failed: %s", e)
        return f"[summary unavailable] generation error: {e}"
