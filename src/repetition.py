"""Fold recogniser loops in a re-listened line, without deleting the turn.

Whisper sometimes emits the same word or syllable until the segment ends (`Look at Look at…`,
`adadad…`, `ddtrace, and ddtrace…`). The re-listen pass is what a person reads afterwards, so
the loop is collapsed here. The live path is left alone (R9).

A run of the same n-gram becomes one copy of that n-gram plus 〔重複已摺疊〕. A segment that
is nothing but the loop is replaced by the marker alone: the turn stays, the degenerate text
does not.

The thresholds are set by what people say, because a false fold deletes real words from the
text a person relies on, while a missed fold only leaves noise to read past:

- one word or character (`no, no, no, no`, `對對對`, `謝謝謝謝`) is a loop at six repeats;
- a two-character Chinese unit (`好的好的好的`, `對啊對啊對啊`) is treated the same way;
- a longer phrase (`Look at`, `ddtrace, and`) is a loop at four repeats, so
  `thank you thank you thank you` stays;
- a word that tiles a syllable (`adadad…`) is a loop at five repeats of letters, so `www`,
  `hahaha`, `888` and `121212` stay;
- a run of digits is never a loop: `1.1.1`, `0.0.0.0` and phone numbers are data.
"""
import re

MARKER = "〔重複已摺疊〕"

# One CJK ideograph, or one Latin/digit word. Punctuation stays between tokens so
# "ddtrace, and" can repeat without the comma becoming part of the word.
_TOKEN = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"
    r"|[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?"
)

_MAX_NGRAM = 8
_MAX_PASSES = 20

_MIN_SHORT_REPEATS = 6      # one token, or a CJK unit of at most two characters
_MIN_PHRASE_REPEATS = 4     # anything longer
_MIN_SYLLABLE_REPEATS = 5   # `adadad…` inside one Latin word


def _is_cjk(token):
    return len(token) == 1 and bool(_TOKEN.fullmatch(token)) and not token.isascii()


def _latin_unit(word):
    """Shortest piece that tiles `word` at least three times, or None.

    `adadad` is `ad` three times. `ddtrace` does not tile, so it is left whole for the
    phrase pass.
    """
    folded = word.lower()
    if not folded.isalpha() or len(folded) < _MIN_SYLLABLE_REPEATS:
        return None
    for size in range(1, len(folded) // _MIN_SYLLABLE_REPEATS + 1):
        if len(folded) % size:
            continue
        times = len(folded) // size
        if times >= _MIN_SYLLABLE_REPEATS and folded[:size] * times == folded:
            return word[:size], times
    return None


def _tokens(text):
    return [(match.start(), match.end(), match.group()) for match in _TOKEN.finditer(text)]


def _best_run(tokens):
    """The repeated n-gram covering the most tokens, or None.

    A trailing partial copy counts (`ddtrace, and` four times, then one more `ddtrace`).
    The repeat counts are the module's thresholds; a pattern of digits is never a run.
    """
    keys = [token.lower() for _start, _end, token in tokens]
    count = len(keys)
    best = None
    max_n = min(_MAX_NGRAM, count // _MIN_PHRASE_REPEATS)
    for size in range(1, max_n + 1):
        fewest = _MIN_SHORT_REPEATS if size == 1 else _MIN_PHRASE_REPEATS
        for start in range(0, count - size * fewest + 1):
            pattern = keys[start:start + size]
            if all(key.isdigit() for key in pattern):
                continue
            short = size == 1 or (size == 2 and all(_is_cjk(tokens[start + k][2])
                                                    for k in range(size)))
            need = _MIN_SHORT_REPEATS if short else _MIN_PHRASE_REPEATS
            times = 1
            while start + (times + 1) * size <= count and keys[
                    start + times * size:start + (times + 1) * size] == pattern:
                times += 1
            if times < need:
                continue
            covered = times * size
            extra = 0
            while (extra < size and start + covered + extra < count
                   and keys[start + covered + extra] == pattern[extra]):
                extra += 1
            covered += extra
            # More tokens wins. The same coverage prefers the shorter unit, so six 對 collapse
            # to one 對 rather than to 對對, while "Look at" still wins because the single
            # words do not themselves repeat.
            rank = (covered, -size, -start)
            if best is None or rank > best[0]:
                best = (rank, start, size, times, extra)
    if best is None:
        return None
    _rank, start, size, times, extra = best
    return start, size, times, extra


def _collapse_latin_loops(text):
    tokens = _tokens(text)
    loops = []
    for index, (start, end, token) in enumerate(tokens):
        if _is_cjk(token):
            continue
        found = _latin_unit(token)
        if found:
            loops.append((index, start, end, found[0]))
    if not loops:
        return text
    if len(loops) == len(tokens):
        return MARKER
    out = []
    cursor = 0
    for _index, start, end, unit in loops:
        out.append(text[cursor:start])
        out.append(unit + MARKER)
        cursor = end
    out.append(text[cursor:])
    return "".join(out)


def _collapse_ngrams(text):
    for _pass in range(_MAX_PASSES):
        tokens = _tokens(text)
        found = _best_run(tokens)
        if not found:
            return text
        start, size, times, extra = found
        last = start + times * size + extra - 1
        if start == 0 and last == len(tokens) - 1:
            return MARKER
        span_start = tokens[start][0]
        span_end = tokens[last][1]
        keep_end = tokens[start + size - 1][1]
        kept = text[span_start:keep_end]
        text = text[:span_start] + kept + MARKER + text[span_end:]
    return text


def collapse_repetition(text):
    """Return `text` with recogniser loops folded. Empty input is unchanged."""
    if not text or not str(text).strip():
        return text
    text = _collapse_latin_loops(str(text))
    if text == MARKER:
        return text
    return _collapse_ngrams(text)
