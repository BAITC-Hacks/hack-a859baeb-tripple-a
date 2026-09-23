"""Validated normalized documents and evidence-backed analysis contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Side = Literal["before", "after"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Chunk(StrictModel):
    id: str
    document_id: str
    text: str
    page: int | None = None
    section: str | None = None
    paragraph: int | None = None
    sheet: str | None = None
    row: int | None = None


class Document(StrictModel):
    id: str
    filename: str
    document_type: Literal["pdf", "docx", "xlsx"]
    side: Side
    chunks: list[Chunk]
    warnings: list[str] = Field(default_factory=list)


class Evidence(StrictModel):
    chunk_id: str
    quote: str = Field(min_length=1)


class Unit(StrictModel):
    id: str
    name: str = Field(min_length=1, max_length=250)
    side: Side
    evidence: list[Evidence] = Field(min_length=1)


class Function(StrictModel):
    id: str
    unit_id: str
    description: str = Field(min_length=1)
    side: Side
    evidence: list[Evidence] = Field(min_length=1)


class UnitMapping(StrictModel):
    id: str
    before_ids: list[str]
    after_ids: list[str]
    status: Literal[
        "unchanged", "renamed", "reorganized", "removed", "created", "uncertain"
    ]
    confidence: float = Field(ge=0, le=1)
    explanation: str
    evidence: list[Evidence] = Field(min_length=1)


class FunctionMapping(StrictModel):
    id: str
    before_ids: list[str]
    after_ids: list[str]
    match_type: Literal[
        "unchanged",
        "equivalent",
        "modified",
        "transferred",
        "potential_loss",
        "new",
        "uncertain",
    ]
    confidence: float = Field(ge=0, le=1)
    explanation: str
    evidence: list[Evidence] = Field(min_length=1)


class Finding(StrictModel):
    id: str
    category: Literal["loss", "duplication", "overlap", "conflict", "uncertain"]
    title: str
    explanation: str
    severity: Literal["high", "medium", "low"]
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence] = Field(min_length=1)
    recommendation: str
    requires_review: bool = True


class AnalysisResult(StrictModel):
    units: list[Unit]
    functions: list[Function]
    unit_mappings: list[UnitMapping]
    function_mappings: list[FunctionMapping]
    findings: list[Finding]
    warnings: list[str]
    summary: dict[str, int]
    report: str
