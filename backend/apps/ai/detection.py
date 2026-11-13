"""The language a text is written in, as code on the server tells it, so nothing goes out to
learn it (D35)."""

import re
from functools import cache

from lingua import IsoCode639_1, Language, LanguageDetectorBuilder

# No detector tells these apart in a short text, and whoever reads one of them reads them all.
SAME = {"bs": "hr", "sr": "hr"}
SAMPLE = 1000
SURE = 0.5
# What a text carries besides its words: links, addresses, the long tokens that track a
# newsletter's reader and the invisible characters that pad its preview. Left in, they outweigh
# a short text's words and turn the detector to a language nobody wrote.
NOISE = re.compile(
    r"\[([^\]]*)\]\([^)]*\)|<[^>\s]*>|<!--.*?-->|https?://\S+|www\.\S+|\S+@\S+|\S{25,}"
    r"|[\u00ad\u034f\u180e\u200b-\u200f\u2060-\u2064\ufeff]+"
)
LETTER = re.compile(r"[^\W\d_]", re.U)


@cache
def _detector():
    return LanguageDetectorBuilder.from_all_languages().build()


def _code(language: Language) -> str:
    code = language.iso_code_639_1.name.lower()
    return SAME.get(code, code)


KNOWN = sorted({_code(language) for language in Language.all()})


def name_of(code: str) -> str:
    """The language's English name, which a model is told."""
    return Language.from_iso_code_639_1(IsoCode639_1.from_str(code)).name.title()


def language_in(text: str) -> str | None:
    """The language of the text's start, or None where too little of it or too mixed to tell."""
    sample = NOISE.sub(lambda found: found[1] or " ", text)[:SAMPLE]
    if len(LETTER.findall(sample)) < 2:
        return None
    sums: dict[str, float] = {}
    for found in _detector().compute_language_confidence_values(sample):
        code = _code(found.language)
        sums[code] = sums.get(code, 0) + found.value
    best = max(sums, key=sums.__getitem__, default=None)
    return best if best and sums[best] >= SURE else None
