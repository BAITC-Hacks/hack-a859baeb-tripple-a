"""Regressions for real quotations attached to unsupported organizational claims."""

import json

import pytest
from app import ai, pipeline
from app.models import Chunk, Document, Evidence, Function, FunctionMapping, Unit


def sources():
    return [
        Document(
            id=side,
            filename=f"{side}.pdf",
            document_type="pdf",
            side=side,
            chunks=[
                Chunk(
                    id=f"{side}-audit",
                    document_id=side,
                    text="Audit Department checks internal controls.",
                    page=1,
                ),
                Chunk(
                    id=f"{side}-treasury",
                    document_id=side,
                    text="Treasury Department pays salaries."
                    if side == "before"
                    else "Treasury Department approves grants.",
                    page=2,
                ),
            ],
        )
        for side in ("before", "after")
    ]


def ref(document, index=0):
    chunk = document.chunks[index]
    return Evidence(chunk_id=chunk.id, quote=chunk.text)


def audit_owner(document):
    return Unit(
        id=f"{document.side}-audit-unit",
        name="Audit Department",
        side=document.side,
        evidence=[ref(document)],
    )


def supported_review(payload):
    return ai.EvidenceReview(
        verdicts=[
            ai.Verdict(
                finding_id=item["claim"]["id"],
                verdict="supported",
                reason="The cited source explicitly assigns this responsibility.",
                confidence=0.9,
            )
            for item in payload
        ]
    )


def test_unit_names_require_nonblank_verbatim_source_text(monkeypatch):
    document = sources()[0]
    proposed = ai.UnitExtraction(
        units=[
            ai.ExtractedUnit(name=name, evidence=[ref(document)])
            for name in ("999. Audit Department", " ", "Audit Department")
        ]
    )
    monkeypatch.setattr(ai, "ask", lambda *args: proposed)
    warnings = []
    result = pipeline.ai_units([document], warnings)
    assert [unit.name for unit in result] == ["Audit Department"]
    assert warnings


def test_function_descriptions_cannot_be_whitespace_substrings(monkeypatch):
    document = sources()[0]
    owner = audit_owner(document)

    def fake(schema, instruction, payload):
        if schema is ai.FunctionExtraction:
            return ai.FunctionExtraction(
                functions=[
                    ai.ExtractedFunction(
                        unit_id=owner.id,
                        description=description,
                        evidence=[ref(document)],
                    )
                    for description in (" ", document.chunks[0].text)
                ]
            )
        assert schema is ai.EvidenceReview
        return supported_review(payload)

    monkeypatch.setattr(ai, "ask", fake)
    warnings = []
    result = pipeline.ai_functions([document], [owner], warnings)
    assert [function.description for function in result] == [document.chunks[0].text]
    assert warnings


def test_known_owner_id_does_not_validate_other_units_evidence(monkeypatch):
    document = sources()[0]
    owner = audit_owner(document)

    def fake(schema, instruction, payload):
        if schema is ai.FunctionExtraction:
            return ai.FunctionExtraction(
                functions=[
                    ai.ExtractedFunction(
                        unit_id=owner.id,
                        description=document.chunks[1].text,
                        evidence=[ref(document, 1)],
                    )
                ]
            )
        assert schema is ai.EvidenceReview
        return supported_review(payload)

    monkeypatch.setattr(ai, "ask", fake)
    warnings = []
    assert pipeline.ai_functions([document], [owner], warnings) == []
    assert warnings


@pytest.mark.parametrize(
    ("verdict", "confidence"),
    [("unsupported", 0.95), ("uncertain", 0.9), ("supported", 0.69), (None, 0.0)],
)
def test_ownership_reviewer_must_explicitly_support_assignment(
    monkeypatch, verdict, confidence
):
    document = sources()[0]
    owner = audit_owner(document)
    document.chunks[
        1
    ].text = "Treasury Department sends payroll reports to Audit Department."
    function = Function(
        id="proposed-owner",
        unit_id=owner.id,
        description=document.chunks[1].text,
        side="before",
        evidence=[ref(document, 1)],
    )
    calls = []

    def fake(schema, instruction, payload):
        assert schema is ai.EvidenceReview
        calls.append(payload)
        return ai.EvidenceReview(
            verdicts=[]
            if verdict is None
            else [
                ai.Verdict(
                    finding_id=function.id,
                    verdict=verdict,
                    reason="Audit receives the report; Treasury performs the duty.",
                    confidence=confidence,
                )
            ]
        )

    monkeypatch.setattr(ai, "ask", fake)
    warnings = []
    result = pipeline.review_extracted_functions(
        [function], [owner], [document], warnings
    )
    assert calls, "Ownership must actually be independently reviewed"
    assert result == []
    assert warnings


def test_valid_owner_assignment_survives_independent_review(monkeypatch):
    document = sources()[0]
    owner = audit_owner(document)
    function = Function(
        id="supported-owner",
        unit_id=owner.id,
        description=document.chunks[0].text,
        side="before",
        evidence=[ref(document)],
    )

    def fake(schema, instruction, payload):
        assert schema is ai.EvidenceReview
        return supported_review(payload)

    monkeypatch.setattr(ai, "ask", fake)
    result = pipeline.review_extracted_functions([function], [owner], [document], [])
    assert [item.id for item in result] == [function.id]


def mapped_functions(documents):
    return [
        Function(
            id="before-function",
            unit_id="before-audit-unit",
            description=documents[0].chunks[0].text,
            side="before",
            evidence=[ref(documents[0])],
        ),
        Function(
            id="after-function",
            unit_id="after-treasury-unit",
            description=documents[1].chunks[1].text,
            side="after",
            evidence=[ref(documents[1], 1)],
        ),
    ]


def unchanged_mapping(functions, evidence):
    return FunctionMapping(
        id="unsupported-continuity",
        before_ids=[functions[0].id],
        after_ids=[functions[1].id],
        match_type="unchanged",
        confidence=0.99,
        explanation="The responsibility is unchanged.",
        evidence=evidence,
    )


def test_real_quotes_must_belong_to_the_entities_being_mapped():
    documents = sources()
    functions = mapped_functions(documents)
    mapping = unchanged_mapping(functions, [ref(documents[0], 1), ref(documents[1])])
    warnings = []
    result = pipeline.validate_mappings(
        [mapping], functions, documents, "function", warnings
    )
    assert result
    assert all(item.match_type == "uncertain" for item in result)
    assert warnings


def test_unchanged_functions_are_reviewed_with_resolved_entities(monkeypatch):
    documents = sources()
    functions = mapped_functions(documents)
    mapping = unchanged_mapping(functions, [ref(documents[0]), ref(documents[1], 1)])
    units = [
        audit_owner(documents[0]),
        Unit(
            id="after-treasury-unit",
            name="Treasury Department",
            side="after",
            evidence=[ref(documents[1], 1)],
        ),
    ]
    calls = []

    def fake(schema, instruction, payload):
        assert schema is ai.EvidenceReview
        calls.append(payload)
        # Source text is present either way. Check that the referenced entity
        # definitions themselves reach the reviewer, not only opaque IDs.
        serialized = json.dumps(payload, ensure_ascii=False)
        assert '"description"' in serialized
        assert '"unit_id"' in serialized
        assert all(function.description in serialized for function in functions)
        return ai.EvidenceReview(
            verdicts=[
                ai.Verdict(
                    finding_id=mapping.id,
                    verdict="unsupported",
                    reason="Checking controls and approving grants are different duties.",
                    confidence=0.95,
                )
            ]
        )

    monkeypatch.setattr(ai, "ask", fake)
    pipeline.semantic_review(
        [], [], [mapping], documents, [], units=units, functions=functions
    )
    assert calls, "An unchanged label cannot bypass semantic verification"
    assert mapping.match_type == "uncertain"
