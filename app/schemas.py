from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class ProjectInput(Strict):
    name: str = Field(min_length=1, max_length=200)

class RunInput(Strict):
    mode: Literal['demo', 'ollama'] = 'demo'

class Evidence(Strict):
    fragment_id: str
    quote: str = Field(min_length=1)

class Unit(Strict):
    id: str
    name: str
    phase: Literal['before', 'after']
    evidence: list[Evidence] = Field(min_length=1)

class Function(Strict):
    id: str
    unit_id: str
    text: str
    evidence: list[Evidence] = Field(min_length=1)

class Change(Strict):
    before_ids: list[str]
    after_ids: list[str]
    status: Literal['preserved', 'reorganized', 'created', 'removed', 'uncertain']
    explanation: str
    evidence: list[Evidence] = Field(min_length=1)

class Match(Strict):
    before_id: str
    after_ids: list[str]
    status: Literal['matched', 'partial', 'not_found']
    explanation: str

class Finding(Strict):
    kind: Literal['potential_loss', 'potential_duplication', 'potential_conflict']
    function_ids: list[str] = Field(min_length=1)
    explanation: str
    recommendation: str

class Report(Strict):
    units: list[Unit]
    functions: list[Function]
    changes: list[Change]
    matches: list[Match]
    findings: list[Finding]
