"""Combine posting structure with a local model's reading of the actual requirements."""
from __future__ import annotations

from typing import Literal
from pydantic import Field
from .laptop import ask
from .models import Keyword, Model
from .planning import (_canonical, _evidence_for, analyze_job, credential_requirement,
                       keyword_matches, valid_requirement_term)
from .priorities import capability, literal_pattern, normalize, passages, score


class Requirement(Model):
    capability: str = Field(min_length=2, max_length=100)
    quote: str = Field(min_length=8, max_length=310)
    kind: Literal["capability", "credential", "strength"] = "capability"


class Reading(Model):
    requirements: list[Requirement] = Field(max_length=8)


_SYSTEM = """Analyze ONLY the supplied hiring requirements. Rank up to seven distinct
job capabilities, prioritizing the specialty, hands-on responsibilities, and required
skills. Group alternative tools and languages into one OR requirement, not several
mandatory missing skills. Keep preferred qualifications lower than core duties.
Classify degrees, licenses and certifications separately from performable capabilities.
Ignore compensation, benefits, privacy disclosures, tracking codes, and recruiting
boilerplate. Never reuse requirements from a previous job or infer them from the
candidate resume. Reject fragments such as 'with application' and 'are multiplied'.
For every requirement supply an exact supporting quotation from the given posting.
Quote actual requirements; do not invent or paraphrase the quoted text."""


def _capability_key(term):
    canonical = _canonical(term)
    group = capability(canonical)
    return normalize(group.label if group else canonical)


def analyze_posting(profile, job, keywords, settings):
    rows = analyze_job(profile, job, keywords)
    if settings.provider == "none" or not settings.model.strip() or not job.strip():
        return rows
    # Exclude non-hiring sections before sending context to the model. Sending
    # the raw tail of a long job advert previously amplified salary/privacy text.
    cleaned = "\n".join(row.text for row in passages(job))
    excerpt = cleaned[:12000]
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
    education = [" ".join(x for x in (item.degree, item.detail) if x) for item in profile.education]
    if profile.certifications:
        education.append(profile.certifications)
    by_model = {}
    for finding in reading.requirements:
        quote = " ".join(finding.quote.split())
        # Passage parsing normalizes terminal punctuation, but the model may
        # legitimately quote the original sentence including its final period.
        if quote.casefold().rstrip(" .") not in quoted_source:
            continue
        name = _capability_key(finding.capability)
        row = by_label.get(name) or by_alias.get(name)
        if row is not None and finding.kind == "credential" and row.get("kind") != "credential":
            target = Keyword(term=row["term"], weight=row["weight"], required=row["required"],
                             rationale=row["rationale"], kind="credential")
            row = {**_evidence_for(target, records, profile.skills, education),
                   "terms": row.get("terms", [target.term])}
            by_label[_capability_key(row["term"])] = row
        if row is None:
            if not valid_requirement_term(finding.capability):
                continue
            if not literal_pattern(finding.capability).search(quote):
                continue
            ranking = score(passages(job), [finding.capability])
            if not ranking:
                continue
            _, weight, required, rationale = ranking
            kind = "credential" if (finding.kind == "credential" or credential_requirement(finding.capability)) \
                   else "strength" if finding.kind == "strength" else "skill"
            target = Keyword(term=finding.capability, weight=weight, required=required,
                             rationale=rationale, kind=kind)
            row = {**_evidence_for(target, records, profile.skills, education), "terms": [target.term]}
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
        if row.get("kind") == "credential":
            return -1, -(by_model.get(key, position) + position / 100)
        if key in explicit or row["rationale"] == "User requested priority.":
            return 2, -position
        base = 1 / (3 + position)
        support = .9 / (3 + by_model[key]) if key in by_model else 0
        if row["weight"] <= 3:
            support *= .25
        # Apply the model's ranking within each requirement tier. A new
        # quoted requirement can enter the core tier on the same evidence as
        # a known term. Optional suggestions cannot displace mandatory work.
        core = row["required"] or row["weight"] == 5
        return int(core), base + support

    return sorted(by_label.values(), key=priority, reverse=True)
