# Handle It NL — `chat_completion()` Call Scenarios

This document explains how many times `chat_completion()` can be called during a single `/api/analyze` request in the current Handle It NL backend.

The important code is in:

```text
backend/app/agent.py
```

The normal agent loop is:

```py
for _ in range(9):
    assistant_message = await chat_completion(...)
```

So the normal tool-calling loop allows at most:

```text
9 chat_completion() calls
```

However, `_repair_final_json()` can make up to **2 additional `chat_completion()` calls** if the model returns malformed final JSON.

Therefore:

```text
Normal agent-loop maximum = 9
Possible repair calls      = +2
--------------------------------
Absolute theoretical max   = 11
```

---

## 1. Exact same document is already cached

Before OpenRouter is called, `analyze_document()` checks:

```py
cached = get_cached_document_analysis(
    document_hash
)
```

If the exact same uploaded file has already been analyzed:

```text
same file
   ↓
same SHA-256
   ↓
cache hit
   ↓
return saved AnalyzeResponse
```

Result:

```text
chat_completion() calls = 0
```

This is the cheapest and fastest path.

---

## 2. New document, no tool required

Example: a simple informational letter.

```text
Call 1
Model reads document
        ↓
No tool_calls
        ↓
Returns valid final JSON
        ↓
Done
```

Result:

```text
chat_completion() calls = 1
```

This is the minimum for a new, uncached document.

---

## 3. One tool round

Example: only address verification is needed.

```text
Call 1
Model reads document
        ↓
Requests verify_dutch_address()
        ↓
Python executes PDOK
        ↓
Tool result added to messages

Call 2
Model sees PDOK result
        ↓
Returns final JSON
```

Result:

```text
chat_completion() calls = 2
```

Important:

```py
await execute_tool(...)
```

does **not** itself consume an OpenRouter model call.

The flow:

```text
Model
 ↓
Tool
 ↓
Model
```

means:

```text
2 chat_completion() calls
```

---

## 4. Two sequential tool rounds

Example:

```text
verify_dutch_address()
then
prepare_calendar_event()
```

Possible flow:

```text
Call 1
Model requests address verification
        ↓
PDOK executes

Call 2
Model sees PDOK result
        ↓
Requests calendar event
        ↓
Calendar tool executes

Call 3
Model sees calendar result
        ↓
Returns final JSON
```

Result:

```text
chat_completion() calls = 3
```

---

## 5. Three sequential tool rounds

A typical appointment may require:

```text
verify_dutch_address()
prepare_calendar_event()
save_deadline()
```

If the model asks for them one at a time:

```text
Call 1 → verify address
Call 2 → prepare calendar
Call 3 → save deadline
Call 4 → final JSON
```

Result:

```text
chat_completion() calls = 4
```

---

## 6. Multiple tools requested in one model response

One `assistant_message` can contain multiple tool calls.

The code does:

```py
calls = _tool_calls(assistant_message)

for call in calls:
    result = await execute_tool(...)
```

So the model could request all of these in one response:

```text
verify_dutch_address()
prepare_calendar_event()
save_deadline()
```

Flow:

```text
Call 1
Model requests:
  - verify_dutch_address()
  - prepare_calendar_event()
  - save_deadline()
        ↓
Python executes all 3 tools
        ↓
All tool results are added to messages

Call 2
Model sees all results
        ↓
Returns final JSON
```

Result:

```text
Tool executions          = 3
chat_completion() calls  = 2
```

This is an important distinction:

```text
tool count != chat_completion count
```

---

## 7. Many tool rounds but valid final JSON

The normal loop is capped at:

```py
for _ in range(9):
```

So a valid maximum-length normal flow could be:

```text
Call 1 → tool
Call 2 → tool
Call 3 → tool
Call 4 → tool
Call 5 → tool
Call 6 → tool
Call 7 → tool
Call 8 → tool
Call 9 → final valid JSON
```

Result:

```text
chat_completion() calls = 9
```

This is the maximum normal successful agent-loop path.

---

## 8. All 9 iterations request more tools

Suppose every iteration continues requesting tools:

```text
Call 1 → tool
Call 2 → tool
...
Call 9 → tool
```

After the loop ends, the code reaches:

```py
raise RuntimeError(
    "Agent reached the maximum number "
    "of tool iterations."
)
```

Result:

```text
chat_completion() calls = 9
then request fails
```

There is no 10th normal call.

---

## 9. No tool, but malformed final JSON

Suppose the first response contains no tool calls, but its final JSON is invalid.

The code first tries:

```py
_try_parse_understanding(...)
```

If parsing fails:

```text
_try_parse_understanding()
        ↓
failed
        ↓
_repair_final_json()
```

Inside `_repair_final_json()`:

```py
repaired = await chat_completion(...)
```

Flow:

```text
Call 1
Original analysis
        ↓
Invalid JSON

Call 2
Repair JSON
        ↓
Valid JSON
```

Result:

```text
chat_completion() calls = 2
```

This can happen with **zero tool calls**.

---

## 10. JSON-schema repair fails, JSON-object fallback runs

The repair function first tries structured output using:

```py
response_format={
    "type": "json_schema",
    ...
}
```

If the provider rejects that request:

```py
except RuntimeError:
```

the code tries again with:

```py
response_format={
    "type": "json_object"
}
```

Flow:

```text
Call 1
Original analysis
        ↓
Malformed JSON

Call 2
json_schema repair
        ↓
Request fails

Call 3
json_object repair
        ↓
Valid JSON
```

Result:

```text
chat_completion() calls = 3
```

with no tools involved.

---

## 11. Tool call + final JSON repair

Example:

```text
Call 1
Model requests verify_dutch_address()
        ↓
PDOK executes

Call 2
Model returns final answer
        ↓
Final JSON is malformed

Call 3
Repair JSON
```

Result:

```text
chat_completion() calls = 3
```

If the first repair method fails and the fallback is required:

```text
Call 4
json_object repair
```

Result:

```text
chat_completion() calls = 4
```

---

## 12. Several tool rounds + JSON repair

Example:

```text
Call 1 → verify_dutch_address()
Call 2 → prepare_calendar_event()
Call 3 → save_deadline()
Call 4 → malformed final JSON
Call 5 → repair
```

Result:

```text
chat_completion() calls = 5
```

If the first repair request fails:

```text
Call 6 → json_object fallback repair
```

Result:

```text
chat_completion() calls = 6
```

---

## 13. Absolute theoretical maximum

A repair only happens when one of the normal loop iterations returns:

```text
no tool_calls
+
invalid final JSON
```

Therefore the theoretical worst case is:

```text
Call 1  → tool
Call 2  → tool
Call 3  → tool
Call 4  → tool
Call 5  → tool
Call 6  → tool
Call 7  → tool
Call 8  → tool
Call 9  → malformed final JSON
Call 10 → json_schema repair
Call 11 → json_object fallback repair
```

Result:

```text
Absolute theoretical maximum = 11 chat_completion() calls
```

This only happens when:

```text
8 tool-request rounds
+
1 malformed final-answer call
+
2 repair attempts
```

---

## 14. Why 9 tool calls does NOT become 11

If all 9 normal iterations request tools:

```text
Call 1 → tool
...
Call 9 → tool
```

the code exits the loop and immediately raises:

```py
RuntimeError(
    "Agent reached the maximum number of tool iterations."
)
```

So that path is:

```text
9 calls
+
error
```

not:

```text
11 calls
```

The repair mechanism only runs after a response with **no tool calls**.

---

## 15. Full scenario table

| Scenario | Tool usage | `chat_completion()` calls |
|---|---:|---:|
| Exact document cached | None | **0** |
| New document, no tools, valid JSON | None | **1** |
| No tools, malformed JSON, repair succeeds | None | **2** |
| No tools, first repair fails, fallback works | None | **3** |
| One tool round | 1 stage | **2** |
| Two sequential tool rounds | 2 stages | **3** |
| Three sequential tool rounds | 3 stages | **4** |
| 3 tools requested together in one response | 3 tools | **2** |
| 3 tool rounds + JSON repair | 3 stages | **5–6** |
| 8 tool rounds + valid final response | 8 stages | **9** |
| 8 tool rounds + malformed final response + repair | 8 stages | **10–11** |
| All 9 normal calls request tools | 9 stages | **9, then error** |

---

## 16. Easy formula

For a successful normal flow:

```text
chat_completion calls
=
tool-request rounds
+ 1 final-answer call
+ optional repair calls
```

where:

```text
optional repair calls = 0, 1, or 2
```

Example:

```text
2 tool rounds
+ 1 final call
+ 0 repairs
= 3 chat_completion calls
```

Another example:

```text
2 tool rounds
+ 1 malformed final call
+ 1 repair
= 4 chat_completion calls
```

---

## 17. Tool executions are not the same as LLM rounds

Suppose one model response asks for:

```text
verify_dutch_address()
prepare_calendar_event()
save_deadline()
```

Your code executes:

```py
for call in calls:
    result = await execute_tool(...)
```

All three tools are executed before the next model request.

Therefore:

```text
LLM
 ↓
Tool A
Tool B
Tool C
 ↓
LLM
```

is:

```text
3 tool executions
2 chat_completion calls
```

not 4 LLM calls.

---

## 18. Typical appointment example

For a municipality appointment, the model may need:

```text
verify_dutch_address()
prepare_calendar_event()
save_deadline()
```

### Best-case batching

If the model requests all three together:

```text
Call 1
 ↓
3 tool executions
 ↓
Call 2 final JSON
```

Result:

```text
2 chat_completion calls
```

### Sequential tool calling

If the model requests one at a time:

```text
Call 1 → verify address
Call 2 → prepare calendar
Call 3 → save deadline
Call 4 → final JSON
```

Result:

```text
4 chat_completion calls
```

### Sequential + malformed final JSON

```text
Call 1 → verify address
Call 2 → prepare calendar
Call 3 → save deadline
Call 4 → malformed final JSON
Call 5 → repair
```

Result:

```text
5 calls
```

or:

```text
6 calls
```

if the first repair method fails.

So for a normal rich appointment document, a practical expectation is roughly:

```text
2–4 OpenRouter calls normally
```

with larger numbers mainly being defensive/error-handling cases.

---

# Summary

The current Handle It NL limits are:

```text
Cached document:
0 calls

Simple new document:
1 call

Normal tool-calling document:
usually 2–4 calls

Normal agent loop maximum:
9 calls

Absolute theoretical maximum including JSON repair:
11 calls
```

The most important relationship to remember is:

```text
Tool count != LLM call count
```

A single LLM response can request multiple tools, and all of those tools can execute before the next `chat_completion()` call.
