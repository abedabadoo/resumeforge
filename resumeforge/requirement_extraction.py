"""Occupation-neutral requirement extraction based on sentence structure.

This module intentionally has NO industry, company, technology, or job-title
catalog. It finds actual work/qualification spans in a posting so an unseen
profession can still produce meaningful suggestions. A local LLM may later
group and prioritize these spans, but cannot introduce unsourced requirements.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .priorities import Passage, normalize

# General task verbs, not a closed list of occupations or skill keywords.
_VERB = (
    r"administer|analy[sz]e|assess|audit|build|coach|collaborate|"
    r"communicate|configure|coordinate|create|deliver|design|develop|"
    r"diagnose|document|drive|evaluate|facilitate|forecast|identify|"
    r"implement|improve|inspect|integrate|investigate|lead|maintain|"
    r"manage|mentor|monitor|operate|optimize|organize|oversee|"
    r"perform|plan|prepare|prioritize|process|provide|reconcile|"
    r"report|research|resolve|review|schedule|secure|set|support|"
    r"test|track|train|troubleshoot|verify"
)
_ACTION = re.compile(rf"^(?:(?:you(?: will|['’]ll)?|the candidate will|responsible for)\s+)?(?:{_VERB})\b", re.I)
_QUALIFICATION = re.compile(
    r"^(?:hands.on |demonstrated |strong |working |prior |some |real )?"
    r"(?:experience|expertise|proficiency|knowledge|familiarity|ability|comfort)"
    r"\s+(?:with|in|of|using|to)\s+", re.I)
_FILLER = re.compile(r"^(?:the|a|an|our|your|hands.on|directly|strong|some|real)\s+", re.I)
_COORD_ACTION = re.compile(rf"\s+(?:and|or)\s+(?:directly\s+)?(?:{_VERB})\b", re.I)
_STOP = re.compile(r"\b(?:in order to|so that|with room to|rather than|instead of|"
                   r"without the need for|who will|that will)\b", re.I)
_NON_REQUIREMENT = re.compile(
    r"^(?:we |our |this role |you(?:'ll| will) (?:enjoy|love|benefit)|"
    r"about |company |team |salary |pay |benefits?|equal opportunity|"
    r"limited sponsorship|must be legally authorized)\b", re.I)
_GENERIC = frozenset((
    "work", "working", "skills", "tools", "people", "teams", "the team",
    "customers", "software", "experience", "solutions", "a platform",
    "data", "systems", "technology", "projects", "information",
))


@dataclass(frozen=True)
class Extracted:
    label: str
    source: str
    section: str


def _focused_phrases(sentence: str) -> list[str]:
    """Extract action objects or qualification objects, never isolated tokens."""
    clause = sentence.strip(" .:;,*")
    if _NON_REQUIREMENT.search(clause):
        return []
    qualification = _QUALIFICATION.match(clause)
    action = _ACTION.match(clause)
    if not (qualification or action):
        return []
    clause = clause[(qualification or action).end():].strip(" ,:;")
    # For "Design, build, and manage X" remove coordination verbs but keep X.
    for _ in range(4):
        before = clause
        clause = re.sub(rf"^(?:,\s*|and\s+|&\s+)*(?:directly\s+)?(?:{_VERB})\b\s*", "", clause, count=1, flags=re.I)
        if clause == before:
            break
        clause = clause.lstrip(" ,")
    clause = _STOP.split(clause, maxsplit=1)[0]
    parts = _COORD_ACTION.split(clause)
    phrases: list[str] = []
    for part in parts[:4]:
        item = part.strip(" .:;,")
        while _FILLER.match(item):
            item = _FILLER.sub("", item, count=1)
        words = item.split()
        if len(words) > 14:
            # Avoid truncating into meaningless half-sentences.
            cut = re.search(r"[,;]|\b(?:including|such as|e\.g\.|for example)\b", item, re.I)
            if cut:
                item = item[:cut.start()].strip(" .,:;")
                words = item.split()
        if not 2 <= len(words) <= 14 or not 9 <= len(item) <= 110:
            continue
        if normalize(item) in _GENERIC:
            continue
        if re.search(r"\b(?:which|whom|who|we|you|we're|you'll|would|could|should)\b", item, re.I):
            continue
        phrases.append(item)
    return phrases


def extract(rows: list[Passage]) -> list[Extracted]:
    """Return source-literal requirements from core sections in posting order."""
    results = []
    seen = set()
    for row in rows:
        if row.section not in ("duties", "required"):
            continue
        for phrase in _focused_phrases(row.text):
            key = normalize(phrase)
            if key in seen:
                continue
            seen.add(key)
            results.append(Extracted(phrase, row.text, row.section))
    return results


def word_stems(text: str) -> set[str]:
    """Generic morphological overlap, deliberately not an industry thesaurus."""
    stop = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "into",
            "of", "on", "or", "the", "to", "using", "via", "with", "work",
            "experience", "skills", "strong", "required", "have", "will"}
    result = set()
    for word in re.findall(r"[a-z0-9+#]+", text.casefold()):
        if word in stop or len(word) < 3:
            continue
        if len(word) > 5 and word.endswith("ing"):
            word = word[:-3]
        elif len(word) > 5 and word.endswith("tion"):
            word = word[:-3]
        elif len(word) > 5 and word.endswith("ed"):
            word = word[:-2]
        elif len(word) > 5 and word.endswith("s"):
            word = word[:-1]
        result.add(word)
    return result


def grounded_label(label: str, quote: str) -> bool:
    """Require a nontrivial overlap for an LLM-paraphrased capability.

    The quote itself must also be verified against the supplied posting.
    This guards against unrelated model-suggested abilities being inserted.
    """
    label_tokens, quote_tokens = word_stems(label), word_stems(quote)
    overlap = label_tokens & quote_tokens
    return len(overlap) >= 2 or (len(label_tokens) == 1 and len(overlap) == 1
                                 and len(next(iter(overlap))) >= 6)
