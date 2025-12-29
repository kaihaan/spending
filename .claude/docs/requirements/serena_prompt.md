
### Prompt for Claude Code

You are configuring **Serena’s persistent prompts / memories** for this project.

**Important constraints:**

* `claude.md` already defines all **authoritative, non-negotiable rules** (architecture, stack, coding standards, tooling, constraints).
* You must **not restate, paraphrase, or duplicate** anything from `claude.md` in Serena’s memories.
* Serena’s memories must **never override or conflict with `claude.md`**.

**Your task:**
Configure Serena’s prompts so they capture **operational behavior and working preferences**, not project law.

Specifically, Serena memories may include:

* Preferred reasoning or problem-solving approaches
* How the user likes answers structured (brevity vs depth, examples vs theory)
* Learned workflow optimizations (e.g. debugging order, validation habits)
* Cross-project preferences that are *useful but not mandatory*

Serena memories must **not** include:

* Technology choices, architecture decisions, or “must/never” rules
* Coding standards or repo-specific policies
* Tooling constraints already enforced by `claude.md`
* Literal task prompts or verbatim instructions

**Memory style requirements:**

* Store memories as **short, generalized behavioral rules**
* Avoid task-specific or one-off details
* Prefer abstraction over exact phrasing

**Test before storing a memory:**
Ask: *“If this memory were forgotten, would the project break or violate rules?”*

* If yes → it belongs in `claude.md`, do not store it
* If no → it may be stored as a Serena prompt

Output only the proposed Serena prompts, written as concise behavioral guidance.
