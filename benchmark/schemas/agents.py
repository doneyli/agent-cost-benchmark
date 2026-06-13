"""Structured output schemas for agent responses."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Scout
# ---------------------------------------------------------------------------

class BugFinding(BaseModel):
    file: str = Field(description="File path relative to target_project/")
    line: int = Field(description="Line number where the bug is located")
    description: str = Field(description="What the bug is and why it's a problem")
    severity: str = Field(description="critical / high / medium / low")
    category: str = Field(
        description=(
            "security / logic / data-integrity / performance / "
            "error-handling / concurrency / business-logic / edge-case"
        )
    )


class ScoutOutput(BaseModel):
    findings: list[BugFinding]
    summary: str = Field(description="Brief summary of overall code quality")


# ---------------------------------------------------------------------------
# Triage
# ---------------------------------------------------------------------------

class FixPlanItem(BaseModel):
    bug_description: str
    priority: int = Field(description="1 = fix first, 8 = fix last")
    rationale: str = Field(description="Why this priority")
    dependencies: list[str] = Field(
        default_factory=list,
        description="Other fixes this depends on",
    )


class TriageOutput(BaseModel):
    plan: list[FixPlanItem]
    strategy: str = Field(description="Overall fix strategy")


# ---------------------------------------------------------------------------
# Fixer
# ---------------------------------------------------------------------------

class FixedFile(BaseModel):
    path: str = Field(description="File path relative to target_project/")
    content: str = Field(description="Complete fixed file content")
    changes_made: list[str] = Field(description="List of changes made to this file")


class FixerOutput(BaseModel):
    fixed_files: list[FixedFile]
    bugs_addressed: list[str] = Field(description="Bug descriptions that were fixed")


# ---------------------------------------------------------------------------
# Reviewer
# ---------------------------------------------------------------------------

class ReviewFinding(BaseModel):
    file: str
    line: int
    issue: str
    severity: str
    suggestion: str


class ReviewerOutput(BaseModel):
    findings: list[ReviewFinding]
    overall_quality: int = Field(ge=1, le=5, description="1-5 overall quality rating")
    summary: str
    remaining_concerns: list[str]
