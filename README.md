# Handle It NL 🇳🇱

URL : https://nl-expat-copilot-1.onrender.com/

**A Dutch-letter problem solver for expats in the Netherlands.**

Moving to the Netherlands means receiving letters from municipalities, the IND, Belastingdienst, CJIB, insurers, schools, VvEs, and many other organisations.

Translation helps with the Dutch words, but it often does not answer the real questions:

- What is this?
- Is it important?
- Can I ignore it?
- Do I need to pay something?
- What is the deadline?
- Do I need to visit somewhere?
- What should I bring?
- What happens if I do nothing?
- Is this a normal Dutch administrative process?

**Handle It NL turns a Dutch letter into a plain-English explanation and safe next actions.**

---

## Why not just translate the letter?

Translation is not the same as understanding what to do.

A perfectly translated Dutch government letter can still leave a newcomer wondering:

> “Okay... but what am I supposed to do now?”

Handle It NL tries to bridge that gap.

Instead of returning only translated text, it classifies the document and identifies whether the user needs to:

- take action;
- make a payment;
- attend an appointment;
- remember a deadline;
- bring specific documents;
- or simply read the information and do nothing.

---

## What the app does

Upload a:

- JPG
- PNG
- WEBP
- scanned PDF

Handle It NL analyzes the document and classifies it as:

- **Payment required**
- **Appointment / visit**
- **Action required**
- **Information only**
- **Mixed**
- **Needs review**

The UI then answers:

```text
WHAT IS THIS?

CAN I IGNORE IT?

WHAT DO I NEED TO DO?

BY WHEN?
```

It can also extract:

- sender;
- subject;
- amount;
- payment reference;
- deadline;
- appointment date/time;
- visit location;
- things to bring;
- consequence of ignoring the letter when supported;
- useful Dutch administrative terms.

---

## Example scenarios

### Municipality appointment

A letter says:

```text
Attend Burgerzaken on 12 October at 10:20.
Bring your passport and passport photo.
```

Handle It NL can:

- explain the letter in English;
- identify the appointment;
- list what the user needs to bring;
- verify the Dutch address through PDOK;
- prepare a calendar event;
- save the appointment locally.

---

### Payment letter

A CJIB-style letter contains:

```text
Amount: €127
Payment deadline: 21 October
Payment reference: ...
```

Handle It NL can:

- classify the letter as payment required;
- explain what it means;
- extract the amount and deadline;
- explain the relevant Dutch process;
- save the payment deadline.

It does **not** perform the payment.

---

### Information-only notice

A neighbourhood notice says:

```text
A food cart will visit the neighbourhood every Tuesday.
```

Handle It NL can classify it as:

```text
INFORMATION ONLY
NO ACTION NEEDED
```

No calendar entry and no unnecessary deadline are created.

---

## Architecture

```text
             Dutch letter / scanned PDF
                       │
                       ▼
                    Angular
                       │
                       ▼
                    FastAPI
                       │
                       ▼
              OpenRouter API
                       │
                       ▼
          DeepSeek V4.1 Flash
           Vision + tool calling
                       │
              decides what it needs
                       │
       ┌───────────────┼─────────────────┐
       ▼               ▼                 ▼
     PDOK          Calendar           SQLite
 verify address    create .ics      save deadlines
       │                                 │
       └────────────────┬────────────────┘
                        ▼
                Actionable result
```

---

## The model interprets. Tools execute.

One important design rule in Handle It NL is:

> **The model can decide what should happen, but deterministic code decides what actually happened.**

For example:

- the model identifies a possible appointment;
- PDOK verifies the Dutch address;
- Python generates the `.ics` calendar file;
- SQLite determines whether a deadline was actually saved;
- duplicate appointments are detected by date/time + location;
- identical documents are cached using a SHA-256 document hash.

Uploading the exact same document again therefore does not generate a completely new interpretation.

If the model cannot produce a reliable structured result, the UI shows:

```text
MANUAL REVIEW NEEDED
```

instead of incorrectly claiming that no action is required.

---

## Tool calling

The model can request the following tools:

```text
lookup_official_process()
verify_dutch_address()
prepare_calendar_event()
save_deadline()
get_upcoming_deadlines()
```

The model does not execute these actions itself.

The flow is:

```text
OpenRouter model
      │
      ▼
tool_calls
      │
      ▼
FastAPI executes Python tool
      │
      ▼
tool result
      │
      ▼
OpenRouter model
      │
      ▼
final structured explanation
```

The Angular UI exposes these calls through the **Agent Trace**.

---

## Dutch process guidance

Handle It NL currently includes small curated process guides for:

- IND
- CJIB
- Belastingdienst

The guide supplements the uploaded document.

It does not override the original letter or current information from the authority.

---

## Address verification

Dutch addresses can be verified using the public **PDOK Location API**.

For example:

```text
Stadsplein 1, 3431 LZ Nieuwegein
```

The agent can call:

```text
verify_dutch_address()
```

and display the verified location and map link.

---

## Saved deadlines

Appointments and deadlines are stored locally in SQLite.

The dashboard shows upcoming saved items.

Clicking a saved item restores the original analysis, including:

- What is this?
- Can I ignore it?
- What do I need to do?
- Deadline
- Appointment
- What happens if I do nothing?
- What should I bring?
- Dutch terminology
- verified address;
- calendar action;
- agent trace.

Saved items can also be removed through a confirmation dialog.

---

## Duplicate protection

The same letter should not create multiple versions of the same appointment.

Handle It NL uses two mechanisms:

### Document caching

The original uploaded file is hashed with SHA-256.

```text
same file
   ↓
same hash
   ↓
same cached analysis
```

Uploading the exact same PDF again therefore reuses the previous analysis instead of asking the model to reinterpret it.

### Appointment identity

Appointments are deduplicated primarily using:

```text
date/time + physical location
```

This means differently worded model-generated titles do not create duplicate appointments.

---

## Scanned PDF support

FastAPI uses **PyMuPDF** to render scanned PDF pages into optimized JPEG images before sending them to the vision model.

Current limits:

```text
Maximum PDF size: 20 MB
Maximum pages analyzed: 5
Render resolution: 140 DPI
JPEG quality: 84
```

This keeps image payloads manageable while retaining enough document detail for OCR-style vision analysis.

---

## AI model

The default model is:

```text
deepseek/deepseek-v4.1-flash
```

It is configured through:

```text
OPENROUTER_MODEL
```

so the model layer can be changed without rewriting the application.

---

## Why open AI?

Handle It NL uses an open-weight model rather than building the application around one permanently closed model provider.

The model is accessed through OpenRouter for this demo because running a large multimodal model locally is not practical on the development laptop.

However, the application architecture remains model-independent.

The AI layer is responsible for:

- document understanding;
- classification;
- structured extraction;
- deciding which tools are useful.

Application behaviour remains controlled by transparent Python functions.

This separation makes it easier to:

- swap models;
- experiment with different open-weight models;
- change inference providers;
- self-host models in the future;
- keep business logic independent of one AI vendor.

---

## Payment safety

Handle It NL never performs payments.

For payment-related letters it may extract:

- amount;
- deadline;
- payment reference.

Users should always verify payment information against the original letter or official portal.

The application never automatically transfers money based on AI-extracted:

- IBANs;
- QR codes;
- payment references.

---

## Calendar safety

`prepare_calendar_event()` creates:

- a local `.ics` file;
- a pre-filled Google Calendar URL.

The user still reviews and confirms the event.

Handle It NL does not silently modify an external calendar.

---

## Privacy

When using this OpenRouter edition:

```text
uploaded document
      ↓
FastAPI
      ↓
OpenRouter / selected model provider
```

Document content therefore leaves the local machine for model inference.

For public demos, use **synthetic or redacted letters**.

The project includes synthetic Dutch government-style demo documents specifically for this purpose.

The OpenRouter API key remains in the FastAPI backend and is never exposed to Angular.

---

## Prerequisites

### Frontend

Angular 22.2.1

Use a supported Node.js version:

```text
Node.js ^22.22.3
Node.js ^24.15.0
or >=26.0.0
```

Check:

```powershell
node -v
npm -v
```

---

## Setup

### 1. Get an OpenRouter API key

Create a key at:

https://openrouter.ai/keys

Never commit the key to GitHub.

---

### 2. Configure the backend

```powershell
cd backend
Copy-Item .env.example .env
```

Edit `.env`:

```text
OPENROUTER_API_KEY=sk-****
OPENROUTER_MODEL=deepseek/deepseek-v4.1-flash
OPENROUTER_APP_URL=http://localhost:4200
OPENROUTER_APP_NAME=Handle It NL
```

`backend/.env` is ignored by Git.

You can alternatively configure the environment directly:

```powershell
$env:OPENROUTER_API_KEY="sk-***"
$env:OPENROUTER_MODEL="deepseek/deepseek-v4.1-flash"
```

---

### 3. Start FastAPI

```powershell
cd backend

python -m venv .venv
.venv\Scripts\Activate.ps1

pip install -r requirements.txt

uvicorn app.main:app --reload --port 8000
```

Health check:

```text
http://localhost:8000/api/health
```

Expected response:

```json
{
  "status": "ok",
  "provider": "openrouter",
  "model": "deepseek/deepseek-v4.1-flash",
  "api_key_configured": true
}
```

---

### 4. Start Angular

Open another terminal:

```powershell
cd frontend

npm install
npm start
```

Open:

```text
http://localhost:4200
```

---

## Tech stack

### Frontend

- Angular 22
- TypeScript
- HTML/CSS

### Backend

- Python
- FastAPI
- Pydantic
- httpx
- PyMuPDF

### AI

- DeepSeek V4.1 Flash
- OpenRouter
- multimodal document understanding
- function/tool calling
- structured extraction

### Tools and data

- PDOK Location API
- SQLite
- `.ics` calendar generation
- Google Calendar event links

---

## Hacktoberfest 2026

Handle It NL was created for the:

**Hacktoberfest Weekend Challenge 2026 — Build for a Friend**

The project explores a simple question:

> Translation can tell someone what a Dutch letter says. Can an AI assistant safely help them understand what they should actually do next?

---

## License

MIT
