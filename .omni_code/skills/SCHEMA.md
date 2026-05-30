# Skill schema — RGV Lead Scraper

A **skill** is a layer *above tools*. A tool does one thing (`request_lead_generation`,
`promote_lead_candidates`, …). A skill names a **goal** ("stage candidates for a
vertical", "promote only the no-website candidates"), pins the **exact tool sequence**
that achieves it, and encodes the **behavior rules** (filters, caps, error handling,
when to stop) so that the *same input produces the same output every time*.

Skills **compose existing tools**. They never add new tools and never widen the
agent's permissions. The two mutating tools (`request_lead_generation`,
`promote_lead_candidates`) still go through the host's per-call approval gate when a
skill calls them — a skill is an orchestration recipe, not an authority grant.

## Where skills live

```
.omni_code/skills/
├── SCHEMA.md                         # this file
├── stage-candidates-for-vertical/    # acquire: scrape one vertical in one city
│   └── SKILL.md
├── sweep-vertical-across-cities/     # acquire: one vertical across many RGV cities
│   └── SKILL.md
├── acquire-no-website-leads/         # acquire + promote (end-to-end no-website play)
│   └── SKILL.md
├── promote-no-website-candidates/    # promote: website-less staged rows
│   └── SKILL.md
├── promote-icp-candidates/           # promote: by attribute band (parametrized ICP)
│   └── SKILL.md
├── promote-selected-candidates/      # promote: specific user-named/numbered rows
│   └── SKILL.md
├── review-staged-candidates/         # read-only: browse staged rows
│   └── SKILL.md
└── preflight-check/                  # read-only: config / auth / budget health
    └── SKILL.md
```

`agents/rgv_lead_scraper/context.py` (`build_skills_context`) discovers every
direct child of `.omni_code/skills/` that contains a `SKILL.md`, validates it, and
injects the `name` + `description` index into the agent's instructions via
`{{ available_skills_block }}`. The agent reads the full `SKILL.md` only when a skill
is relevant (progressive disclosure). See
`.obra/skills/omniagents-basic/references/skills.md` for the framework mechanics.

## File format

Each skill is a directory whose name matches the skill `name`, containing a
`SKILL.md`. The file has two parts:

1. **OmniAgents frontmatter** — only `name` + `description` (and optional
   `metadata`). The validator rejects any other top-level frontmatter field, so the
   structured descriptor lives in the body, *not* the frontmatter.
2. **Body** — a single fenced ` ```yaml ` block holding the **skill descriptor**
   (the machine-readable contract below), followed by short imperative prose telling
   the agent how to execute the playbook.

```markdown
---
name: stage-candidates-for-vertical
description: One line — what it does AND when to trigger it. This is the only thing
  the agent sees before activation, so make it specific.
---

# Stage candidates for a vertical

​```yaml
# --- skill descriptor (the contract) ---
name: stage-candidates-for-vertical
...
​```

## How the agent executes this
- imperative step-by-step prose...
```

## Descriptor fields (all required)

| Field | Type | Meaning |
|-------|------|---------|
| `name` | str | Skill id. Lowercase, hyphens only, matches the directory name. |
| `description` | str | What it does + when to use it. Mirrors the frontmatter line. |
| `when_to_use` | list[str] | Concrete user phrasings / situations that should trigger this skill. Used for selection. |
| `tool_playbook` | list[step] | **Ordered** tool calls. Each step has `step`, `tool`, `args` (templates referencing skill inputs in `{{ }}`), optional `when` (conditional), and `note`. This is the deterministic recipe. |
| `success_criteria` | list[str] | Observable conditions that mean the skill succeeded. Checked against tool results, not assumed. |
| `fallback_behavior` | list[rule] | What to do when a step fails (auth, budget, empty result, partial failure). Each rule is `{ on: <condition>, do: <action> }`. |
| `stop_conditions` | list[str] | Hard stops. The agent must NOT continue past these (e.g. "never loop a second scrape", "never promote a row with a website"). |

### `tool_playbook` step shape

```yaml
tool_playbook:
  - step: 1
    tool: request_lead_generation          # must be a tool the agent already has
    args:
      city: "{{ city }}"                    # {{ }} = skill input, resolved at call time
      category: "{{ vertical }}"
      limit: "{{ min(limit, 20) }}"         # arg templates may express the cap rule
    when: always                            # or a condition string, e.g. "candidates_total > 0"
    note: "Scrapes + stages ~20, promotes top `limit`."
```

`args` values are **templates**, not literals: `{{ city }}` resolves to the skill's
`city` input. Conditionals (`when`) and inline expressions (`min(limit, 20)`) encode
behavior rules directly in the recipe so the agent does not improvise them.

## On-the-wire skill frames (consumed by the CRM UI)

When a skill runs, the transport surfaces three optional JSON-RPC notification
frames so the chat UI can group the skill's tool calls under one row. The CRM parser
(`lib/agentRpc.ts`) recognizes them and the `SkillInvocation` type
(`types.ts`) is the shape the UI's `SkillTraceRow.tsx` (P2.7 #4) consumes:

```jsonc
// skill_start  — emitted when a skill begins
{ "jsonrpc": "2.0", "method": "skill_start",
  "params": { "run_id": "...", "skill_name": "promote-no-website-candidates",
              "timestamp": "2026-05-29T18:00:00Z" } }

// tool_called / tool_result frames in between nest under the open skill

// skill_end    — emitted on success
{ "jsonrpc": "2.0", "method": "skill_end",
  "params": { "run_id": "...", "skill_name": "promote-no-website-candidates",
              "status": "complete", "timestamp": "2026-05-29T18:00:05Z" } }

// skill_error  — emitted instead of skill_end on failure
{ "jsonrpc": "2.0", "method": "skill_error",
  "params": { "run_id": "...", "skill_name": "promote-no-website-candidates",
              "error": "auth_required", "timestamp": "2026-05-29T18:00:05Z" } }
```

These frames are **optional and additive**: a tool-only trace (no skill frames)
still renders exactly as before. `skill_name` is the canonical key; `name` is
accepted as a fallback.

## How to add a new skill

1. `mkdir .omni_code/skills/<my-skill-name>` (lowercase, hyphens only).
2. Add `SKILL.md` with the frontmatter (`name` == directory name) and a `description`
   that names both *what* it does and *when* to trigger it.
3. In the body, write the ` ```yaml ` descriptor with **all** required fields. Keep
   the `tool_playbook` strictly ordered and only reference tools the agent already
   has (`request_lead_generation`, `list_lead_candidates`, `promote_lead_candidates`,
   `get_settings_summary`, `read_file`, `list_directory`).
4. Encode every behavior rule in the descriptor — caps in `args`, branches in `when`,
   guards in `stop_conditions` — so behavior is in the recipe, not improvised.
5. Add the selection hint to `agents/rgv_lead_scraper/instructions.md` under
   "Skill selection" so the agent knows when to pick it over a similar skill or raw
   tools.
6. Validate before wiring:
   ```bash
   python -c "from pathlib import Path; from omniagents.core.skills import validate; \
     print(validate(Path('.omni_code/skills/<my-skill-name>')) or 'OK')"
   ```
   An empty list / `OK` means the frontmatter passes. Then confirm discovery:
   ```bash
   python -c "from pathlib import Path; from omniagents.core.skills import \
     build_available_skills_block as b; print(b([Path('.omni_code/skills')]))"
   ```

## Determinism contract

Same skill + same input args ⇒ identical `tool_playbook` order ⇒ identical tool-call
sequence ⇒ identical filtered output set. Anything that would vary the output
(a filter, a cap, a tie-break) must be pinned in the descriptor. If a decision can't
be pinned, it belongs in `fallback_behavior` with an explicit branch — never left to
the model's discretion.
