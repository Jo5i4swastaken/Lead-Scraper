---
name: omniagents-basic
description: Create basic AI agents using the OmniAgents YAML format. Use this skill whenever the user wants to create an AI agent, build a chatbot, scaffold an omniagents project, set up an agent with tools, create a skill for an agent, generate tools from an OpenAPI spec, or mentions "omniagents" in the context of agent creation. Also trigger when the user wants to add tools to an existing omniagents agent, add skills to an agent, generate an MCP server from a REST API, debug an agent server, or test an agent via WebSocket. Even if they just say "make me an agent", "I need a bot that does X", or "turn this API into agent tools", this skill has the answer.
---

# OmniAgents Basic Agent Creator

This skill helps you create working AI agents using the OmniAgents YAML configuration format. Agents are runnable with `omniagents run -c agent.yml`.

## Installation

OmniAgents is hosted on a private Gemfury registry. Install with:

```bash
pip install --extra-index-url https://pypi.fury.io/ericmichael/ "omniagents[all]"
```

Or add to `requirements.txt`:

```
--extra-index-url https://pypi.fury.io/ericmichael/
omniagents[all]>=0.6.31
python-dotenv
```

The agent also needs an API key. Create a `.env` file in the agent directory:

```
OPENAI_BASE_URL=https://rgvaiclass.com/v1
OPENAI_API_KEY=sk-...

# Required for web_search, scholar_search, youtube_search tools
SERPAPI_API_KEY=...
```

OmniAgents automatically loads `.env` files from the agent directory.

## What you're building

An OmniAgents agent is a directory containing:

```
my-agent/
├── agent.yml          # Agent configuration (required)
├── instructions.md    # System prompt (optional, recommended)
├── context.py         # Context factory (optional, for dynamic data)
├── tools/             # Custom tool implementations (optional)
│   └── my_tools.py
└── skills/            # Skills for the agent (optional)
    └── my-skill/
        └── SKILL.md
```

The YAML config wires together the model, instructions, and tools. OmniAgents discovers tools from `tools/`, context factories from `.py` files in the agent directory, and skills from configured skill directories.

## Step-by-step workflow

### 1. Understand what the user needs

Before writing anything, clarify:
- What should the agent do? (purpose, personality, domain)
- Does it need custom tools, or are the builtins enough?
- Will it run in web mode (browser UI, the default), ink mode (terminal), or server mode (API)?

### 2. Write the agent.yml

Start with this template and adapt it:

```yaml
name: Agent Name
model: gpt-5.2
welcome_text: "A greeting shown when the agent starts."
instructions_file: instructions.md
tools:
  - tool_name_1
  - tool_name_2
model_settings:
  temperature: 0.7
  max_tokens: 4096
```

**Required fields:**
- `name` (str): Human-readable display name
- `model` (str): Model identifier. Default to `gpt-5.2` unless the user specifies otherwise

**Common optional fields:**
- `welcome_text`: Greeting shown on start
- `instructions`: Inline system prompt (use `instructions_file` instead for anything longer than a sentence)
- `instructions_file`: Path to markdown file with system prompt (relative to agent.yml)
- `tools`: List of tool names (builtin or custom) to make available
- `model_settings`: Dict with `temperature`, `max_tokens`, `top_p`, etc.
- `max_turns`: Max conversation turns before stopping (default: 20)
- `use_safe_agent`: Whether tools require approval before running (default: true)

### 3. Write the instructions file

Create `instructions.md` with the agent's system prompt. Keep it focused on the agent's purpose and behavior. The instructions should tell the model who it is and how to behave — not restate what tools are available (the model already knows that from the tool definitions).

### 4. Add tools

Mix builtin tools and custom tools as needed. List them all by name in the `tools` array in agent.yml.

#### Builtin tools

OmniAgents ships with these builtin tools — just reference them by name, no code needed:

| Tool | Purpose |
|------|---------|
| `read_file` | Read file contents with line numbers |
| `write_file` | Create or overwrite files |
| `edit_file` | Targeted find-and-replace edits |
| `apply_patch` | Apply multi-file patches |
| `glob_files` | Find files by glob pattern |
| `grep_files` | Search file contents with regex |
| `list_directory` | List directory tree with depth control |
| `execute_bash` | Run shell commands |
| `download_file` | Download files from URLs |
| `read_image` | Read images for vision processing |
| `display_artifact` | Display rich content (markdown, HTML, images, PDFs) in the UI |
| `web_search` | Google search via SerpAPI (requires `SERPAPI_API_KEY`) |
| `scholar_search` | Google Scholar search (requires `SERPAPI_API_KEY`) |
| `youtube_search` | YouTube video search (requires `SERPAPI_API_KEY`) |

See `references/builtin-tools.md` for full parameter details on each builtin tool.

#### Custom tools

Create Python files in the `tools/` directory. Every function decorated with `@function_tool` from `omniagents` is automatically discovered.

```python
from omniagents import function_tool

@function_tool
def my_tool(param: str, count: int = 5) -> str:
    """One-line description of what this tool does.

    Args:
        param: What this parameter is for.
        count: How many times to do it.
    """
    return f"Result: {param} x {count}"
```

The rules for custom tools:
- Import `function_tool` from `omniagents` (not from `agents` — the omniagents decorator adds a discovery marker that the loader looks for)
- The docstring becomes the tool description the model sees, so write it clearly
- Use Python type hints on all parameters — they become the tool's JSON schema
- Supported types: `str`, `int`, `float`, `bool`, `Optional[T]`, `List[T]`, `Dict[str, T]`, `Literal["a", "b"]`
- Default values make parameters optional
- Return `str` or `Dict[str, Any]` — the return value is what the model sees as the tool result
- File naming doesn't matter — any `.py` file in `tools/` works (except `__init__.py` which is skipped)

### 5. Run the agent

```bash
# Web UI (default) — opens browser
omniagents run -c agent.yml

# Terminal UI
omniagents run -c agent.yml --mode ink

# API server (useful for debugging and programmatic access)
omniagents run -c agent.yml --mode server --port 9494
```

Common flags:
- `--mode web|ink|server`: Interface mode
- `--approvals skip`: Disable tool approval prompts (useful during development)
- `--debug` / `-d`: Enable debug logging
- `--session-id ID`: Resume a previous session

### 6. Debug with server mode

Server mode exposes the agent as a JSON-RPC 2.0 WebSocket API at `/ws`. This is useful for testing the agent programmatically or building custom frontends.

```bash
omniagents run -c agent.yml --mode server --port 9494
```

To test it, connect via WebSocket and send JSON-RPC messages:

```python
import asyncio, websockets, json

async def test():
    async with websockets.connect("ws://127.0.0.1:9494/ws") as ws:
        # Get agent info
        await ws.send(json.dumps({
            "jsonrpc": "2.0", "id": "1",
            "method": "get_agent_info", "params": {}
        }))
        print(await ws.recv())

        # Send a message
        await ws.send(json.dumps({
            "jsonrpc": "2.0", "id": "2",
            "method": "start_run",
            "params": {"prompt": "Hello, what can you do?"}
        }))

        # Read responses until run_end
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
            method = msg.get("method", "")
            print(f"{method}: {msg}")

            # Handle tool approval if SafeAgent is enabled
            if method == "client_request" and msg["params"].get("function") == "ui.request_tool_approval":
                await ws.send(json.dumps({
                    "jsonrpc": "2.0",
                    "method": "client_response",
                    "params": {
                        "request_id": msg["params"]["request_id"],
                        "ok": True,
                        "result": {"approved": True, "always_approve": False}
                    }
                }))

            if method == "run_end":
                break

asyncio.run(test())
```

Key server events you'll see:
- `run_started` — run begins
- `tool_called` — model wants to call a tool
- `client_request` — server asks for tool approval (when SafeAgent is on)
- `tool_result` — tool returned a result
- `message_output` — model's text response
- `run_end` — run completed (check `end_reason`: "completed", "cancelled", "max_turns", "error")

## Dynamic instructions with context factories

Instructions support Jinja2 templates. To feed data into them, use **context factories** — Python functions that fetch or compute context at runtime.

### How it works

1. Define a context factory in a `.py` file in the agent directory (next to `agent.yml`)
2. Reference it by name in `agent.yml` via the `context` field
3. Pass input data via `variables`
4. Use `{{ variable_name }}` in instructions

### Example

**agent.yml:**
```yaml
name: Personal Assistant
model: gpt-5.2
instructions_file: instructions.md
context: build_user_context
variables:
  user_id: "${USER_ID:-user_001}"
tools: []
```

**instructions.md:**
```markdown
You are a personal assistant for {{ user_name }}.

User profile:
- Location: {{ location }}
- Timezone: {{ timezone }}
- Current time: {{ current_time }}

Personalize all responses based on this information.
```

**context.py:**
```python
from datetime import datetime
from zoneinfo import ZoneInfo
from omniagents.core.context.decorator import context_factory

# Simulating a database lookup
USER_DB = {
    "user_001": {"name": "Alice", "location": "San Francisco", "timezone": "America/Los_Angeles"},
    "user_002": {"name": "Bob", "location": "London", "timezone": "Europe/London"},
}

@context_factory
def build_user_context(variables):
    """Fetch user data and build template context."""
    user_id = variables.get("user_id", "unknown")
    user = USER_DB.get(user_id, {"name": "Guest", "location": "Unknown", "timezone": "UTC"})

    tz = ZoneInfo(user["timezone"])
    return {
        "user_name": user["name"],
        "location": user["location"],
        "timezone": user["timezone"],
        "current_time": datetime.now(tz).strftime("%I:%M %p %Z"),
    }
```

### Key rules

- The factory function must be decorated with `@context_factory` from `omniagents.core.context.decorator`
- It receives the `variables` dict (after env var substitution) and returns a dict (or dataclass/Pydantic model)
- The returned keys become available as `{{ key }}` in Jinja2 templates
- Discovery scans `.py` files directly in the agent directory (not subdirectories, not `tools/`)
- The `context` field in YAML must match the function name exactly
- If no context factory is specified, `variables` are used directly as template context
- Templates use silent undefined — missing variables render as empty strings, not errors

### Without a factory (simple variables)

For simple cases where you don't need to fetch external data, just use `variables` directly:

```yaml
name: Greeter
model: gpt-5.2
instructions: "You are a helpful assistant for {{ user_name }} who works in {{ department }}."
variables:
  user_name: "${USER_NAME:-World}"
  department: "${DEPARTMENT:-Engineering}"
tools: []
```

## Handoffs (multi-agent)

An agent can hand off conversations to other agents. Each handoff becomes a tool the model can call.

```yaml
name: Router
model: gpt-5.2
instructions: "Route the user to the right specialist based on their question."
tools: []
handoffs:
  - yaml: ./agents/math_expert/agent.yml
  - yaml: ./agents/writer/agent.yml
    tool_name_override: "transfer_to_writer"
    tool_description_override: "Hand off to the writing specialist"
```

Each handoff entry points to another agent's YAML file. The target agent is a full agent with its own config, instructions, and tools. Optional overrides let you customize the handoff tool's name and description as seen by the model.

## Safe agent options

By default, `use_safe_agent: true` means every tool call requires user approval. You can fine-tune this:

```yaml
use_safe_agent: true
safe_agent_options:
  skip_approvals: false          # Set true to auto-approve everything
  halt_on_rejection: true        # Stop the agent if user rejects a tool call
  safe_tool_names:               # These tools never need approval
    - get_current_time
    - read_file
    - glob_files
  safe_tool_patterns:            # Regex patterns for safe tools
    - "^read_.*"
    - "^get_.*"
    - "^list_.*"
```

This is useful for letting read-only tools run freely while still gating destructive ones like `execute_bash` or `write_file`.

## MCP servers

Agents can use tools from MCP (Model Context Protocol) servers. This lets you integrate external tool providers without writing custom Python tools.

```yaml
name: MCP Agent
model: gpt-5.2
instructions: "You have access to external tools via MCP."
tools: []
mcp_servers:
  - name: my-mcp-server
    type: stdio
    params:
      command: my_mcp_server_binary
      args: ["--verbose"]
      env:
        API_KEY: "${MCP_API_KEY}"
    options:
      cache_tools_list: true
```

- `name`: Unique identifier for this server
- `type`: Server transport type (`stdio` is most common)
- `params.command`: The command to launch the MCP server process
- `params.args`: Command-line arguments (optional)
- `params.env`: Environment variables for the server process (optional)
- `options.cache_tools_list`: Cache the tool list instead of re-fetching each time (optional)

Tools provided by MCP servers are automatically available to the agent alongside builtin and custom tools. You can also set a global `mcp_config` to apply settings across all MCP servers:

```yaml
mcp_config:
  convert_schemas_to_strict: true
```

## Environment variable substitution

YAML string values support `${VAR}` syntax anywhere:

```yaml
model: ${MODEL_NAME:-gpt-5.2}           # Fallback if not set
variables:
  api_key: "${API_KEY}"                  # Error if not set
  token: "${TOKEN:?Token is required}"   # Error with custom message
```

A `.env` file in the agent directory (or parent directories) is automatically loaded.

## Voice / realtime mode

Agents can communicate via real-time audio using OpenAI's Realtime API. Enable it with:

```yaml
name: Voice Assistant
model: gpt-realtime
realtime_mode: true
realtime_settings:
  voice: alloy
  modalities: [audio]
tools:
  - get_weather
```

Voice agents run in web mode (browser enables microphone automatically) or server mode (separate `/ws/realtime` WebSocket endpoint). Tools work normally during voice sessions.

See `references/voice-mode.md` for the full configuration reference, WebSocket API, streaming events, and instruction tips for voice agents.

## Tools from OpenAPI specs

OmniAgents can generate agent tools directly from OpenAPI 3.x specifications — no manual tool writing needed. This is the fastest way to give an agent access to a REST API.

### Generate Python tool files

Generate a Python file with `@function_tool` functions from an OpenAPI spec:

```bash
omniagents generate openapi \
  --spec petstore_spec.yaml \
  --name pet_api \
  --output tools/pet_api_tools.py \
  --include-tags pets animals
```

This creates a file in `tools/` with one `@function_tool` per API operation. The generated tools are automatically discovered by the YAML loader, so you can reference them by name in `agent.yml`:

```yaml
name: Pet Finder
model: gpt-5.2
instructions_file: instructions.md
tools:
  - get_pet_by_id
  - search_pets
  - list_categories
  - read_image
```

The generated tools use environment variables for configuration:
- `{NAME}_BASE_URL` — API endpoint (e.g., `PET_API_BASE_URL`)
- `{NAME}_KEY` — API key (e.g., `PET_API_KEY`)

Set these in a `.env` file in the agent directory or export them in the shell.

CLI flags:

| Flag | Description |
|------|-------------|
| `--spec, -s` | Path to OpenAPI spec (YAML or JSON). Required. |
| `--name, -n` | API name, used as env var prefix. Required. |
| `--output, -o` | Output file path (default: `tools/<name>_tools.py`) |
| `--include-tags` | Only include operations with these OpenAPI tags |
| `--exclude-operations` | Exclude specific operationIds |
| `--context-params` | Path params injected from runtime context instead of function args |
| `--project, -P` | Project directory (default: cwd) |

### Generate MCP server files

Alternatively, generate a FastMCP server from a spec. This is useful for sharing API tools across multiple agents or integrating with non-omniagents systems:

```bash
omniagents generate mcp \
  --spec petstore_spec.yaml \
  --name pet_api \
  --server-name "Pet Store API" \
  --output pet_api_mcp_server.py
```

Then reference the MCP server in the agent's YAML:

```yaml
name: Pet Finder
model: gpt-5.2
tools: []
mcp_servers:
  - name: pet-api
    type: stdio
    params:
      command: python
      args: ["pet_api_mcp_server.py"]
      env:
        PET_API_BASE_URL: "https://api.example.com"
        PET_API_KEY: "${PET_API_KEY}"
```

### When to use which approach

- **Generated tools** (default choice) — Tools land in `tools/`, are discovered by the YAML loader, and can be listed by name in `agent.yml`. You can also customize the generated code after generation.
- **Generated MCP server** — When you want to share API tools across multiple agents, or the API needs to run as a separate process.

### Common pattern: bridging tools

OpenAPI-generated tools handle API calls, but you often need custom "glue" tools alongside them. For example, an API might require species codes but users provide common names. Write a custom bridging tool in `tools/`:

```python
@function_tool
def lookup_species_code(query: str) -> str:
    """Search for a bird species by common name and return its API code."""
    # ... search logic ...
```

Then list both the generated and custom tools in `agent.yml`.

See `references/openapi.md` for advanced features like context parameter injection, nested object flattening, and type mappings.

## Skills

Skills are modular instruction bundles that teach an agent how to handle specific tasks. They use progressive disclosure — the agent sees only skill names and descriptions until it needs the full instructions.

### How skills work

1. A **context factory** discovers skills from configured directories and generates an `available_skills_block`
2. The block is injected into the agent's instructions via Jinja2 (`{{ available_skills_block }}`)
3. At runtime, the agent scans the index and reads the full `SKILL.md` only when a skill is relevant to the current task
4. Skills can reference additional files (`references/`, `scripts/`, `assets/`) that are loaded only when needed

### Creating a skill

Each skill is a directory with a `SKILL.md` file containing YAML frontmatter:

```
my-skill/
├── SKILL.md               # Required — frontmatter + instructions
├── references/            # Optional — deep documentation
│   └── api-schema.md
├── scripts/               # Optional — helper scripts
│   └── validate.py
└── assets/                # Optional — templates, boilerplate
    └── starter-template.txt
```

**SKILL.md format:**

```markdown
---
name: my-skill
description: One-line description of what this skill does and when to use it.
---

# My Skill

Instructions for the agent go here. This is what the agent reads
when it activates the skill.

## Steps
1. Do this first
2. Then do this
...
```

**Frontmatter fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Lowercase, alphanumeric + hyphens, max 64 chars. Must match the directory name. |
| `description` | Yes | What the skill does and when to trigger it. Max 1024 chars. |
| `license` | No | License identifier |
| `compatibility` | No | Compatibility notes (max 500 chars) |
| `allowed-tools` | No | Tools this skill is allowed to use |
| `metadata` | No | Custom key-value pairs |

**Name rules:**
- Lowercase only (after normalization)
- Only alphanumeric characters and hyphens
- Cannot start or end with a hyphen
- No consecutive hyphens (`--`)

### Wiring skills into an agent

Skills are discovered from **skill root directories** and injected into instructions via a context factory.

**1. Organize skills in a directory:**

```
my-agent/
├── agent.yml
├── instructions.md
├── context.py
└── skills/
    ├── code-review/
    │   └── SKILL.md
    └── testing/
        └── SKILL.md
```

**2. Write a context factory that discovers skills:**

```python
from pathlib import Path
from omniagents.core.context.decorator import context_factory
from omniagents.core.skills import build_available_skills_block

@context_factory
def build_context(variables):
    """Build context with available skills."""
    agent_dir = Path(__file__).parent
    skill_roots = [agent_dir / "skills"]
    return {
        "available_skills_block": build_available_skills_block(skill_roots),
    }
```

**3. Reference the context factory and use the variable in instructions:**

```yaml
# agent.yml
name: My Agent
model: gpt-5.2
instructions_file: instructions.md
context: build_context
tools:
  - read_file
```

```markdown
<!-- instructions.md -->
{{ available_skills_block }}

You are a helpful assistant. When a task matches an available skill,
activate it by reading the full SKILL.md before proceeding.
```

### Skills discovery and precedence

- `build_available_skills_block(skill_roots)` scans each root for directories containing `SKILL.md`
- Multiple skill roots can be provided (e.g., local project skills + global shared skills)
- When the same skill name appears in multiple roots, the **first one wins** — put local/project skills before global ones
- Invalid skills (missing required fields, bad name format) are silently excluded
- The generated block is XML that lists each skill's name, description, and SKILL.md path

### Skills activation protocol

Include instructions like these to teach the agent how to use skills:

```markdown
## Skills Protocol

At the start of each new task, scan the available skills index.
If one or more skills are relevant:

1. Read each selected skill's SKILL.md (use its location path).
2. Follow the skill's progressive-disclosure guidance — only load
   references, assets, or scripts when the current subtask needs them.
3. Do not assume the contents of SKILL.md without reading it.

Skills may require other skills. When a skill references another,
treat it as a dependency and activate that skill too.
```

See `references/skills.md` for the full skills development guide including validation rules, progressive disclosure patterns, and the generated XML format.

## Reference files

- `references/builtin-tools.md` — Full parameter documentation for each builtin tool
- `references/openapi.md` — OpenAPI integration: runtime tool loading, Python codegen, MCP server codegen, CLI commands, parser API, type mappings, and advanced features.
- `references/patterns.md` — Proven agent design patterns: memory, API wrappers, structured output, browser automation, instruction writing, and more. Read this when designing an agent's tools and instructions.
- `references/skills.md` — Skills system: creating skills, SKILL.md format, validation rules, discovery API, progressive disclosure, and the activation protocol.
- `references/voice-mode.md` — Voice/realtime mode: YAML configuration, backend types, WebSocket API, streaming events, audio storage, and instruction tips for spoken output.
