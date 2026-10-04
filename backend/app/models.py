from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolTrace(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    status: Literal["success", "error"]
    summary: str
    result: Any | None = None


class CalendarAction(BaseModel):
    event_id: str
    title: str
    start: str
    end: str
    location: str | None = None
    notes: str | None = None
    ics_url: str
    google_calendar_url: str


class AddressAction(BaseModel):
    query: str
    display_name: str
    latitude: float | None = None
    longitude: float | None = None
    map_url: str | None = None


class DeadlineAction(BaseModel):
    id: int
    title: str
    due_at: str
    source: str | None = None
    notes: str | None = None

    # True only in the response from save_deadline when that same deadline
    # already existed. List/detail responses normally return False.
    is_duplicate: bool = False

    # Lets the UI know whether clicking the saved item can reconstruct
    # the full original analysis view.
    has_details: bool = False


class OfficialGuidance(BaseModel):
    organization: str
    topic: str
    summary: str
    official_url: str
    cautions: list[str] = Field(default_factory=list)


class ActionItem(BaseModel):
    action: str
    deadline: str | None = None
    importance: Literal["critical", "important", "optional"] = "important"


class DutchTerm(BaseModel):
    term: str
    meaning: str


class LetterUnderstanding(BaseModel):
    category: Literal[
        "payment_required",
        "appointment_or_visit",
        "action_required",
        "information_only",
        "mixed",
        "needs_review",
    ]
    priority: Literal["urgent", "important", "normal", "low"]
    sender: str | None = None
    subject: str | None = None
    simple_summary: str
    why_you_received_it: str | None = None
    action_required: Literal["yes", "no", "unclear"]
    can_ignore: Literal["no", "probably_yes", "unclear"]
    ignore_explanation: str
    action_items: list[ActionItem] = Field(default_factory=list)
    payment_amount: str | None = None
    payment_reference: str | None = None
    primary_deadline: str | None = None
    appointment_time: str | None = None
    appointment_location: str | None = None
    what_to_bring: list[str] = Field(default_factory=list)
    consequence_if_ignored: str | None = None
    dutch_terms: list[DutchTerm] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]


class AnalyzeResponse(BaseModel):
    source_kind: Literal["image", "pdf"] = "image"
    total_pages: int = 1
    processed_pages: int = 1
    processing_warning: str | None = None
    understanding: LetterUnderstanding
    tool_trace: list[ToolTrace] = Field(default_factory=list)
    calendar_actions: list[CalendarAction] = Field(default_factory=list)
    address_actions: list[AddressAction] = Field(default_factory=list)
    saved_deadlines: list[DeadlineAction] = Field(default_factory=list)
    official_guidance: list[OfficialGuidance] = Field(default_factory=list)


class DeadlineListResponse(BaseModel):
    deadlines: list[DeadlineAction]
