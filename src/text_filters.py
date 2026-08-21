"""Pure text filters applied to ASR output before it reaches the dialogue buffer.

Adopted from `origin/feat/streaming-transcriber` per `docs/decisions/0006` -- the one piece that
record marks adoptable as-is. It lives in its own module rather than as staticmethods on
`Transcriber` for one practical reason: importing `transcriber` pulls `webrtcvad`,
`sounddevice` and `mlx_whisper`, so its boundary tests could only run on a machine with the full
audio stack installed. The logic is pure, so keeping it importable on its own is what lets the
tests actually be run rather than skipped.

Nothing here may grow a dependency. If it needs one, it belongs in `transcriber.py` instead.
"""

# Deliberately empty since 2026-08-12. Every string this list ever held — `字幕`, `Subtitles`,
# `Amara.org`, `請訂閱`, `Thank you.`, `謝謝`, `I don't know.`, `Bye.` — was judged "implausible as
# real meeting speech", and that judgement was made from one scenario: a legislative hearing. A
# fork transcribing a podcast, a review show or a language class says every one of them in earnest.
# **We cannot predict what a forker records, so we do not guess which words they never say.**
#
# The list stays empty, but not for the reason first written here. That reason -- "the shipped model
# produced text on zero of 441 non-speech calls, so a filter that catches nothing can only destroy
# something" -- was measured on 63 distinct synthesized sounds repeated seven times. On real
# non-speech the model shipping at the time produced text on **23 of 253** segments (V60):
# laughter, coughing, sneezing, and room tone below -45 dBFS with no speech in it.
#
# What survives that correction is the argument from *content*. All eight deleted strings were
# checked against every string the real-audio probe produced: zero matches. Laughter yields
# `Laughter.` and `Ha ha ha.`, which a list could hold -- and `I would like to come for tea.`, a
# fluent invented sentence no list could anticipate. A blacklist reaches the harmless half of this
# and not the half that would mislead a speaker, while every entry stays able to destroy a real
# utterance. That is why it is empty, and it is a weaker claim than the one it replaces: R37 is
# **not** satisfied by the model alone, and nothing in this file closes that gap.
#
# ⚠️ **2026-08-17: the model changed, and the second half of that argument got weaker again.**
# `docs/decisions/0012` replaced the ASR model on supply-chain grounds (R50), and the replacement
# produces text on **252 of 253** of the same real non-speech segments, 243 of which reach the
# buffer (V72). Two things follow, and they point in opposite directions -- which is why this is a
# note and not an edit:
#
#   - **The list would now catch something.** The strings this model invents include `Bye.`, which
#     the deleted list held. The "zero matches" finding above was about a different model.
#   - **The reason for emptying it has not changed.** It was emptied because a fork transcribing a
#     podcast, a review show or a language class says every one of those words in earnest, and
#     because the dangerous output -- a fluent invented sentence -- is the half no list reaches.
#     Neither of those depends on which model is loaded.
#
# **So this is the operator's decision, not a consequence of the model swap, and it has not been
# taken.** Restoring entries here reverses an explicit decision made 2026-08-12 with its reasoning
# recorded. Raised in `STATE.md` and `docs/decisions/0012`; left alone here.
#
# Hallucination removal belongs to the post-meeting cleanup pass, where the full transcript is
# available and an operator reads the result before anyone acts on it. The live path gives the
# gist (R9); it does not adjudicate.
#
# **Before adding an entry here, measure that this deployment produces it.** A string somebody
# once saw in a subtitle corpus is not evidence about your audio.
HALLUCINATION_PHRASES = []

# Trailing punctuation that carries no meaning for phrase equality. Both ASCII and CJK forms,
# because a bilingual meeting produces both (R8).
_TRAILING_PUNCTUATION = ".。!！?？,，、…"


def normalize_phrase(text):
    """Strip surrounding whitespace and trailing punctuation, lower-case Latin.

    Used only to compare a whole utterance against a known hallucination phrase -- never to
    alter what is stored. Transcript content is never normalised (R38, R3).
    """
    return text.strip().strip(_TRAILING_PUNCTUATION).strip().lower()


def is_acceptable(text):
    """Whether an utterance should reach the buffer.

    **This drops almost nothing, and that is the decision, not an oversight.** The length test
    below measures the raw string, and the model terminates nearly every utterance with
    punctuation -- so `哦。`, `嗯。` and `啊！` are two characters and pass. In practice the only
    thing it removes is a lone punctuation mark. Chosen by the operator 2026-08-12 after that was
    measured in production (**V64**), against two alternatives:

    - **Normalise before measuring length.** Consistent, and it would also drop `是。`, `不。` and
      `Yes.`. In a hearing, a witness answering "Yes." is among the most consequential things
      said, and with retention off (R16) nothing recovers it. Rejected for the same reason the
      hallucination blacklist was emptied: **noise costs a line, a destroyed answer costs the
      record.**
    - **Remove the guard entirely.** Barely different -- a lone `.` would reach the buffer. Not
      worth a change.

    So short noise **reaches the transcript on purpose**. Chewing, throat-clearing and laughter
    produce it (V60, V62), it is visible, and a person can see it for what it is. Removing it
    belongs to the post-meeting cleanup pass (R49), where the whole transcript is present and an
    operator reads the result before anyone acts on it. The live path owes the gist (R9), not a
    clean record.

    Also drops text that is **exactly** a known hallucination phrase -- of which there are
    currently none.

    The boundary is the whole normalised utterance, not a substring. That is the entire point of
    this function: matching as a substring destroyed real speech that merely contained one of
    these words -- "謝謝大家" and "Okay, thank you, see you" were discarded as ghosts, and with
    retention off there was no recording to recover them from (V48, R3). Trailing punctuation
    and Latin case are ignored, so "Thank you", "Thank you." and "THANK YOU." all match.
    """
    # Raw length, deliberately: see above. Normalising here is the change that looks like a bug
    # fix and is a policy reversal.
    if not text or len(text) <= 1:
        return False
    normalized = normalize_phrase(text)
    return not any(normalized == normalize_phrase(phrase) for phrase in HALLUCINATION_PHRASES)
