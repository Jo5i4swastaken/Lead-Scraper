# Skills System

Skills are modular instruction bundles that extend an agent's capabilities without changing its code or tools. They use progressive disclosure — the agent sees a compact index of available skills and only loads the full instructions when a skill is relevant.

## SKILL.md Format

Every skill is a directory containing a `SKILL.md` file with YAML frontmatter and a markdown body:

```markdown
---
name: my-skill
description: What this skill does and when it should activate.
---

# My Skill

Full instructions here. The agent reads this when it activates the skill.
```

The file must be named `SKILL.md` (uppercase preferred) or `skill.md` (fallback).

### Frontmatter fields

| Field | Type | Required | Max Length | Description |
|-------|------|----------|-----------|-------------|
| `name` | str | Yes | 64 | Skill identifier. Must match the directory name exactly. |
| `description` | str | Yes | 1024 | What the skill does and when to trigger it. This is what the agent sees in the index. |
| `license` | str | No | — | License identifier (e.g., "MIT") |
| `compatibility` | str | No | 500 | Compatibility notes |
| `allowed-tools` | str | No | — | Tools this skill is allowed to use |
| `metadata` | dict | No | — | Custom key-value pairs (all values are stringified) |

No other fields are allowed in the frontmatter — extra fields cause validation failure.

### Name validation rules

- Lowercase only (normalized via NFKC)
- Only alphanumeric characters and hyphens (`a-z`, `0-9`, `-`)
- Cannot start or end with a hyphen
- No consecutive hyphens (`--`)
- Max 64 characters
- Must exactly match the containing directory name

### Description guidelines

The description is the primary trigger for skill activation. Write it to clearly convey:
- What the skill does
- When it should be used
- Key terms that would appear in a matching user request

Good: `"Create, read, edit, and manipulate Word documents (.docx files). Use when the user mentions .docx, Word doc, or wants formatted document output."`

Bad: `"Handles documents."`

## Directory Structure

```
my-skill/
├── SKILL.md               # Required — metadata + instructions
├── references/            # Optional — deep documentation
│   ├── api-schema.md
│   └── variants.md
├── scripts/               # Optional — deterministic helper scripts
│   ├── validate.py
│   └── pack.sh
└── assets/                # Optional — templates, boilerplate
    ├── starter-template.docx
    └── brand-colors.json
```

The `references/`, `scripts/`, and `assets/` subdirectories support progressive disclosure — the agent only reads them when the current subtask needs them.

## Progressive Disclosure

Skills are designed to minimize context usage through three loading levels:

1. **Index** (always visible): Just `name` + `description` in the available skills block
2. **SKILL.md body** (loaded on activation): Full instructions, steps, rules
3. **Bundled resources** (loaded on demand): References, scripts, assets

This means an agent with 50 available skills only uses context for the ones relevant to the current task.

### SKILL.md body structure recommendations

- Start with a quick reference table (Task → Approach)
- Numbered golden-path steps for the common case
- Pitfalls and rules as a bulleted list
- Pointers to `references/` for edge cases and deep documentation

## Discovery API

### Core functions

```python
from omniagents.core.skills import (
    build_available_skills_block,  # High-level: discover → validate → merge → generate prompt
    discover_skill_dirs,           # Find skill directories in roots
    merge_skill_dirs,              # Deduplicate by name (first wins)
    to_prompt,                     # Generate XML from skill dirs
    validate,                      # Validate a single skill directory
    read_properties,               # Parse SKILL.md into SkillProperties
)
```

### build_available_skills_block

The main entry point. Takes a list of root directories, discovers all valid skills, and returns an XML string ready for template injection:

```python
from pathlib import Path
from omniagents.core.skills import build_available_skills_block

skill_roots = [
    Path("./skills"),              # Local project skills (higher priority)
    Path("~/.config/myapp/skills"), # Global shared skills
]

xml_block = build_available_skills_block(skill_roots)
```

### Discovery logic

For each root directory:
1. If the root itself contains `SKILL.md`, it's treated as a skill
2. Each direct child directory containing `SKILL.md` is treated as a skill
3. Discovery does **not** recurse deeper than one level below each root

### Merging and precedence

When the same skill name appears in multiple roots:
- The **first one encountered wins** (earlier roots have priority)
- Put local/project-specific skills before global ones in the roots list
- Later duplicates are silently skipped

### Validation

Skills that fail validation are silently excluded from the generated block:

```python
from omniagents.core.skills import validate

errors = validate(Path("./skills/my-skill"))
if errors:
    print(f"Validation failed: {errors}")
# errors is a list[str] — empty means valid
```

Common validation failures:
- Missing `SKILL.md`
- Missing required fields (`name`, `description`)
- Extra fields in frontmatter
- Name doesn't match directory name
- Name contains invalid characters

## Generated XML Format

`build_available_skills_block` produces XML like:

```xml
<available_skills>
<skill>
<name>code-review</name>
<description>Review code for bugs, style issues, and improvement opportunities.</description>
<location>/path/to/skills/code-review/SKILL.md</location>
</skill>
<skill>
<name>testing</name>
<description>Write and run tests for Python projects using pytest.</description>
<location>/path/to/skills/testing/SKILL.md</location>
</skill>
</available_skills>
```

Names and descriptions are HTML-escaped. If no valid skills are found, the block is `<available_skills>\n</available_skills>`.

## Wiring Skills into an Agent

Skills are injected into agent instructions via a context factory and Jinja2 templates.

### Complete example

**Directory layout:**
```
my-agent/
├── agent.yml
├── instructions.md
├── context.py
└── skills/
    ├── code-review/
    │   └── SKILL.md
    └── testing/
        ├── SKILL.md
        └── references/
            └── pytest-patterns.md
```

**agent.yml:**
```yaml
name: Dev Assistant
model: gpt-5.2
instructions_file: instructions.md
context: build_dev_context
tools:
  - read_file
  - write_file
  - edit_file
  - execute_bash
  - glob_files
  - grep_files
```

**context.py:**
```python
from pathlib import Path
from omniagents.core.context.decorator import context_factory
from omniagents.core.skills import build_available_skills_block

@context_factory
def build_dev_context(variables):
    """Build context with skill discovery."""
    agent_dir = Path(__file__).parent
    skill_roots = [agent_dir / "skills"]

    # Add global skills directory if it exists
    global_skills = Path.home() / ".config" / "myapp" / "skills"
    if global_skills.is_dir():
        skill_roots.append(global_skills)

    return {
        "available_skills_block": build_available_skills_block(skill_roots),
    }
```

**instructions.md:**
```markdown
{{ available_skills_block }}

You are a development assistant with access to coding tools.

## Skills Protocol

At the start of each new task, scan the available skills index.
If one or more skills are relevant:

1. Read each selected skill's SKILL.md (use its location path).
2. Follow the skill's progressive-disclosure guidance — only load
   references, assets, or scripts when the current subtask needs them.
3. Do not assume the contents of SKILL.md without reading it.

Skills may require other skills. When a skill references another,
treat it as a dependency and activate that skill too.

When multiple skills conflict, resolve at the most specific scope.
If two skills impose incompatible requirements, ask the user which to prioritize.
```

## Skills Activation Protocol

The activation protocol should be included in the agent's instructions. Key principles:

1. **Scan on each task** — Check the skills index when the user's goal changes
2. **Read before using** — Always read the full SKILL.md before acting on it
3. **Progressive loading** — Only load references/scripts/assets when needed
4. **Dependency chaining** — If skill A requires skill B, activate both
5. **Conflict resolution** — Specific-scope skills win; ask the user if ambiguous
6. **Report activation** — Briefly state which skills were activated and why

## Writing Effective Skills

### The description is the trigger

The `description` field is the only thing the agent sees before activation. It must be specific enough to trigger on the right tasks and not on the wrong ones.

### Keep SKILL.md actionable

The body should be instructions the agent can follow, not documentation for humans. Use imperative language ("Do X", "Check Y") not explanatory prose.

### Use progressive disclosure

Put the common path in SKILL.md. Put edge cases, detailed schemas, and variant approaches in `references/`. The agent will only load what it needs.

### Test skills in isolation

Before wiring a skill into an agent, verify:
1. The frontmatter passes validation
2. The instructions are clear and actionable
3. Any referenced files exist at the expected paths
