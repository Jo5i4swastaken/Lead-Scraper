# Agent Design Patterns

Proven patterns for building effective omniagents agents, drawn from real working examples.

## Table of Contents

1. [Tool output formatting](#1-tool-output-formatting)
2. [Read before write](#2-read-before-write)
3. [File-based memory](#3-file-based-memory)
4. [API wrapper tools](#4-api-wrapper-tools)
5. [Image to structured data](#5-image-to-structured-data)
6. [Browser automation via MCP](#6-browser-automation-via-mcp)
7. [Multi-source synthesis](#7-multi-source-synthesis)
8. [Writing good instructions](#8-writing-good-instructions)
9. [Safe tool approval patterns](#9-safe-tool-approval-patterns)
10. [Output format drives instructions](#10-output-format-drives-instructions)

---

## 1. Tool output formatting

Return whatever format the LLM can act on most effectively. The omniagents builtins use a mix depending on the tool:

- **Search tools** (`web_search`, `scholar_search`) return JSON — structured results with titles, links, and snippets that the LLM can sift through.
- **File tools** (`read_file`) return line-numbered content; edit/write tools return concise status strings like `"Successfully updated foo.py - made 2 replacement(s)"`.
- **Bash** (`execute_bash`) returns a status header (`Exit code: 0 (success) | Wall time: 42ms`) followed by raw stdout/stderr.

For simple custom tools, returning a formatted string is the easiest approach:

```python
@function_tool
def get_weather(latitude: float, longitude: float) -> str:
    """Get current weather for a location."""
    # ... API call ...
    return (
        f"Temperature: {current['temperature_2m']}°F\n"
        f"Humidity: {current['relative_humidity_2m']}%\n"
        f"Conditions: {condition}"
    )
```

For tools that return complex structured data (like search results with many fields), JSON is fine — LLMs handle it well. Use your judgement based on what the LLM needs to do with the result.

---

## 2. Read before write

For any agent that modifies files or code, the workflow should always be:

1. **Locate** — `glob_files` or `grep_files` to find relevant files
2. **Understand** — `read_file` to see the current state
3. **Edit** — `edit_file` for targeted changes
4. **Verify** — `execute_bash` to run tests or the code

Example instructions for a coding agent:
```
You are a skilled programmer. When asked to fix bugs or modify code:

1. **Locate** - Use glob_files or grep_files to find relevant files
2. **Understand** - Always read_file before editing. Never modify code you haven't seen.
3. **Edit** - Use edit_file to make targeted changes. Keep edits minimal and focused.
4. **Verify** - Run tests or the code to confirm your fix works
```

The agent should never edit a file it hasn't read first. This prevents blind modifications that break things.

---

## 3. File-based memory

A simple JSON file with three tools gives agents persistent memory across conversations. This pattern works well for dozens of user preferences — no vector database needed.

### The tools

```python
import json
from pathlib import Path
from filelock import FileLock
from omniagents import function_tool

MEMORY_FILE = Path("memories/preferences.json")
LOCK_FILE = Path("memories/preferences.json.lock")

def _load_memories() -> list[str]:
    if MEMORY_FILE.exists():
        return json.loads(MEMORY_FILE.read_text())
    return []

def _save_memories(memories: list[str]) -> None:
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(memories, indent=2))

@function_tool
def read_memories() -> str:
    """Read all stored memories about the user.
    Call this at the start of a conversation to recall what you know."""
    with FileLock(LOCK_FILE):
        memories = _load_memories()
    if not memories:
        return "No memories stored yet."
    return "Known facts about the user:\n" + "\n".join(f"- {m}" for m in memories)

@function_tool
def save_memory(fact: str) -> str:
    """Save a new fact about the user.

    Args:
        fact: A concise fact to remember (e.g., "User is vegetarian")
    """
    with FileLock(LOCK_FILE):
        memories = _load_memories()
        if fact.lower() in [m.lower() for m in memories]:
            return f"Already remembered: {fact}"
        memories.append(fact)
        _save_memories(memories)
    return f"Remembered: {fact}"

@function_tool
def delete_memory(fact: str) -> str:
    """Remove a stored fact that is no longer true.

    Args:
        fact: The fact to forget (must match an existing memory)
    """
    with FileLock(LOCK_FILE):
        memories = _load_memories()
        lower_memories = [m.lower() for m in memories]
        if fact.lower() in lower_memories:
            idx = lower_memories.index(fact.lower())
            removed = memories.pop(idx)
            _save_memories(memories)
            return f"Forgot: {removed}"
    return f"No matching memory found for: {fact}"
```

### Key instruction pattern

The agent must be told to check memory at the start of every conversation:

```
Before responding to ANY user message, you MUST call `read_memories()` to check
what you already know about the user. Do this even if the user doesn't mention
preferences — you may already have stored facts.
```

### Constraints vs preferences

When storing user facts, instructions should distinguish hard rules from soft suggestions:

```
**Constraints** (allergies, restrictions, dislikes) are hard rules — NEVER violate these.

**Preferences** (favorite cuisines, liked ingredients) are soft suggestions — use them
to inform recommendations but offer variety. Don't always suggest Thai food just because
they like Thai. Mix it up!
```

Without this distinction, the agent will over-index on preferences and give repetitive suggestions.

### When to use this pattern

- Dozens of facts, not thousands
- Discrete facts ("vegetarian", "allergic to X", "has an air fryer")
- All stored facts are potentially relevant to every conversation

If you need hundreds+ of memories or semantic search, consider a vector database instead.

---

## 4. API wrapper tools

Wrap external APIs in `@function_tool` functions. The tool handles the HTTP call and formats the response for the LLM.

```python
import httpx
from omniagents import function_tool

@function_tool
def geocode(city: str) -> str:
    """Convert a city name to latitude/longitude coordinates.

    Args:
        city: Name of the city (e.g., "Paris", "New York", "Tokyo")
    """
    response = httpx.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 5},
    )
    data = response.json()

    if "results" not in data:
        return f"No locations found for '{city}'"

    locations = []
    for r in data["results"]:
        loc = f"{r['name']}, {r.get('admin1', '')}, {r['country']} (lat={r['latitude']}, lon={r['longitude']})"
        locations.append(loc)
    return "\n".join(locations)
```

The recipe:
1. Wrap the API call in a `@function_tool`
2. Write a clear docstring explaining what it does and when to use it
3. Return data formatted as readable text, not raw JSON
4. Let the agent decide when and how to use it

### Chaining tools

Agents naturally chain tools when each one returns useful data. For example, a weather agent:
1. `geocode("Tokyo")` → returns coordinates
2. `get_weather(35.69, 139.69)` → returns formatted weather

The agent reads the output of the first tool and uses it as input to the second. No orchestration code needed — just clear tool docstrings.

---

## 5. Image to structured data

LLMs with vision can extract structured data from images. Combine the builtin `read_image` tool with Pydantic models and a database for a powerful pipeline.

### Define the schema

```python
from enum import Enum
from pydantic import BaseModel

class ExpenseCategory(str, Enum):
    GROCERIES = "groceries"
    DINING = "dining"
    COFFEE = "coffee"
    TRANSPORTATION = "transportation"
    OTHER = "other"

class LineItem(BaseModel):
    description: str
    quantity: float = 1.0
    total_price: float

class Receipt(BaseModel):
    merchant_name: str
    category: ExpenseCategory
    items: list[LineItem]
    total: float
```

### The flow

```
Image → read_image() → LLM extracts structured data → save to database → query later
```

The LLM handles OCR, understanding, and categorization in one step. The Pydantic model ensures consistent data shape for the database.

### Database safety

When giving agents SQL query tools, only allow SELECT:
```python
@function_tool
def query_expenses(sql_query: str) -> str:
    """Query the expenses database using SQL."""
    if not sql_query.strip().upper().startswith("SELECT"):
        return "Error: Only SELECT queries are allowed for safety."
    # ... execute and format results ...
```

---

## 6. Browser automation via MCP

The Playwright MCP server gives agents full browser control. This is how agents interact with websites — searching, clicking, filling forms, taking screenshots.

### Setup

```python
from agents import Agent
from agents.mcp import MCPServerStdio

playwright_server = MCPServerStdio(
    params={
        "command": "npx",
        "args": ["@playwright/mcp@latest"],
    },
    name="Playwright Browser",
)
```

In YAML, this translates to:
```yaml
mcp_servers:
  - name: playwright-browser
    type: stdio
    params:
      command: npx
      args: ["@playwright/mcp@latest"]
```

### Key tools provided by Playwright MCP

- `browser_navigate` — go to a URL
- `browser_click` — click elements
- `browser_type` — type into fields
- `browser_snapshot` — read page structure (accessibility tree)
- `browser_screenshot` — capture the screen

### Instruction tips for browser agents

```
## Tips
- Use browser_snapshot to read page structure before clicking
- If you encounter popups or modals, try to dismiss them
- Take screenshots at key moments to show progress
- Never enter payment information
- Stop at the cart — don't proceed to checkout
```

The agent uses snapshots to understand what's on the page, then decides what to click or type. It's the same perceive → reason → act loop, just applied to a browser.

---

## 7. Multi-source synthesis

Agents that pull data from multiple sources and synthesize a coherent output. The morning briefing pattern:

1. Read stored preferences (memory) → know what topics to search
2. Fetch weather for user's location (API)
3. Check today's calendar (local data)
4. Search news for each topic of interest (web search)
5. Synthesize into a personalized briefing

The agent decides what to fetch based on stored preferences. No hardcoded logic — just instructions and tools.

### Instructions pattern

```
When asked for a briefing, follow this order:
1. **Weather** - Call get_weather() with their location
2. **Calendar** - Call get_todays_events() for their schedule
3. **News** - Call web_search() for each of their news topics (limit to 2-3 searches)
4. **Synthesize** - Combine everything into a friendly, scannable briefing
```

---

## 8. Writing good instructions

### Use narrative language, not pseudo-code

**Good:**
```
When asked to fix bugs or modify code:
1. Locate relevant files with glob_files or grep_files
2. Always read_file before editing — never modify code you haven't seen
3. Use edit_file for targeted changes, keep edits minimal
4. Run tests to confirm your fix works
```

**Bad:**
```
if user_input.contains("fix"):
    tool.read_file()
    tool.edit_file()
```

### Put important instructions first

Critical guidance goes at the top. The agent is more likely to follow instructions that appear early:

```
## IMPORTANT: Always Check Memory First

Before responding to ANY user message, you MUST call read_memories()...

## Other Capabilities
...
```

### Don't hard-code tool sequences

Tell the agent what to accomplish, not a rigid step-by-step. LLMs are good at planning:

```
# Good - goal-oriented
Use these tools as needed to accomplish the goal.

# Less good - rigid sequence
Step 1: always call tool_a. Step 2: always call tool_b. Step 3: always call tool_c.
```

### Test tools separately before giving them to agents

Verify tools work on their own before wiring them into an agent. Use the `unwrap_tools()` context manager for testing:

```python
from utils import unwrap_tools

with unwrap_tools():
    print(geocode("Paris"))
    print(get_weather(48.86, 2.35))
```

---

## 9. Safe tool approval patterns

Use SafeAgent to gate dangerous operations while auto-approving safe ones:

```python
runner = Runner.from_agent(
    coder,
    safe=True,
    safe_tool_names=["read_file", "glob_files", "grep_files"],  # Auto-approve read-only
)
# edit_file, write_file, execute_bash still require approval
```

In YAML:
```yaml
use_safe_agent: true
safe_agent_options:
  safe_tool_names:
    - read_file
    - glob_files
    - grep_files
  safe_tool_patterns:
    - "^read_.*"
    - "^get_.*"
```

The principle: read-only tools are safe to auto-approve. Anything that writes, deletes, or executes should require approval.

---

## 10. Output format drives instructions

The same agent with the same tools needs different instructions depending on how the output will be consumed.

### Text output (markdown, for reading)

```
**Weather in Seattle**
- Currently: 52°F, Partly cloudy
- High: 58°F, Low: 48°F
- Chance of rain: 20%

**News: AI**
- [OpenAI announces new model](https://...)
```

### Voice output (TTS, for listening)

```
Good morning! It's currently 52 degrees in Seattle with partly cloudy skies.
The high today will be 58 with a 20 percent chance of rain.

In AI news, OpenAI announced a new reasoning model yesterday.
```

Voice instructions must specify: no markdown, no URLs, no special characters, natural transitions, conversational tone.

You can use the same tools with two different agents — one for text, one for voice — just with different instructions.
