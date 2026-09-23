"""Conservative offline review of real documents; no simulated AI conclusions."""

import hashlib
import re
from difflib import SequenceMatcher

from .evidence import unique_evidence
from .models import (
    Document,
    Evidence,
    Finding,
    Function,
    FunctionMapping,
    Unit,
    UnitMapping,
)


def stable_id(prefix: str, *parts: str) -> str:
    return prefix + "_" + hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def norm(text: str) -> str:
    text = re.sub(r"^\s*\d+(?:\.\d+)*[.)]?\s*", "", text)
    return " ".join(re.findall(r"[\w-]+", text.lower().replace("ё", "е")))


def similarity(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if a == b:
        return 1.0
    if min(len(a), len(b)) >= 60 and (a in b or b in a):
        return (
            0.86  # Expanded clauses retain a candidate; containment is not equivalence.
        )
    tokens_a, tokens_b = set(a.split()), set(b.split())
    union = tokens_a | tokens_b
    overlap = len(tokens_a & tokens_b) / max(1, len(union))
    return max(overlap, SequenceMatcher(None, a, b, autojunk=False).ratio())


# Names are harvested from source text, not from fixture-specific expected changes.
UNIT_PATTERNS = [
    r"Департамент\s+[А-Яа-яЁёA-Za-z-]+(?:\s+[а-яёa-z-]+){0,10}",
    r"(?:[A-Z][A-Za-z&-]*\s+){1,5}(?:Department|Division|Office|Committee|Team)\b",
    r"(?:Department|Division|Team)\s+(?:of\s+)?[A-Z][A-Za-z& -]{2,65}",
]


def local_units(documents: list[Document]) -> list[Unit]:
    output: dict[tuple[str, str], Unit] = {}
    for doc in documents:
        for chunk in doc.chunks:
            names = [
                m.group().strip()
                for p in UNIT_PATTERNS
                for m in re.finditer(p, chunk.text)
            ]
            if re.search(r"Блок[а]?\s+внутреннего\s+аудита.*?БВА", chunk.text):
                names.append("БВА")
            for name in names:
                # Drop tails that are prose, rather than part of the observed unit name.
                name = re.split(
                    r"\s+(?:осуществляет|обеспечивает|подчиняется|является|shall|must|is|owns|manages)\b",
                    name,
                )[0]
                key = (doc.side, norm(name))
                quote = chunk.text
                ref = Evidence(chunk_id=chunk.id, quote=quote)
                if key in output:
                    output[key].evidence = unique_evidence(
                        output[key].evidence + [ref]
                    )[:4]
                else:
                    output[key] = Unit(
                        id=stable_id("u", *key),
                        name=name,
                        side=doc.side,
                        evidence=[ref],
                    )
    return list(output.values())


def aliases(unit: Unit) -> list[str]:
    found = [unit.name]
    if unit.name.startswith("Департамент "):
        found.append(unit.name.replace("Департамент ", "департамента ", 1))
    for ev in unit.evidence:
        pattern = re.escape(unit.name) + r"\s*\(([A-ZА-ЯЁ]{2,15})\)"
        found.extend(re.findall(pattern, ev.quote))
    return list(set(found))


def local_functions(documents: list[Document], units: list[Unit]) -> list[Function]:
    results: dict[tuple[str, str, str], Function] = {}
    responsibility = re.compile(
        r"организ|провед|провод|обеспеч|контрол|готовит|разработ|осуществ|согласов|утверж|анализ|планир|оцени|оценк|распредел|несет|отвеч|shall|must|responsib|manag|review|audit|monitor|approv|maintain|prepare",
        re.IGNORECASE,
    )
    for doc in documents:
        scoped = [u for u in units if u.side == doc.side]
        active: list[Unit] = []
        heading_refs: list[Evidence] = []
        parent_section = ""
        for chunk in doc.chunks:
            text = chunk.text
            owner_matches = [
                u
                for u in scoped
                if any(
                    re.search(
                        r"(?<!\w)" + re.escape(a) + r"(?!\w)", text, re.IGNORECASE
                    )
                    for a in aliases(u)
                )
            ]
            sec = re.match(r"^(\d+\.\d+)(?:\.|\s)", text)
            is_heading = len(text) < 220 and (
                bool(re.search(r":\s*\d*\s*$", text))
                or (chunk.section and chunk.section == text)
            )
            if sec and parent_section and sec.group(1) != parent_section:
                active, heading_refs = [], []
                parent_section = ""
            if is_heading:
                active = owner_matches
                heading_refs = (
                    [Evidence(chunk_id=chunk.id, quote=text)] if active else []
                )
                parent_section = sec.group(1) if sec else ""
                continue
            if len(text) < 35 or not responsibility.search(text):
                continue
            # Prefer a governing heading; mere mentions can be counterparties, so local ownership remains provisional.
            owners = active or owner_matches
            if not owners:
                continue
            # Exclude membership lists, broad governance definitions and document contents.
            if re.search(
                r"состоит из следующих|составе следующих должностей|содержание",
                text,
                re.IGNORECASE,
            ):
                continue
            for unit in owners:
                refs = unique_evidence(
                    [Evidence(chunk_id=chunk.id, quote=text)] + heading_refs
                )
                key = (doc.side, unit.id, norm(text))
                if key not in results:
                    results[key] = Function(
                        id=stable_id("f", *key),
                        unit_id=unit.id,
                        description=text,
                        side=doc.side,
                        evidence=refs,
                    )
    return list(results.values())


def local_unit_matches(units: list[Unit]) -> list[UnitMapping]:
    before, after = (
        [u for u in units if u.side == "before"],
        [u for u in units if u.side == "after"],
    )
    matched: set[str] = set()
    mappings = []
    for a in before:
        b = next((b for b in after if norm(a.name) == norm(b.name)), None)
        if b:
            matched.add(b.id)
        mappings.append(
            UnitMapping(
                id=stable_id("um", a.id),
                before_ids=[a.id],
                after_ids=[b.id] if b else [],
                status="unchanged" if b else "uncertain",
                confidence=1.0 if b else 0.35,
                explanation="The same unit name appears in both sets. This establishes name continuity only; duties may differ."
                if b
                else "This exact unit name was not extracted from the AFTER set. A rename, reassignment or extraction gap requires human review; removal is not established.",
                evidence=unique_evidence(
                    a.evidence[:1] + (b.evidence[:1] if b else [])
                ),
            )
        )
    for b in after:
        if b.id not in matched:
            mappings.append(
                UnitMapping(
                    id=stable_id("um", b.id),
                    before_ids=[],
                    after_ids=[b.id],
                    status="uncertain",
                    confidence=0.4,
                    explanation="This unit name appears in AFTER and has no exact-name match in BEFORE. It may be new, renamed or outside the earlier documents; creation is not established.",
                    evidence=b.evidence[:1],
                )
            )
    return mappings


def local_function_matches(functions: list[Function]) -> list[FunctionMapping]:
    before, after = (
        [f for f in functions if f.side == "before"],
        [f for f in functions if f.side == "after"],
    )
    # Global ordering avoids earlier weak matches consuming later exact matches.
    candidates = sorted(
        (
            (similarity(a.description, b.description), a, b)
            for a in before
            for b in after
        ),
        key=lambda x: x[0],
        reverse=True,
    )
    paired: dict[str, tuple[float, Function]] = {}
    used: set[str] = set()
    best = {}
    for score, a, b in candidates:
        best.setdefault(a.id, (score, b))
        if score >= 0.58 and a.id not in paired and b.id not in used:
            paired[a.id] = (score, b)
            used.add(b.id)
    mappings = []
    for a in before:
        pair = paired.get(a.id)
        score, b = pair if pair else (0.0, None)
        exact = score == 1
        match_type = "unchanged" if exact else "uncertain" if b else "potential_loss"
        explanation = (
            "Wording matches after removing clause numbering and punctuation. Ownership still requires validation."
            if exact
            else f"Candidate based on lexical similarity ({score:.0%}), not semantic equivalence. Changed wording and ownership require review."
            if b
            else "No sufficiently similar one-to-one text match was found in the extracted AFTER responsibilities. This is a review candidate, not proof of loss. Renumbering, split duties or incomplete extraction may explain it."
        )
        competing = best.get(a.id)
        extra_evidence = []
        if b is None and competing and competing[0] >= 0.58:
            match_type = "uncertain"
            explanation = "A similar AFTER duty was matched to another BEFORE responsibility. This may represent shared wording, merged duties or an ownership ambiguity. It must not be interpreted as a lost function."
            extra_evidence = competing[1].evidence
        mappings.append(
            FunctionMapping(
                id=stable_id("fm", a.id),
                before_ids=[a.id],
                after_ids=[b.id] if b else [],
                match_type=match_type,
                confidence=1 if exact else min(score, 0.6) if b else 0.3,
                explanation=explanation,
                evidence=unique_evidence(
                    a.evidence + (b.evidence if b else []) + extra_evidence
                ),
            )
        )
    for b in after:
        if b.id not in used:
            mappings.append(
                FunctionMapping(
                    id=stable_id("fm", b.id),
                    before_ids=[],
                    after_ids=[b.id],
                    match_type="uncertain",
                    confidence=0.35,
                    explanation="No one-to-one BEFORE candidate was selected. Newly added wording, a split duty or extraction differences require review.",
                    evidence=b.evidence,
                )
            )
    return mappings


def local_findings(
    functions: list[Function], mappings: list[FunctionMapping]
) -> list[Finding]:
    results = []
    for m in mappings:
        if m.match_type == "potential_loss":
            results.append(
                Finding(
                    id=stable_id("issue", m.id),
                    category="loss",
                    title="Responsibility needs an AFTER owner",
                    explanation=m.explanation,
                    severity="medium",
                    confidence=m.confidence,
                    evidence=m.evidence,
                    recommendation="Check the full AFTER document set, including renamed units and delegated duties. Confirm an accountable owner before declaring the function lost.",
                )
            )
    after = [f for f in functions if f.side == "after"]
    seen = set()
    for i, a in enumerate(after):
        for b in after[i + 1 :]:
            if (
                a.unit_id == b.unit_id
                or a.evidence[0].chunk_id == b.evidence[0].chunk_id
            ):
                continue
            score = similarity(a.description, b.description)
            key = tuple(sorted((a.id, b.id)))
            if score >= 0.88 and key not in seen:
                seen.add(key)
                results.append(
                    Finding(
                        id=stable_id("issue", *key),
                        category="duplication" if score == 1 else "overlap",
                        title="Similar duties are attributed to different units",
                        explanation="The cited AFTER duties have "
                        + (
                            "identical normalized wording."
                            if score == 1
                            else f"{score:.0%} lexical similarity."
                        )
                        + " Similar wording can describe legitimate shared work; accountability overlap is not established.",
                        severity="low",
                        confidence=0.55,
                        evidence=unique_evidence(a.evidence + b.evidence),
                        recommendation="Verify the provisional unit assignments and compare scope, authority, handoffs and accountability with the document owners.",
                    )
                )
    return results
