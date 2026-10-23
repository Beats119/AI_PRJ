"""AssignmentSpec: the structured assignment contract built during setup."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AssignmentExample(BaseModel):
    """An authoritative example stated by the instructor / assignment source."""

    input_data: str
    expected_output: str
    provenance: str  # where this example came from (document + location)


class AssignmentSpec(BaseModel):
    assignment_id: str
    specification_hash: str = ""  # filled after canonical hashing
    purpose: str = ""
    input_contract: str = ""
    output_contract: str = ""
    constraints: list[str] = Field(default_factory=list)
    expected_behavior: list[str] = Field(default_factory=list)
    boundary_conditions: list[str] = Field(default_factory=list)
    invalid_input_behavior: str | None = None  # None = spec is silent
    examples: list[AssignmentExample] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    provenance: list[str] = Field(default_factory=list)
