from __future__ import annotations

import hashlib

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.middleware.cors import (
    CORSMiddleware,
)
from fastapi.responses import (
    FileResponse,
)

from .agent import analyze_document
from .calendar_utils import CALENDAR_DIR
from .db import (
    delete_deadline,
    get_deadline_analysis,
    init_db,
    list_deadlines,
)
from .document_utils import prepare_document
from .models import (
    AnalyzeResponse,
    DeadlineListResponse,
)
from .openrouter_client import (
    OPENROUTER_MODEL,
    api_key_configured,
)


app = FastAPI(
    title="Handle It NL API",
    version="1.4.0",
    description=(
        "Multimodal Dutch-letter assistant for expats, "
        "powered by OpenRouter and local Python tools."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200"
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()

    CALENDAR_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "provider": "openrouter",
        "model": OPENROUTER_MODEL,
        "api_key_configured": (
            api_key_configured()
        ),
    }


@app.post(
    "/api/analyze",
    response_model=AnalyzeResponse,
)
async def analyze(
    file: UploadFile = File(...),
    instruction: str = Form(
        "Explain this Dutch letter to me as an "
        "expat and tell me what I need to do."
    ),
) -> AnalyzeResponse:
    content_type = (
        file.content_type or ""
    ).lower()

    filename = file.filename or ""

    is_image = content_type.startswith(
        "image/"
    )

    is_pdf = (
        content_type == "application/pdf"
        or filename.lower().endswith(
            ".pdf"
        )
    )

    if not (is_image or is_pdf):
        raise HTTPException(
            status_code=400,
            detail=(
                "Please upload an image or PDF."
            ),
        )

    file_bytes = await file.read()

    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail=(
                "The uploaded file is empty."
            ),
        )

    max_bytes = (
        20 * 1024 * 1024
        if is_pdf
        else 12 * 1024 * 1024
    )

    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                "PDF is too large. Keep it under 20 MB."
                if is_pdf
                else (
                    "Image is too large. "
                    "Keep it under 12 MB."
                )
            ),
        )

    # Exact same source bytes => same hash => same cached analysis.
    document_hash = hashlib.sha256(
        file_bytes
    ).hexdigest()

    try:
        prepared = prepare_document(
            file_bytes,
            content_type,
            filename,
        )

        return await analyze_document(
            image_pages=prepared.images,
            media_types=prepared.media_types,
            instruction=instruction,
            source_kind=prepared.source_kind,
            total_pages=prepared.total_pages,
            processed_pages=prepared.processed_pages,
            processing_warning=prepared.warning,
            document_hash=document_hash,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Analysis failed: {exc}. "
                "Check OPENROUTER_API_KEY, "
                "internet connectivity and the "
                "configured model."
            ),
        ) from exc


@app.get(
    "/api/deadlines",
    response_model=DeadlineListResponse,
)
def deadlines() -> DeadlineListResponse:
    return DeadlineListResponse(
        deadlines=list_deadlines(30)
    )


@app.get(
    "/api/deadlines/{deadline_id}/analysis",
    response_model=AnalyzeResponse,
)
def deadline_analysis(
    deadline_id: int,
) -> AnalyzeResponse:
    analysis = get_deadline_analysis(
        deadline_id
    )

    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Detailed analysis is not available "
                "for this older saved item. Re-analyze "
                "the original letter once."
            ),
        )

    try:
        return AnalyzeResponse.model_validate(
            analysis
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "The stored deadline analysis "
                "could not be read."
            ),
        ) from exc


@app.delete(
    "/api/deadlines/{deadline_id}"
)
def remove_deadline(
    deadline_id: int,
) -> dict[str, object]:
    deleted = delete_deadline(
        deadline_id
    )

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Saved deadline was not found.",
        )

    return {
        "deleted": True,
        "deadline_id": deadline_id,
    }


@app.get(
    "/api/calendar/{event_id}.ics"
)
def calendar_file(
    event_id: str,
) -> FileResponse:
    safe = "".join(
        character
        for character in event_id
        if character.isalnum()
    )

    if safe != event_id:
        raise HTTPException(
            status_code=400,
            detail="Invalid event id.",
        )

    path = (
        CALENDAR_DIR
        / f"{safe}.ics"
    )

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Calendar event not found."
            ),
        )

    return FileResponse(
        path=path,
        media_type=(
            "text/calendar; charset=utf-8"
        ),
        filename="handle-it-event.ics",
    )
