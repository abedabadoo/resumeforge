"""Occupation-neutral, evidence-backed Skills selection.

Job priorities are useful, but a resume Skills row should be based on:
  1. what the applicant actually lists or demonstrably uses,
  2. what the complete posting asks for (not just its first model keywords),
  3. what the final printable accomplishments demonstrate, and
  4. the finite amount of space left on the actual page.

New technical labels may be promoted from positively attributed achievements,
never from a job posting or an unselected example alone. No job-specific
whitelists or mandatory vendors are required.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Iterable

from .models import Candidate, Keyword, Profile
from . import priorities


# Generic English words and section labels must not become technology skills
# because they happen to be capitalized at the start of a sentence.
_NOT_TECHNOLOGIES = frozenset({
    "ability", "analyze", "applicants", "build", "candidate", "case",
    "cloud", "collaboration", "compliance", "communication", "computer",
    "coordinate", "create", "data", "develop", "design", "document",
    "engineer", "enterprise", "experience", "familiarity", "including",
    "investigation", "knowledge", "maintain", "manage", "monitor",
    "opportunities", "operations", "platform", "required", "responsibilities",
    "security", "software", "strong", "support", "systems", "technology",
    "the", "tools", "work", "workflow", "workflows",
    "certifications", "qualifications", "professional", "essential",
    "benefits", "salary", "office", "role", "education", "identity",
    "automation", "endpoint", "review", "reliability", "incident",
    "microsoft", "network", "access", "management", "technical",
    "stakeholders", "risk", "alerts", "ticket", "ticketing",
})
# A software or named tool appears in job text and an actual accomplishment.
# Require an operational context for a previously unknown proper name.
_USAGE_NEAR_TOOL = re.compile(
    r"\b(?:using|used|with|via|through|integrated with|implemented in|"
    r"configured in|developed in|built in|deployed with|operated|"
    r"administered|automated|monitored|managed|migrated to|"
    r"from|tested with|wrote in)\b", re.I)
_NAMED_WORD = re.compile(
    r"(?<![\w])(?:[A-Z][a-z]+[A-Z][A-Za-z0-9]*|"
    r"[A-Z][a-z]{2,}|[A-Z]{2,}(?:[/.-][A-Z0-9]+)*)(?![\w])")
_SECTION_POINTS = {"required": 140, "duties": 110, "preferred": 62, "other": 30}
_MAX_SKILLS = 18


@dataclass(frozen=True)
class SkillChoice:
    label: str
    score: float
    source: str


def _helpers():
    # Avoid a circular import: planning.rank_skills delegates to this module.
    from .planning import ALIASES, _canonical, _positive_use, keyword_matches
    return ALIASES, _canonical, _positive_use, keyword_matches


def _identity(value: str) -> str:
    from .planning import _canonical
    value = value.strip()
    # "Infrastructure as Code (IaC)" and "IaC" describe one capability.
    # Retain the user's full label when it is the first sourced spelling.
    bracket = re.match(r"^(.+?)\s*\(([A-Za-z0-9+.#/-]{2,15})\)$", value)
    if bracket and _canonical(bracket.group(1)).casefold() == _canonical(bracket.group(2)).casefold():
        value = bracket.group(1)
    return priorities.normalize(_canonical(value))


def _source_skills(profile: Profile) -> list[str]:
    result, seen = [], set()
    for label in profile.skills:
        label = " ".join(label.split())
        identity = _identity(label)
        if identity and identity not in seen:
            result.append(label)
            seen.add(identity)
    return result


def _candidates_from_work(profile: Profile, selected: Iterable[Candidate] | None,
                          job_description: str, keywords: list[Keyword]) -> list[str]:
    from .planning import ALIASES, _positive_use, keyword_matches
    if not profile.skills:
        # Keep the legacy semantics for an empty imported inventory when the
        # caller has not supplied actual printable achievements.
        if selected is None:
            return []
    confirmed = [e.text for e in profile.evidence().values()
                 if e.confirmed and e.role_id]
    selected = list(selected) if selected is not None else None
    shown = [c.text for c in selected if not c.needs_confirmation] if selected is not None else []
    # Original/confirmed work is relevant for a user-confirmed skill even when
    # the one-page layout selects a different bullet. Generated examples,
    # however, count only when they are actually printable.
    targets = [k.term for k in keywords if k.kind in ("tool", "skill", "domain")
               and k.term.strip()]
    targets += [name for name in ALIASES if keyword_matches(job_description, name)]
    names = list(dict.fromkeys(targets))
    additions, known = [], {_identity(x) for x in profile.skills}
    for name in names:
        if not name or len(name) > 60:
            continue
        canonical = _identity(name)
        if canonical in known:
            continue
        # Do not turn "case creation" or "opportunities" into technical
        # labels even if a role legitimately calls for these work activities.
        if name not in ALIASES and not any(
            name.casefold() == term.casefold()
            for term in ("Infrastructure as Code", "REST API")
        ):
            continue
        if any(_positive_use(text, name) for text in (confirmed + shown)):
            additions.append(name)
            known.add(canonical)

    if selected is not None and job_description:
        # Identify recognizable *unknown* vendor/application names without
        # building a new industry-specific dictionary for every job.
        for match in _NAMED_WORD.finditer(job_description):
            name = match.group()
            if name.casefold() in _NOT_TECHNOLOGIES or len(name) < 3:
                continue
            identity = _identity(name)
            if identity in known:
                continue
            # A standalone acronym is not automatically a skill merely
            # because it appears in compliance or legal boilerplate.
            if name.isupper():
                continue
            if any(_positive_use(text, name) and
                   any(_USAGE_NEAR_TOOL.search(text[max(0, m.start()-65):m.start()])
                       for m in re.finditer(r"(?<![\w])" + re.escape(name) + r"(?![\w])", text))
                   for text in shown):
                additions.append(name)
                known.add(identity)
    return additions


def _direct_job_points(skill: str, rows) -> float:
    _, _, _, match = _helpers()
    points = []
    for row in rows:
        if match(row.text, skill):
            points.append(_SECTION_POINTS.get(row.section, 30))
    return max(points, default=0.0)


def choices(profile: Profile, keywords: list[Keyword] | list[str],
            job_description: str = "", selected: Iterable[Candidate] | None = None,
            model_order: Iterable[str] = ()) -> list[SkillChoice]:
    """Return only evidenced skill labels with transparent relevance scores.

    Requirements are read from the job *independently of the applicant*.
    The candidate inventory is then reconciled against the source resume and
    the selected achievements. New labels require concrete use, never a
    desired-but-missing qualification.
    """
    from .planning import keyword_matches
    keys = [k if isinstance(k, Keyword)
            else Keyword(term=k, weight=max(1, min(5, len(keywords)-i)))
            for i, k in enumerate(keywords)]
    original = _source_skills(profile)
    if not keys and not job_description:
        return [SkillChoice(skill, 0, "source") for skill in original]
    selected_list = list(selected) if selected is not None else None
    additions = _candidates_from_work(profile, selected_list, job_description, keys)
    rows = priorities.passages(job_description) if job_description else []
    model_rank = {_identity(s): i for i, s in enumerate(model_order)}
    values, seen = [], set()
    original_ids = {_identity(label) for label in original}
    demonstrated = [c.text for c in selected_list if not c.needs_confirmation] if selected_list is not None else []

    for index, label in enumerate(original + additions):
        key = _identity(label)
        if key in seen:
            continue
        seen.add(key)
        direct = _direct_job_points(label, rows)
        kw_scores = []
        for position, requirement in enumerate(keys):
            if requirement.kind in ("credential", "strength"):
                continue
            weight = requirement.weight
            if keyword_matches(label, requirement.term):
                kw_scores.append(26 + weight * 13 / (1 + position / 18))
            elif priorities.related(label, requirement.term):
                kw_scores.append(7 + weight * 4 / (1 + position / 18))
        priority = max(kw_scores, default=0)
        display_bonus = 22 if any(keyword_matches(text, label) for text in demonstrated) else 0
        source_bonus = 4 if key in original_ids else 0
        suggested = 6 / (1 + model_rank[key]/6) if key in model_rank else 0
        score = direct + priority + display_bonus + source_bonus + suggested
        source = "source" if key in original_ids else "accomplishment"
        values.append((score, -index, SkillChoice(label, round(score, 2), source)))

    # A source skill can be legitimate without appearing in a posting; let
    # low-scoring ones trail rather than crowding out direct technical matches.
    values.sort(key=lambda item: (-item[0], -item[1]))
    return [choice for _, _, choice in values]


def select_skills(profile: Profile, keywords: list[Keyword] | list[str],
                  job_description: str = "", selected: Iterable[Candidate] | None = None,
                  model_order: Iterable[str] = (), limit: int = _MAX_SKILLS) -> list[str]:
    if limit < 0:
        raise ValueError("Skills limit cannot be negative")
    ranked = choices(profile, keywords, job_description, selected, model_order)
    if not ranked or not limit:
        return []
    if not job_description and not keywords:
        return [item.label for item in ranked[:limit]]
    # Once the posting provides meaningful matches, unrelated technologies
    # should not fill every available Skills slot merely because the profile
    # contains them. Keep a small transferable core as a fallback, but spend
    # the remaining space only on demonstrably relevant expertise.
    strongest = ranked[0].score
    if strongest >= 24:
        # A resume with a substantial existing skills inventory still needs
        # room for useful transferable technologies (e.g., a CI/CD platform
        # adjacent to a delivery requirement), not only literal matches.
        minimum = min(12, len(ranked), limit)
        cutoff = max(17.0, strongest * .16)
        relevant = [item for item in ranked if item.score >= cutoff]
        count = max(minimum, len(relevant))
        return [item.label for item in ranked[:min(count, limit)]]
    # When no requirements are recognizable, preserve the source order rather
    # than pretending the application can confidently rank unseen domains.
    return [item.label for item in ranked[:min(limit, max(8, len(profile.skills)))]]
