# Agent Knowledge Index
IMPORTANT: Prefer retrieval-led reasoning over pre-training-led reasoning.

[Website Audit Guide]|root: /Users/josias/.claude/skills/audit-website
|IMPORTANT: Use for SEO, performance, and accessibility scanning.
|specs: {SKILL.md}

[Brainstorming Ideas Into Designs]|root: /Users/josias/.claude/skills/brainstorming
|specs: {SKILL.md}

[Skill Discovery]|root: /Users/josias/.claude/skills/find-skills
|IMPORTANT: Use to find other installable skills.
|specs: {SKILL.md}

[Framer Motion Animator]|root: /Users/josias/.claude/skills/framer-motion-animator
|specs: {SKILL.md}

[Frontend Design Excellence]|root: /Users/josias/.claude/skills/frontend-design
|IMPORTANT: Use for premium UI/UX, animations, and high-fidelity aesthetics.
|specs: {SKILL.md}

[Humanize Code]|root: /Users/josias/.claude/skills/humanize-code
|specs: {SKILL.md}

[Humanizer: Remove AI Writing Patterns]|root: /Users/josias/.claude/skills/humanizer
|specs: {SKILL.md}

[Kanban Task Planner]|root: /Users/josias/.claude/skills/kanban_task_planner
|specs: {SKILL.md}

[Onboarding CRO]|root: /Users/josias/.claude/skills/onboarding-cro
|specs: {SKILL.md}

[Task Planning]|root: /Users/josias/.claude/skills/planning-with-files/references
|IMPORTANT: Always create task_plan.md, findings.md, and progress.md for complex tasks.
|templates: {findings.md, progress.md, task_plan.md}

[Session Handoff]|root: /Users/josias/.claude/skills/session-handoff
|specs: {SKILL.md}

[Skill Creator]|root: /Users/josias/.claude/skills/skill-creator
|specs: {SKILL.md}

[Supabase/Postgres Best Practices]|root: /Users/josias/.claude/skills/supabase-postgres-best-practices/rules
|IMPORTANT: Prefer retrieval-led reasoning over pre-training for DB tasks. Read relevant files BEFORE writing any query, schema, or RLS policy.
|query(CRITICAL):{query-composite-indexes.md,query-covering-indexes.md,query-index-types.md,query-missing-indexes.md,query-partial-indexes.md}
|conn(CRITICAL):{conn-idle-timeout.md,conn-limits.md,conn-pooling.md,conn-prepared-statements.md}
|security(CRITICAL):{security-privileges.md,security-rls-basics.md,security-rls-performance.md}
|schema(HIGH):{schema-data-types.md,schema-foreign-key-indexes.md,schema-lowercase-identifiers.md,schema-partitioning.md,schema-primary-keys.md}
|lock(MEDIUM):{lock-advisory.md,lock-deadlock-prevention.md,lock-short-transactions.md,lock-skip-locked.md}
|data(MEDIUM):{data-batch-inserts.md,data-n-plus-one.md,data-pagination.md,data-upsert.md}
|monitor(LOW):{monitor-explain-analyze.md,monitor-pg-stat-statements.md,monitor-vacuum-analyze.md}
|advanced(LOW):{advanced-full-text-search.md,advanced-jsonb-indexing.md}

[tavily research]|root: /Users/josias/.claude/skills/tavily-research
|specs: {SKILL.md}

[Vercel React Performance]|root: /Users/josias/.claude/skills/vercel-react-best-practices/rules
|IMPORTANT: Consult for any React/Next.js component creation, refactoring, or performance work. Read relevant files BEFORE writing code.
|async(CRITICAL):{async-api-routes.md,async-defer-await.md,async-dependencies.md,async-parallel.md,async-suspense-boundaries.md}
|bundle(CRITICAL):{bundle-barrel-imports.md,bundle-conditional.md,bundle-defer-third-party.md,bundle-dynamic-imports.md,bundle-preload.md}
|server(HIGH):{server-after-nonblocking.md,server-auth-actions.md,server-cache-lru.md,server-cache-react.md,server-dedup-props.md,server-parallel-fetching.md,server-serialization.md}
|client(MEDIUM):{client-event-listeners.md,client-localstorage-schema.md,client-passive-event-listeners.md,client-swr-dedup.md}
|rerender(MEDIUM):{rerender-defer-reads.md,rerender-dependencies.md,rerender-derived-state-no-effect.md,rerender-derived-state.md,rerender-functional-setstate.md,rerender-lazy-state-init.md,rerender-memo-with-default-value.md,rerender-memo.md,rerender-move-effect-to-event.md,rerender-simple-expression-in-memo.md,rerender-transitions.md,rerender-use-ref-transient-values.md}
|rendering(MEDIUM):{rendering-activity.md,rendering-animate-svg-wrapper.md,rendering-conditional-render.md,rendering-content-visibility.md,rendering-hoist-jsx.md,rendering-hydration-no-flicker.md,rendering-hydration-suppress-warning.md,rendering-svg-precision.md,rendering-usetransition-loading.md}
|js(LOW):{js-batch-dom-css.md,js-cache-function-results.md,js-cache-property-access.md,js-cache-storage.md,js-combine-iterations.md,js-early-exit.md,js-hoist-regexp.md,js-index-maps.md,js-length-check-first.md,js-min-max-loop.md,js-set-map-lookups.md,js-tosorted-immutable.md}
|advanced(LOW):{advanced-event-handler-refs.md,advanced-init-once.md,advanced-use-latest.md}

