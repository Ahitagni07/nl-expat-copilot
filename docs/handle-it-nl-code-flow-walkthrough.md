# Handle It NL — Complete Code Flow Walkthrough

The easiest way to understand Handle It NL is as this chain:

```text
app.component.html
        ↓ click
app.component.ts
        ↓
api.service.ts
        ↓ HTTP
FastAPI main.py
        ↓
agent.py
        ↓
OpenRouter model
        ↓ asks for tools
tools.py
        ↓
PDOK / SQLite / Calendar / Process Guide
        ↓ tool result
agent.py
        ↓ OpenRouter again
        ↓ final JSON
main.py
        ↓ HTTP response
api.service.ts
        ↓
app.component.ts
        ↓
app.component.html renders result
```

## 1. What happens when the application first opens?

The root Angular component is:

```text
frontend/src/app/app.component.ts
```

Angular calls:

```ts
ngOnInit()
```

Your method is:

```ts
ngOnInit(): void {
  this.checkBackend();
  this.loadDeadlines();
}
```

So **two requests happen immediately**.

### Backend status

```text
ngOnInit()
 ↓
checkBackend()
 ↓
ApiService.health()
 ↓
GET /api/health
```

Frontend files:

```text
app.component.ts
    checkBackend()

api.service.ts
    health()
```

`api.service.ts` contains:

```ts
health(): Observable<HealthResponse> {
  return this.http.get<HealthResponse>(
    '/api/health'
  );
}
```

In production the browser requests:

```text
https://nl-expat-copilot-1.onrender.com/api/health
```

Your Render rewrite forwards that to the FastAPI service.

FastAPI receives it in:

```text
backend/app/main.py
```

Method:

```py
@app.get("/api/health")
def health():
```

It returns:

```json
{
  "status": "ok",
  "provider": "openrouter",
  "model": "...",
  "api_key_configured": true
}
```

Back in `checkBackend()`:

```ts
this.model.set(health.model);
this.backendState.set("ready");
```

That is why the top-right UI changes:

```text
Connecting
   ↓
Ready
```

If this request fails:

```ts
error: () => this.backendState.set("offline")
```

and you see:

```text
Offline
```

---

## 2. At the same time, saved deadlines load

The second call from `ngOnInit()` is:

```ts
this.loadDeadlines();
```

Flow:

```text
app.component.ts
loadDeadlines()
 ↓
api.service.ts
deadlines()
 ↓
GET /api/deadlines
 ↓
main.py
deadlines()
 ↓
db.py
list_deadlines(30)
 ↓
SQLite
```

`ApiService`:

```ts
deadlines(): Observable<DeadlineListResponse> {
  return this.http.get<DeadlineListResponse>(
    '/api/deadlines'
  );
}
```

FastAPI:

```py
@app.get("/api/deadlines")
def deadlines():
    return DeadlineListResponse(
        deadlines=list_deadlines(30)
    )
```

Database:

```text
backend/app/db.py
```

Method:

```py
list_deadlines()
```

runs approximately:

```sql
SELECT ...
FROM deadlines
ORDER BY datetime(due_at)
LIMIT 30
```

Angular receives it:

```ts
this.deadlines.set(response.deadlines);
```

Then `app.component.html` automatically renders:

```html
@for (deadline of visibleDeadlines(); ...)
```

So there is no separate `renderDeadline()` call. Angular Signals cause the template to refresh.

---

## 3. Selecting a file

The upload UI is:

```text
frontend/src/app/app.component.html
```

| UI action | HTML binding | TypeScript method |
|---|---|---|
| Click browse/select file | `(change)="onFileInput($event)"` | `onFileInput()` |
| Drag file into box | `(drop)="onDrop($event)"` | `onDrop()` |
| Replace file | `(click)="clearFile()"` | `clearFile()` |
| Explain & handle this | `(click)="analyze()"` | `analyze()` |
| Retry backend | `(click)="checkBackend()"` | `checkBackend()` |
| Saved deadline card | `(click)="openDeadline(deadline)"` | `openDeadline()` |
| × on saved item | `(click)="requestDeleteDeadline(...)"` | `requestDeleteDeadline()` |
| Keep it | `(click)="cancelDeleteDeadline()"` | `cancelDeleteDeadline()` |
| Remove | `(click)="confirmDeleteDeadline()"` | `confirmDeleteDeadline()` |

When you select a file:

```text
onFileInput()
 ↓
setFile(selected)
```

or:

```text
onDrop()
 ↓
setFile(selected)
```

`setFile()` performs frontend validation.

For a PDF:

```text
max 20 MB
```

For an image:

```text
max 12 MB
```

It verifies:

```ts
image/*
application/pdf
```

For an image it creates the preview:

```ts
URL.createObjectURL(selected)
```

and stores the file:

```ts
this.file.set(selected);
```

---

## 4. Why is the Explain button sometimes disabled?

The button is:

```html
<button
  [disabled]="!canAnalyze()"
  (click)="analyze()">
```

`canAnalyze` is:

```ts
readonly canAnalyze = computed(
  () =>
    this.file() !== null &&
    !this.running() &&
    this.backendState() === "ready"
);
```

So all three must be true:

```text
file selected
+
not currently analyzing
+
backend Ready
```

---

## 5. Clicking "Explain & handle this"

HTML:

```html
(click)="analyze()"
```

calls:

```text
frontend/src/app/app.component.ts
analyze()
```

It starts with:

```ts
const selected = this.file();
```

and updates UI state:

```ts
this.running.set(true);
this.result.set(null);
this.error.set("");
```

Then:

```ts
this.api.analyze(
    selected,
    this.analysisInstruction
)
```

The instruction is:

```ts
"Explain this Dutch letter to me as an expat. " +
"Tell me what it is, whether I can ignore it, " +
"exactly what I need to do and by when..."
```

The browser sends:

```text
file
instruction
```

---

## 6. `ApiService` creates the HTTP request

File:

```text
frontend/src/app/api.service.ts
```

Method:

```ts
analyze(file, instruction)
```

It builds:

```ts
const data = new FormData();

data.append('file', file);
data.append('instruction', instruction);
```

then:

```text
POST /api/analyze
```

Conceptually:

```text
Angular

FormData
├── file = gemeente-letter.pdf
└── instruction = "Explain this Dutch letter..."
            ↓
POST /api/analyze
```

---

## 7. FastAPI receives the document

File:

```text
backend/app/main.py
```

Endpoint:

```py
@app.post("/api/analyze")
async def analyze(...)
```

FastAPI validates:

```text
image or PDF
file not empty
size limit
```

Then:

```py
file_bytes = await file.read()
```

The backend repeats validation because frontend validation is only for UX; **backend validation is the real boundary**.

---

## 8. SHA-256 consistency check starts here

Next:

```py
document_hash = hashlib.sha256(
    file_bytes
).hexdigest()
```

Example:

```text
gemeente.pdf
      ↓
bytes
      ↓
SHA-256
      ↓
a6c35....
```

The hash identifies that exact uploaded file.

It is passed to:

```py
analyze_document(
    ...
    document_hash=document_hash
)
```

This is how the app avoids:

> same PDF → different AI interpretation

---

## 9. Image/PDF conversion

Before AI:

```py
prepared = prepare_document(...)
```

File:

```text
backend/app/document_utils.py
```

Method:

```py
prepare_document()
```

For an image:

```text
original image bytes
 ↓
send as image
```

For a PDF:

```text
PDF
 ↓
PyMuPDF
 ↓
page 1 → JPEG
page 2 → JPEG
...
maximum 5 pages
```

Settings:

```py
MAX_PDF_PAGES = 5
PDF_DPI = 140
JPEG_QUALITY = 84
```

Then `main.py` calls:

```py
await analyze_document(...)
```

---

## 10. `agent.py` is the brain/orchestrator

Main backend orchestration file:

```text
backend/app/agent.py
```

Method:

```py
async def analyze_document(...)
```

First it checks the document cache:

```py
cached = get_cached_document_analysis(
    document_hash
)
```

That database method is in:

```text
backend/app/db.py
```

If the exact file was already analyzed:

```text
SHA found
 ↓
_cached_response()
 ↓
return previous AnalyzeResponse
```

So:

```text
Same exact document
      ↓
cache hit
      ↓
no OpenRouter call
      ↓
same result
```

---

## 11. If it isn't cached, the AI prompt is created

`agent.py` builds:

```py
messages = [
    {
        "role": "system",
        "content": SYSTEM_PROMPT
    },
    {
        "role": "user",
        "content": content_parts
    }
]
```

The `SYSTEM_PROMPT` tells the model:

```text
Treat document as source of truth.
Don't invent dates.
Don't invent addresses.
Don't invent consequences.
Never make payments.
Only create calendar events for real appointments.
```

It also defines the final output shape:

```json
{
  "category": "...",
  "priority": "...",
  "sender": "...",
  "simple_summary": "...",
  "action_required": "...",
  "can_ignore": "...",
  "action_items": [],
  "payment_amount": "...",
  "primary_deadline": "...",
  "appointment_time": "...",
  "appointment_location": "...",
  "what_to_bring": [],
  "dutch_terms": [],
  "confidence": "..."
}
```

---

## 12. Tool definitions are given to the AI

`agent.py` calls:

```py
chat_completion(
    client,
    messages=messages,
    tools=tool_definitions(),
    temperature=0.0,
    seed=42
)
```

`tool_definitions()` comes from:

```text
backend/app/tools.py
```

Tools exposed to the model:

```text
verify_dutch_address()
prepare_calendar_event()
save_deadline()
lookup_official_process()
get_upcoming_deadlines()
```

Important:

**These definitions do not execute anything.**

They tell the model:

```text
"You may request these functions,
and these are their accepted arguments."
```

Example schema:

```json
{
  "name": "verify_dutch_address",
  "parameters": {
    "address": "string"
  }
}
```

---

## 13. `openrouter_client.py` calls OpenRouter

File:

```text
backend/app/openrouter_client.py
```

Method:

```py
chat_completion()
```

It builds:

```py
payload = {
    "model": OPENROUTER_MODEL,
    "messages": messages,
    "temperature": 0.0,
    "max_tokens": 1800,
    "seed": 42
}
```

If tools exist:

```py
payload["tools"] = tools
payload["tool_choice"] = "auto"
```

Then:

```text
POST
https://openrouter.ai/api/v1/chat/completions
```

with:

```text
Authorization: Bearer OPENROUTER_API_KEY
```

The configured model is:

```text
deepseek/deepseek-v4.1-flash
```

---

## 14. Tool calling starts

Suppose the letter says:

```text
Appointment
12 October 2026, 10:20
Stadsplein 1
3431 LZ Nieuwegein
```

The model can respond with a tool request:

```text
verify_dutch_address()
```

`agent.py` detects this via:

```py
calls = _tool_calls(
    assistant_message
)
```

Then extracts:

```py
name
args
tool_call_id
```

using:

```py
_tool_args(call)
```

Example:

```text
name:
verify_dutch_address

args:
{
  "address":
  "Stadsplein 1, 3431 LZ Nieuwegein"
}
```

---

## 15. The model does NOT execute the tool

The real execution happens here:

```py
result = await execute_tool(
    name,
    args
)
```

File:

```text
backend/app/tools.py
```

Method:

```py
execute_tool()
```

It routes:

```text
name == verify_dutch_address
          ↓
verify_dutch_address()

name == prepare_calendar_event
          ↓
create_calendar_artifact()

name == save_deadline
          ↓
add_deadline()

name == lookup_official_process
          ↓
lookup_process()

name == get_upcoming_deadlines
          ↓
list_deadlines()
```

This is the real **agent architecture**.

---

## 16. Example: PDOK tool

The model requests:

```text
verify_dutch_address(...)
```

`execute_tool()` calls:

```py
verify_dutch_address(address)
```

in:

```text
backend/app/tools.py
```

That makes a real HTTP call to:

```text
PDOK Location API
```

Python can receive:

```json
{
  "verified": true,
  "display_name": "...",
  "latitude": 52.0,
  "longitude": 5.0,
  "map_url": "..."
}
```

Difference:

```text
AI says address exists
```

versus:

```text
PDOK actually verified address
```

---

## 17. Tool result goes BACK to the model

After execution, `agent.py` creates:

```py
tool_message = {
    "role": "tool",
    "content": json.dumps(result)
}
```

and:

```py
tool_message["tool_call_id"] = tool_call_id
```

Then:

```py
messages.append(tool_message)
```

Conversation now looks like:

```text
SYSTEM
 ↓
USER + letter images
 ↓
ASSISTANT:
"Call verify_dutch_address"
 ↓
TOOL:
"PDOK says verified=true..."
 ↓
ASSISTANT sees result
```

The loop then calls OpenRouter again:

```py
for _ in range(9):
```

Maximum:

```text
9 agent iterations
```

---

## 18. The model can request another tool

After PDOK, the model may request:

```text
prepare_calendar_event()
```

`execute_tool()` routes it to:

```text
backend/app/calendar_utils.py
```

Method:

```py
create_calendar_artifact()
```

This creates:

```py
event_id = uuid4().hex
```

and writes:

```text
backend/data/calendar/<event_id>.ics
```

It returns:

```json
{
  "event_id": "...",
  "title": "...",
  "start": "...",
  "end": "...",
  "ics_url": "/api/calendar/...ics",
  "google_calendar_url": "https://calendar.google.com/..."
}
```

It does **not** silently add anything to the user's calendar.

---

## 19. Saving an appointment

The model may request:

```text
save_deadline()
```

Example:

```json
{
  "title": "Burgerzaken appointment",
  "due_at": "2026-10-12T10:20:00+02:00",
  "source": "Gemeente Nieuwegein",
  "kind": "appointment",
  "location": "Stadsplein 1, Nieuwegein"
}
```

Flow:

```text
tools.py
execute_tool()
 ↓
db.py
add_deadline()
 ↓
SQLite
```

---

## 20. Appointment duplicate detection

Before insert:

```py
_fingerprint()
```

For an appointment the fingerprint uses:

```text
appointment
+
due date/time
+
normalized location
```

Conceptually:

```text
appointment
|2026-10-12T10:20
|stadsplein1-3431lz
      ↓
SHA-256
```

Therefore different AI-generated titles can still map to the same appointment if:

```text
time same
+
location same
```

If it already exists:

```py
is_duplicate=True
```

and no second database row is inserted.

---

## 21. Tool calls become Agent Trace

Every successful tool execution adds:

```py
trace.append(
    ToolTrace(
        tool=name,
        args=args,
        status="success",
        summary=...,
        result=result
    )
)
```

This becomes:

```text
result.tool_trace
```

Angular renders it in:

```text
app.component.html
AGENT TRACE
```

using:

```html
@for (trace of result()!.tool_trace ...)
```

Example:

```text
✓ verify_dutch_address()
  Address verified through PDOK

✓ prepare_calendar_event()
  Calendar event prepared

✓ save_deadline()
  Deadline saved
```

So Agent Trace is based on **actual backend tool executions**.

---

## 22. Eventually the model stops requesting tools

When:

```py
calls = _tool_calls(...)
```

returns nothing, the model has produced the final answer.

`agent.py` tries:

```py
_try_parse_understanding(...)
```

If parsing fails:

```text
_try_parse_understanding()
        ↓ failed
_repair_final_json()
```

If that also fails:

```py
_fallback_understanding()
```

returns a safe:

```text
needs_review
```

response rather than incorrectly showing:

```text
No action needed
```

---

## 23. Final `AnalyzeResponse` is built

`agent.py` creates:

```py
response = AnalyzeResponse(
    understanding=understanding,
    tool_trace=trace,
    calendar_actions=calendar_actions,
    address_actions=address_actions,
    saved_deadlines=saved_deadlines,
    official_guidance=official_guidance,
    ...
)
```

`AnalyzeResponse` is defined in:

```text
backend/app/models.py
```

It combines:

```text
AI interpretation
+
real actions performed
```

Structure:

```text
AnalyzeResponse
├── understanding
├── tool_trace
├── calendar_actions
├── address_actions
├── saved_deadlines
└── official_guidance
```

---

## 24. Full analysis is attached to saved deadlines

If a deadline was saved:

```py
attach_analysis_snapshot(...)
```

in:

```text
backend/app/db.py
```

stores the analysis JSON with the deadline.

That is why clicking an old Saved Deadline can reopen:

```text
What is this?
Can I ignore?
Actions
Appointment
Address
Agent Trace
etc.
```

without re-running the AI.

---

## 25. Successful analysis is cached against the document hash

If structured output is valid:

```py
save_cached_document_analysis(
    document_hash,
    response
)
```

writes to:

```text
document_analyses
```

Next upload:

```text
same PDF
 ↓
same SHA-256
 ↓
get_cached_document_analysis()
 ↓
return previous response
 ↓
NO OpenRouter call
```

---

## 26. Response goes back to Angular

Flow:

```text
agent.py
 ↓ AnalyzeResponse
main.py
 ↓ HTTP JSON
api.service.ts
 ↓ Observable<AnalyzeResponse>
app.component.ts
```

In `analyze()`:

```ts
next: (response) => {
    this.result.set(response);
    this.loadDeadlines();
    this.scrollToAnalysis();
}
```

Three things happen:

```ts
this.result.set(response);
```

renders the analysis.

```ts
this.loadDeadlines();
```

reloads saved deadlines so a new appointment appears immediately.

```ts
this.scrollToAnalysis();
```

scrolls to:

```text
#analysis-result
```

---

## 27. Clicking "Download .ics"

There is **no Angular click method**.

HTML:

```html
<a [href]="absoluteApiUrl(event.ics_url)">
    Download .ics
</a>
```

`absoluteApiUrl()` returns:

```ts
return path;
```

Example request:

```text
/api/calendar/abc123.ics
```

Backend:

```text
main.py
```

method:

```py
calendar_file(event_id)
```

endpoint:

```text
GET /api/calendar/{event_id}.ics
```

FastAPI returns:

```text
backend/data/calendar/abc123.ics
```

using:

```py
FileResponse(...)
```

---

## 28. Clicking "Google Calendar"

HTML:

```html
<a
  [href]="event.google_calendar_url"
  target="_blank">
    Google Calendar
</a>
```

The URL was generated by:

```text
calendar_utils.py
create_calendar_artifact()
```

Flow:

```text
Angular
 ↓
calendar.google.com
```

No new backend or AI call happens.

---

## 29. Clicking "Open map"

PDOK created:

```text
address.map_url
```

HTML:

```html
<a [href]="address.map_url"
   target="_blank">
    Open map
</a>
```

This opens OpenStreetMap directly.

No new FastAPI or AI request occurs.

---

## 30. Clicking a Saved Deadline

HTML:

```html
(click)="openDeadline(deadline)"
```

Flow:

```text
openDeadline(deadline)
 ↓
ApiService.deadlineAnalysis(deadline.id)
 ↓
GET /api/deadlines/{id}/analysis
 ↓
main.py deadline_analysis()
 ↓
db.py get_deadline_analysis()
 ↓
SQLite analysis_json
 ↓
AnalyzeResponse
 ↓
Angular result.set(analysis)
```

No OpenRouter call is needed.

---

## 31. Clicking × to remove a deadline

The × calls:

```ts
requestDeleteDeadline(
    $event,
    deadline
)
```

It uses:

```ts
event.stopPropagation();
```

to prevent the deadline card from also triggering:

```text
openDeadline()
```

Then it sets:

```ts
pendingDeleteDeadline
```

which displays the confirmation modal.

---

## 32. Clicking "Keep it"

HTML:

```html
(click)="cancelDeleteDeadline()"
```

This does:

```ts
this.pendingDeleteDeadline.set(null);
```

No backend call.

---

## 33. Clicking "Remove"

Calls:

```ts
confirmDeleteDeadline()
```

Flow:

```text
confirmDeleteDeadline()
 ↓
ApiService.deleteDeadline(id)
 ↓
DELETE /api/deadlines/{id}
 ↓
main.py remove_deadline()
 ↓
db.py delete_deadline()
 ↓
DELETE FROM deadlines
```

The database also clears:

```sql
DELETE FROM document_analyses
```

Why?

```text
upload A
 ↓
saved appointment #5
 ↓
document cached
```

If appointment #5 is deleted but the document cache remains:

```text
upload A again
 ↓
cached response still says appointment #5 exists
```

So deleting a deadline invalidates cached analyses.

---

## 34. Complete analysis flow

```text
USER
 │
 │ clicks "Explain & handle this"
 ▼
app.component.html
 │
 │ (click)="analyze()"
 ▼
AppComponent.analyze()
 │
 ▼
ApiService.analyze()
 │
 │ FormData(file + instruction)
 │ POST /api/analyze
 ▼
FastAPI main.py::analyze()
 │
 ├── validate type/size
 ├── read bytes
 ├── SHA-256 document
 └── prepare_document()
         │
         ├── Image → keep image
         └── PDF → PyMuPDF → JPEG pages
 │
 ▼
agent.py::analyze_document()
 │
 ├── check document cache
 │
 └── if not cached
       │
       ▼
 OpenRouter chat_completion()
       │
       ▼
 DeepSeek V4.1 Flash
       │
       │ "I need a tool"
       ▼
 tool_calls
       │
       ▼
 agent.py::_tool_calls()
       │
       ▼
 tools.py::execute_tool()
       │
       ├── verify_dutch_address()
       │      └── PDOK
       │
       ├── prepare_calendar_event()
       │      └── calendar_utils.py
       │
       ├── save_deadline()
       │      └── db.py / SQLite
       │
       ├── lookup_official_process()
       │      └── process_guide.py
       │
       └── get_upcoming_deadlines()
              └── db.py
       │
       ▼
 real tool result
       │
       │ role="tool"
       ▼
 OpenRouter again
       │
       ▼
 DeepSeek considers tool result
       │
       ├── request another tool
       │            ↑
       │            └──── loop max 9
       │
       └── final structured JSON
                    │
                    ▼
             AnalyzeResponse
                    │
             ├── save snapshot
             └── cache by SHA
                    │
                    ▼
                  HTTP
                    │
                    ▼
          AppComponent.analyze()
                    │
             result.set(response)
                    │
                    ▼
          app.component.html
                    │
                    ▼
              USER SEES RESULT
```

## The 7 files to study first

Read these in this order:

```text
1. frontend/src/app/app.component.html
          ↓
2. frontend/src/app/app.component.ts
          ↓
3. frontend/src/app/api.service.ts
          ↓
4. backend/app/main.py
          ↓
5. backend/app/agent.py
          ↓
6. backend/app/tools.py
          ↓
7. backend/app/db.py
```

Then:

```text
document_utils.py    → PDF/image preparation
openrouter_client.py → actual OpenRouter HTTP call
calendar_utils.py    → .ics + Google Calendar link
process_guide.py     → curated Dutch process information
models.py            → request/response data structures
```

## Most important concept

```text
DeepSeek does NOT execute actions.

DeepSeek decides:
"I want verify_dutch_address."

agent.py receives that request.

tools.py executes the real Python function.

The real result is sent back to DeepSeek.

DeepSeek uses that verified information
to produce the final answer.
```

That is what turns this from a simple **"send an image to an LLM and print the answer"** application into an actual **tool-calling agent workflow**.
