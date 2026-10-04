from __future__ import annotations

import base64
import json
import re
from typing import Any

import httpx
from pydantic import ValidationError

from .db import (
    attach_analysis_snapshot,
    get_cached_document_analysis,
    save_cached_document_analysis,
)
from .models import (
    AnalyzeResponse,
    LetterUnderstanding,
    ToolTrace,
)
from .openrouter_client import (
    chat_completion,
)
from .tools import (
    execute_tool,
    tool_definitions,
)


SYSTEM_PROMPT = """
You are Handle It NL, an AI assistant for expats in the Netherlands.

Your job is to explain the uploaded Dutch letter and turn only clearly stated
requirements into useful actions.

GROUNDING RULES — VERY IMPORTANT:
1. Treat the uploaded document as the source of truth.
2. Copy dates, times, amounts, reference numbers and addresses from the document.
   Do not invent or "improve" them.
3. If a detail is unreadable or absent, use null/unclear. Never guess it.
4. Do not invent consequences. Only state them when the letter or an official
   process tool supports them.
5. A place verified by PDOK may normalize spelling, but it must not change the
   appointment stated in the letter.
6. If the same appointment/deadline has already been saved, do not create a
   second logical item.

FIRST answer:
- What is this?
- Can the user ignore it?
- What must they do?
- By when?

CLASSIFICATION:
- payment_required
- appointment_or_visit
- action_required
- information_only
- mixed
- needs_review

TOOLS:
- verify_dutch_address
- prepare_calendar_event
- save_deadline
- lookup_official_process
- get_upcoming_deadlines

SAVE RULES:
- For an appointment, call save_deadline with:
  kind="appointment"
  due_at=the exact appointment start
  location=the exact physical appointment location from the document.
- Do not call save_deadline twice for the same appointment.
- For payment deadlines use kind="payment".
- For reply/response deadlines use kind="response".

PAYMENT SAFETY:
- Never make a payment.
- Never instruct the user to trust an AI-extracted IBAN/QR code.
- Tell the user to verify payment details against the original letter/official portal.

CALENDAR:
- Prepare an event only when an actual appointment/event exists.
- If end time is absent, a one-hour event is allowed only if the notes clearly
  state that the end time was assumed.

FINAL OUTPUT:
After tool use, return ONLY JSON with this shape:

{
  "category": "payment_required|appointment_or_visit|action_required|information_only|mixed|needs_review",
  "priority": "urgent|important|normal|low",
  "sender": "sender or null",
  "subject": "short subject or null",
  "simple_summary": "plain-English summary grounded in the document",
  "why_you_received_it": "reason or null",
  "action_required": "yes|no|unclear",
  "can_ignore": "no|probably_yes|unclear",
  "ignore_explanation": "short reason",
  "action_items": [
    {
      "action": "specific action",
      "deadline": "ISO/date text or null",
      "importance": "critical|important|optional"
    }
  ],
  "payment_amount": "amount or null",
  "payment_reference": "reference or null",
  "primary_deadline": "deadline or null",
  "appointment_time": "date/time or null",
  "appointment_location": "location or null",
  "what_to_bring": ["item"],
  "consequence_if_ignored": "supported consequence or null",
  "dutch_terms": [
    {"term": "Dutch term", "meaning": "simple English meaning"}
  ],
  "confidence": "high|medium|low"
}

No markdown fences.
""".strip()


def _tool_calls(
    message: dict[str, Any],
) -> list[dict[str, Any]]:
    calls = message.get("tool_calls")
    return (
        calls
        if isinstance(calls, list)
        else []
    )


def _tool_args(
    call: dict[str, Any],
) -> tuple[str, dict[str, Any], str]:
    function = call.get("function") or {}

    name = str(
        function.get("name") or ""
    ).strip()

    tool_call_id = str(
        call.get("id") or ""
    ).strip()

    arguments = (
        function.get("arguments")
        or {}
    )

    if isinstance(arguments, str):
        try:
            arguments = json.loads(
                arguments
            )
        except json.JSONDecodeError:
            arguments = {}

    if not isinstance(arguments, dict):
        arguments = {}

    return (
        name,
        arguments,
        tool_call_id,
    )


def _clean_json_text(raw: str) -> str:
    value = raw.strip()

    if value.startswith("```"):
        value = re.sub(
            r"^```(?:json)?\s*",
            "",
            value,
            flags=re.IGNORECASE,
        )
        value = re.sub(
            r"\s*```$",
            "",
            value,
        )

    first = value.find("{")
    last = value.rfind("}")

    if first >= 0 and last > first:
        value = value[first : last + 1]

    return value.strip()


def _try_parse_understanding(
    raw: str,
) -> LetterUnderstanding | None:
    try:
        data = json.loads(
            _clean_json_text(raw)
        )

        return LetterUnderstanding.model_validate(
            data
        )

    except (
        json.JSONDecodeError,
        ValidationError,
        TypeError,
    ):
        return None


def _fallback_understanding() -> LetterUnderstanding:
    return LetterUnderstanding(
        category="needs_review",
        priority="normal",
        sender=None,
        subject=None,
        simple_summary=(
            "The model could not produce a reliable structured "
            "interpretation. Please review the original letter carefully."
        ),
        why_you_received_it=None,
        action_required="unclear",
        can_ignore="unclear",
        ignore_explanation=(
            "The document could not be interpreted reliably enough "
            "to say whether it can be ignored."
        ),
        action_items=[],
        payment_amount=None,
        payment_reference=None,
        primary_deadline=None,
        appointment_time=None,
        appointment_location=None,
        what_to_bring=[],
        consequence_if_ignored=None,
        dutch_terms=[],
        confidence="low",
    )


def _page_data_url(
    page_bytes: bytes,
    media_type: str,
) -> str:
    encoded = base64.b64encode(
        page_bytes
    ).decode("ascii")

    safe_media_type = (
        media_type
        if media_type.startswith("image/")
        else "image/jpeg"
    )

    return (
        f"data:{safe_media_type};base64,"
        f"{encoded}"
    )


def _normalise_identity_text(
    value: str | None,
) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        (value or "").lower(),
    ).strip()


def _calendar_identity(
    action: dict[str, Any],
) -> tuple[str, str]:
    return (
        str(action.get("start") or "").strip(),
        _normalise_identity_text(
            str(action.get("location") or "")
        ),
    )


def _address_identity(
    action: dict[str, Any],
) -> str:
    return _normalise_identity_text(
        str(
            action.get("query")
            or action.get("display_name")
            or ""
        )
    )


async def _repair_final_json(
    client: httpx.AsyncClient,
    messages: list[dict[str, Any]],
) -> LetterUnderstanding | None:
    repair_messages = [
        *messages,
        {
            "role": "user",
            "content": (
                "Your previous final response did not match the required "
                "JSON structure. Do not re-analyze or invent facts. Using "
                "only the document/tool information already in this "
                "conversation, return the final result again as valid JSON "
                "matching the required schema exactly."
            ),
        },
    ]

    schema = LetterUnderstanding.model_json_schema()

    try:
        repaired = await chat_completion(
            client,
            messages=repair_messages,
            tools=None,
            temperature=0.0,
            max_tokens=1800,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "letter_understanding",
                    "strict": True,
                    "schema": schema,
                },
            },
            seed=42,
        )
    except RuntimeError:
        # Some routed providers may not honor json_schema. Fall back to
        # plain JSON mode rather than turning a formatting error into a
        # misleading "No action needed" result.
        try:
            repaired = await chat_completion(
                client,
                messages=repair_messages,
                tools=None,
                temperature=0.0,
                max_tokens=1800,
                response_format={
                    "type": "json_object"
                },
                seed=42,
            )
        except RuntimeError:
            return None

    return _try_parse_understanding(
        str(
            repaired.get("content")
            or ""
        )
    )


def _cached_response(
    cached: dict[str, Any],
) -> AnalyzeResponse | None:
    try:
        response = AnalyzeResponse.model_validate(
            cached
        )
    except ValidationError:
        return None

    # Re-uploading the identical document must not look like it inserted
    # the saved deadline again.
    for saved in response.saved_deadlines:
        saved.is_duplicate = True
        saved.has_details = True

    for trace in response.tool_trace:
        if trace.tool == "save_deadline":
            trace.summary = (
                "Already saved — identical document analysis reused"
            )

    return response


async def analyze_document(
    image_pages: list[bytes],
    media_types: list[str],
    instruction: str,
    source_kind: str = "image",
    total_pages: int = 1,
    processed_pages: int = 1,
    processing_warning: str | None = None,
    document_hash: str | None = None,
) -> AnalyzeResponse:
    # Strongest consistency rule: exact same source file => exact same
    # analysis snapshot. No second LLM interpretation is performed.
    if document_hash:
        cached = get_cached_document_analysis(
            document_hash
        )

        if cached:
            response = _cached_response(
                cached
            )

            if response is not None:
                return response

    content_parts: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "Analyze the attached document pages as one document, "
                "in page order. The document itself is the source of truth. "
                "Use tools only when they add a real capability. "
                "If a date/time/address is unreadable, return unclear/null "
                "instead of guessing.\n\n"
                f"User instruction:\n{instruction.strip()}"
            ),
        }
    ]

    for page_bytes, media_type in zip(
        image_pages,
        media_types,
    ):
        content_parts.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": _page_data_url(
                        page_bytes,
                        media_type,
                    ),
                },
            }
        )

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": content_parts,
        },
    ]

    trace: list[ToolTrace] = []
    calendar_actions: list[dict[str, Any]] = []
    address_actions: list[dict[str, Any]] = []
    saved_deadlines: list[dict[str, Any]] = []
    official_guidance: list[dict[str, Any]] = []

    seen_calendar: set[tuple[str, str]] = set()
    seen_addresses: set[str] = set()
    seen_deadline_ids: set[int] = set()

    structured_ok = False

    async with httpx.AsyncClient(
        timeout=180.0
    ) as client:
        for _ in range(9):
            assistant_message = await chat_completion(
                client,
                messages=messages,
                tools=tool_definitions(),
                temperature=0.0,
                max_tokens=1800,
                seed=42,
            )

            messages.append(
                assistant_message
            )

            calls = _tool_calls(
                assistant_message
            )

            if not calls:
                understanding = (
                    _try_parse_understanding(
                        str(
                            assistant_message.get(
                                "content"
                            )
                            or ""
                        )
                    )
                )

                if understanding is None:
                    understanding = (
                        await _repair_final_json(
                            client,
                            messages,
                        )
                    )

                if understanding is None:
                    understanding = (
                        _fallback_understanding()
                    )
                else:
                    structured_ok = True

                for item in saved_deadlines:
                    item["has_details"] = True

                response = AnalyzeResponse(
                    source_kind=source_kind,
                    total_pages=total_pages,
                    processed_pages=processed_pages,
                    processing_warning=processing_warning,
                    understanding=understanding,
                    tool_trace=trace,
                    calendar_actions=calendar_actions,
                    address_actions=address_actions,
                    saved_deadlines=saved_deadlines,
                    official_guidance=official_guidance,
                )

                deadline_ids = [
                    int(item["id"])
                    for item in saved_deadlines
                    if item.get("id") is not None
                ]

                attach_analysis_snapshot(
                    deadline_ids=deadline_ids,
                    analysis=response.model_dump(
                        mode="json"
                    ),
                )

                # Only cache reliable structured responses. A temporary model
                # formatting failure must not permanently poison this document.
                if (
                    document_hash
                    and structured_ok
                ):
                    save_cached_document_analysis(
                        document_hash=document_hash,
                        analysis=response.model_dump(
                            mode="json"
                        ),
                    )

                return response

            for call in calls:
                (
                    name,
                    args,
                    tool_call_id,
                ) = _tool_args(call)

                if not name:
                    continue

                try:
                    result = await execute_tool(
                        name,
                        args,
                    )

                    trace.append(
                        ToolTrace(
                            tool=name,
                            args=args,
                            status="success",
                            summary=_summarize_tool_result(
                                name,
                                result,
                            ),
                            result=result,
                        )
                    )

                    if name == "prepare_calendar_event":
                        key = _calendar_identity(
                            result
                        )

                        if key not in seen_calendar:
                            seen_calendar.add(key)
                            calendar_actions.append(
                                result
                            )

                    elif (
                        name
                        == "verify_dutch_address"
                        and result.get("verified")
                    ):
                        action = {
                            "query": result.get(
                                "query",
                                "",
                            ),
                            "display_name": result.get(
                                "display_name",
                                result.get(
                                    "query",
                                    "",
                                ),
                            ),
                            "latitude": result.get(
                                "latitude"
                            ),
                            "longitude": result.get(
                                "longitude"
                            ),
                            "map_url": result.get(
                                "map_url"
                            ),
                        }

                        key = _address_identity(
                            action
                        )

                        if key not in seen_addresses:
                            seen_addresses.add(key)
                            address_actions.append(
                                action
                            )

                    elif name == "save_deadline":
                        deadline_id = result.get(
                            "id"
                        )

                        if (
                            deadline_id is not None
                            and int(deadline_id)
                            not in seen_deadline_ids
                        ):
                            seen_deadline_ids.add(
                                int(deadline_id)
                            )
                            saved_deadlines.append(
                                result
                            )

                    elif (
                        name
                        == "lookup_official_process"
                        and result.get("found")
                    ):
                        if not any(
                            existing.get(
                                "official_url"
                            )
                            == result.get(
                                "official_url"
                            )
                            for existing
                            in official_guidance
                        ):
                            official_guidance.append(
                                {
                                    "organization": result.get(
                                        "organization",
                                        "",
                                    ),
                                    "topic": result.get(
                                        "topic",
                                        "",
                                    ),
                                    "summary": result.get(
                                        "summary",
                                        "",
                                    ),
                                    "official_url": result.get(
                                        "official_url",
                                        "",
                                    ),
                                    "cautions": result.get(
                                        "cautions"
                                    )
                                    or [],
                                }
                            )

                    tool_message: dict[str, Any] = {
                        "role": "tool",
                        "content": json.dumps(
                            result,
                            ensure_ascii=False,
                            default=str,
                        ),
                    }

                    if tool_call_id:
                        tool_message[
                            "tool_call_id"
                        ] = tool_call_id
                    else:
                        tool_message[
                            "name"
                        ] = name

                    messages.append(
                        tool_message
                    )

                except Exception as exc:
                    error_result = {
                        "error": str(exc),
                        "instruction": (
                            "Do not invent the missing result. "
                            "Explain the limitation."
                        ),
                    }

                    trace.append(
                        ToolTrace(
                            tool=name,
                            args=args,
                            status="error",
                            summary=str(exc),
                            result=error_result,
                        )
                    )

                    tool_message = {
                        "role": "tool",
                        "content": json.dumps(
                            error_result,
                            ensure_ascii=False,
                        ),
                    }

                    if tool_call_id:
                        tool_message[
                            "tool_call_id"
                        ] = tool_call_id
                    else:
                        tool_message[
                            "name"
                        ] = name

                    messages.append(
                        tool_message
                    )

    raise RuntimeError(
        "Agent reached the maximum number "
        "of tool iterations."
    )


def _summarize_tool_result(
    name: str,
    result: dict[str, Any],
) -> str:
    if name == "verify_dutch_address":
        if result.get("verified"):
            return (
                "PDOK verified: "
                f"{result.get('display_name', result.get('query', 'address'))}"
            )

        return (
            "PDOK found no matching Dutch address."
        )

    if name == "prepare_calendar_event":
        return (
            "Prepared calendar event: "
            f"{result.get('title', 'event')}"
        )

    if name == "save_deadline":
        if result.get("is_duplicate"):
            return (
                "Already saved: "
                f"{result.get('title', 'deadline')}"
            )

        return (
            "Saved local deadline: "
            f"{result.get('title', 'deadline')}"
        )

    if name == "lookup_official_process":
        if result.get("found"):
            return (
                "Loaded official-process guidance: "
                f"{result.get('topic', 'process')}"
            )

        return (
            "No curated official-process "
            "guide was available."
        )

    if name == "get_upcoming_deadlines":
        return (
            f"Loaded "
            f"{len(result.get('deadlines') or [])} "
            "saved deadline(s)."
        )

    return "Tool completed."
