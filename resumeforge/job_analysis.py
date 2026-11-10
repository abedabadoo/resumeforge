"""Combine posting structure with a local model's reading of the actual requirements."""
from __future__ import annotations

from pydantic import Field
from .laptop import ask
from .models import Keyword, Model
from .planning import _canonical, _evidence_for, analyze_job, keyword_matches
from .priorities import capability, literal_pattern, normalize, passages, score


class Requirement(Model):
    capability: str = Field(min_length=2, max_length=100)
    quote: str = Field(min_length=8, max_length=310)


class Reading(Model):
    requirements: list[Requirement] = Field(max_length=8)


_SYSTEM = """Read the posting as a hiring manager. Rank up to seven distinct capabilities by
how central they are to doing this job. Prioritize the title's specialty, required hands-on work,
and recurring responsibilities. Group alternative tools that demonstrate the same capability.
Treat preferred qualifications and long lists of interchangeable products as secondary. You may
choose an existing capability label or extract a specific phrase the initial list overlooked.
For each capability quote a short exact passage from the posting which explicitly names it.
The candidate's existing skills must not determine which requirements are important."""


def _capability_key(term):
    canonical = _canonical(term)
    group = capability(canonical)
    return normalize(group.label if group else canonical)


def analyze_posting(profile, job, keywords, settings):
    rows = analyze_job(profile, job, keywords)
    if settings.provider == "none" or not settings.model.strip() or not job.strip():
        return rows
    # Pass only posting content. Sample the beginning and the qualifications at
    # the end when a posting would otherwise overflow a small local context.
    excerpt = job if len(job) <= 12000 else job[:8000] + "\n…\n" + job[-4000:]
    try:
        reading = ask(settings, Reading, _SYSTEM,
                      {"posting": excerpt, "existing_capabilities": [row["term"] for row in rows[:28]]}, 850)
    except (RuntimeError, OSError):
        return rows

    by_label = {}
    by_alias = {}
    for row in rows:
        primary = by_label.setdefault(_capability_key(row["term"]), row)
        for alias in row["terms"]:
            by_alias.setdefault(_capability_key(alias), primary)
    quoted_source = " ".join(excerpt.casefold().split())
    records = [(e.id, e.text) for e in profile.evidence().values() if e.confirmed and e.role_id]
    by_model = {}
    for finding in reading.requirements:
        quote = " ".join(finding.quote.split())
        if quote.casefold() not in quoted_source:
            continue
        name = _capability_key(finding.capability)
        row = by_label.get(name) or by_alias.get(name)
        if row is None:
            if not literal_pattern(finding.capability).search(quote):
                continue
            ranking = score(passages(job), [finding.capability])
            if not ranking:
                continue
            _, weight, required, rationale = ranking
            target = Keyword(term=finding.capability, weight=weight, required=required, rationale=rationale)
            row = {**_evidence_for(target, records, profile.skills), "terms": [target.term]}
        if not any(keyword_matches(quote, term) for term in [row["term"], *row["terms"]]):
            continue
        key = _capability_key(row["term"])
        by_label.setdefault(key, row)
        if key not in by_model:
            row["posting_quote"] = quote
            by_model[key] = len(by_model)
    if not by_model:
        return rows
    explicit = {_capability_key(t) for t in keywords}
    structural = {}
    for index, row in enumerate(rows):
        structural.setdefault(_capability_key(row["term"]), index)

    def priority(row):
        key = _capability_key(row["term"])
        position = structural.get(key, len(rows))
        if key in explicit or row["rationale"] == "User requested priority.":
            return 2, -position
        base = 1 / (3 + position)
        support = .9 / (3 + by_model[key]) if key in by_model else 0
        if row["weight"] <= 2:
            support *= .25
        # Apply the model's ranking within each requirement tier. A new
        # quoted requirement can enter the core tier on the same evidence as
        # a known term. Optional suggestions cannot displace mandatory work.
        core = row["required"] or row["weight"] == 5
        return int(core), base + support

    return sorted(by_label.values(), key=priority, reverse=True)
