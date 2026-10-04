# Handle It NL — OpenRouter Edition

**A Dutch-letter problem solver for expats in the Netherlands.**

Translation is only half the problem. A newcomer can translate a Dutch letter and still wonder:

- What is this?
- Is it serious?
- Can I ignore it?
- Do I need to pay?
- By what date?
- Do I have to visit somewhere?
- What should I bring?
- Is this a normal Dutch process?

Handle It NL answers those questions and then uses tools when an action is genuinely useful.

---

## Why OpenRouter?

This edition does **not** run the vision model on your laptop.

```text
Browser
  ↓
Angular
  ↓
FastAPI
  ↓
OpenRouter
  ↓
Vision + tool-capable model
```

Your machine still runs:
- Angular;
- FastAPI;
- PDF-to-image rendering;
- SQLite;
- calendar generation;
- PDOK/process tools.

The expensive model inference happens remotely.

That means a normal laptop can handle scanned PDFs without loading a 2–8 GB local model into RAM/VRAM.

---

## Default model

```text
deepseek/deepseek-v4.1-flash
```

It currently supports:
- text input;
- image input;
- tool calling;
- structured outputs.

You can switch models without changing code:

```powershell
$env:OPENROUTER_MODEL="another/model-slug"
```

or edit `backend/.env`.

---

# IMPORTANT PRIVACY CHANGE

When you use OpenRouter, uploaded document page images are sent over the internet to OpenRouter / the selected model provider for inference.

This is different from the local Ollama edition.

That means you should **not** use real highly sensitive letters in a public demo unless you are comfortable sending them to the configured cloud provider.

For Hacktoberfest demos, use redacted or synthetic sample letters.

The OpenRouter API key stays only in FastAPI. It is never sent to Angular.

---

# Supported input

- JPG
- PNG
- WEBP
- scanned PDF

For PDFs, FastAPI uses PyMuPDF to render pages to optimized JPEGs.

Current limits:

```text
Maximum PDF size: 20 MB
Maximum pages analyzed: 5
Render resolution: 140 DPI
JPEG quality: 84
```

---

# What the app does

Every letter is classified as:

- Payment required
- Appointment / visit
- Action required
- Information only
- Mixed
- Needs review

The output answers:

```text
WHAT IS THIS?

CAN I IGNORE IT?

WHAT DO I NEED TO DO?

BY WHEN?
```

It can also extract:
- amount;
- payment reference;
- deadline;
- appointment date/time;
- visit address;
- things to bring;
- common Dutch terms;
- consequence of ignoring when well supported.

---

# Tool calling

The remote model decides when it needs tools.

Available tools:

```text
lookup_official_process()
verify_dutch_address()
prepare_calendar_event()
save_deadline()
get_upcoming_deadlines()
```

The model never executes those functions itself.

OpenRouter returns a structured `tool_calls` request to FastAPI.

FastAPI executes the Python function and sends the result back to OpenRouter.

```text
OpenRouter model
      ↓
tool_calls
      ↓
FastAPI executes tool
      ↓
tool result
      ↓
OpenRouter model
      ↓
final answer
```

The Angular UI shows this as the **Agent Trace**.

---

# Prerequisites

Frontend uses Angular 22.2.1. Use a supported Node.js version:

```text
Node.js ^22.22.3, ^24.15.0, or >=26.0.0
```

Check with:

```powershell
node -v
npm -v
```

The project includes `.nvmrc` with `22.22.3`.

---

# Setup

## 1. Get an OpenRouter API key

Create a key:

https://openrouter.ai/keys

Do not put the key in Angular, GitHub, or source code.

## 2. Configure backend

Go to:

```powershell
cd backend
```

Copy:

```text
.env.example
```

to:

```text
.env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Edit `.env`:

```text
OPENROUTER_API_KEY=sk-or-v1-your-real-key
OPENROUTER_MODEL=deepseek/deepseek-v4.1-flash
OPENROUTER_APP_URL=http://localhost:4200
OPENROUTER_APP_NAME=Handle It NL
```

`backend/.env` is ignored by Git.

Alternatively, set the environment variable directly:

```powershell
$env:OPENROUTER_API_KEY="sk-or-v1-..."
$env:OPENROUTER_MODEL="deepseek/deepseek-v4.1-flash"
```

---

## 3. Start FastAPI

Windows:

```powershell
cd backend

python -m venv .venv
.venv\Scripts\Activate.ps1

pip install -r requirements.txt

uvicorn app.main:app --reload --port 8000
```

Test:

```text
http://localhost:8000/api/health
```

Expected:

```json
{
  "status": "ok",
  "provider": "openrouter",
  "model": "deepseek/deepseek-v4.1-flash",
  "api_key_configured": true
}
```

---

## 4. Start Angular

Another terminal:

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

# No Ollama required

For this OpenRouter edition you do **not** need:

```text
ollama pull ...
ollama serve
```

You can remove/stop Ollama while testing this version.

---

# Payment safety

Handle It NL never performs a payment.

For payment letters it may extract:
- amount;
- due date;
- payment reference.

But the UI/model should tell the user to verify payment details against the original document or official portal.

It never uses AI-extracted IBAN/QR details to automatically transfer money.

---

# Calendar safety

`prepare_calendar_event()` creates:

- a local `.ics` file;
- a pre-filled Google Calendar URL.

The user still confirms the event.

The app does not silently modify the user's external calendar.

---

# Dutch official-process guide

The project includes small curated process guidance for:

- IND
- CJIB
- Belastingdienst

This is supplemental guidance only.

The user's actual letter and current official authority website remain the source of truth.

---

# GitHub

Never commit:

```text
backend/.env
```

The included `.gitignore` already excludes it.

Commit:

```text
backend/.env.example
```

because it contains placeholders only.

---

# Suggested Hacktoberfest demo

Use three synthetic screenshots/PDFs:

1. **CJIB payment letter**
   - classify as Payment required;
   - explain deadline;
   - tool call official process;
   - save deadline.

2. **IND appointment/document collection**
   - classify Appointment / visit;
   - explain what to bring;
   - tool call official process;
   - verify address;
   - prepare calendar event.

3. **Neighbourhood food-cart notice**
   - classify Information only;
   - say No action needed;
   - make no unnecessary tool calls.

This shows that the agent is not just translating text—it decides what kind of real-life response is appropriate.
