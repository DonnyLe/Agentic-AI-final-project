"""A case: one meeting excerpt plus the action Kangaroo is about to take.

Only `id` and `content` exist here. Corpus metadata (seeded labels, generation
notes, ambiguity and injection flags) has no field to land in, so it can't
reach a prompt.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue

type Tier = Literal["T1", "T2", "T3", "T4"]

SUPPORTED_TIERS: frozenset[str] = frozenset({"T1", "T2"})


class Segment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    segment_id: str
    speaker_id: str
    speaker: str
    text: str


class CaseContent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    meeting_id: str
    meeting_type: str
    # Some cases leave these unknown on purpose (deadline conversion, R1.3).
    meeting_date: date | None
    meeting_weekday: str | None
    meeting_timezone: str | None
    segments: list[Segment]
    candidate_action: str
    evidence: dict[str, JsonValue]


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    content: CaseContent
