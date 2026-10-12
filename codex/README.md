# Codex — what this toolkit installs, and what Codex does and does not support

Recorded 2026-10-12, against the Codex documentation as it stands at `codex-cli 0.162.1`.
Every claim below rests on a doc page named beside it; anything the docs do not state is
marked as unknown rather than filled in.

## Install

```
python bin/visual-grilling.py install --harness codex
```

That merges a `Stop` hook into `~/.codex/hooks.json` — merging, never replacing, because a
Codex user usually has hooks of their own there. Existing entries are preserved; a group
that already names this hook is replaced, so running it twice leaves one entry.

Then **approve the hook in Codex**: run `/hooks` and trust it. This is not optional —
"Non-managed hooks must be reviewed and trusted before they run", and "Codex records trust
against the hook's current hash, so new or changed hooks are marked for review and skipped
until trusted" (`https://learn.chatgpt.com/docs/hooks.md`). Any edit to
`hooks-handlers/stop-hook.py` therefore needs approving again.

## Why the command is an absolute path

Codex's hook handler takes `command` and an optional `commandWindows`; it has **no `args`
and no plugin-root variable** (compare Claude Code's `${CLAUDE_PLUGIN_ROOT}`), so the
registered command names the hook file by absolute path. On this machine that is
`C:\Dev Work\CC Skills\visual-grilling\hooks-handlers\stop-hook.py`. Codex reads
`~/.codex/hooks.json`, `~/.codex/config.toml`, a trusted project's `.codex/hooks.json`, and
hooks bundled in an installed plugin (`hooks/hooks.json`) — the paths and shape are
documented at the hooks page above.

## Why a Stop hook is the right mechanism

Codex has two turn-end mechanisms and only one of them can hand answers back:

| Mechanism | Documented behaviour |
|---|---|
| `notify` | Fires a program on `agent-turn-complete`. Described only as side-channel alerting; nothing is documented about its output or exit code influencing the turn. No feedback path. |
| **`Stop` hook** | "For this event, `decision: "block"` doesn't reject the turn. Instead, it tells Codex to continue and automatically creates a new continuation prompt that acts as a new user prompt, using your `reason` as that prompt text." |

That is exactly what this toolkit needs, and it is the same JSON the hook already prints for
Claude Code — `{"decision": "block", "reason": ...}` — so one hook file serves both
harnesses. Codex's input on stdin carries `session_id`, `transcript_path`, `cwd` and
`stop_hook_active`, the same field names Claude Code uses, so the hook's per-session key
derivation works unchanged. `stop_hook_active`, which both harnesses set when a stop was
already continued, is the documented loop guard.

## Skills under Codex

Codex discovers skills at `$CWD/.agents/skills`, `$REPO_ROOT/.agents/skills`,
`$HOME/.agents/skills` and `/etc/codex/skills`, and a skill is a directory with a `SKILL.md`
carrying `name` and `description` (`https://learn.chatgpt.com/docs/build-skills.md`) — the
same file this toolkit already ships, so `skills/visual-grilling/` is consumable as-is.

To make the machine's `~/.agents/skills/visual-grilling` follow this repo rather than be a
second copy that drifts:

```
python bin/visual-grilling.py install --harness codex --link-skills
```

It writes a pointer `SKILL.md` there. Do this only once you want this repo to be the single
source of truth for the skill: it replaces whatever stood at that path.

## Plugin packaging

Codex's installable unit is also called a **plugin** — "a first-class concept, not a
metaphor": "Plugins bundle capabilities into reusable workflows in ChatGPT and Codex. They
can include skills and MCP servers" (`https://learn.chatgpt.com/docs/plugins.md`). This repo
carries the pieces for that route too:

- `plugin.json` at the root — the Agent Plugins manifest
  (`https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`); OpenAI-specific settings
  would go under `extensions.com.openai` (`https://developers.openai.com/plugins/build/plugins.md`).
- `.agents/plugins/marketplace.json` — Codex's marketplace file. Codex also reads "a
  legacy-compatible marketplace at `$REPO_ROOT/.claude-plugin/marketplace.json`", which this
  repo already has for Claude Code.

The CLI install above is the recommended path on Windows because it is verifiable here and
because plugin-bundled hooks still require a manual desktop install and a trust review. The
packaging is there for the day that is not true.

## What Codex cannot do here

- Plugin lifecycle hooks are documented as "supported for plugins installed manually in
  Codex desktop", and such plugins "aren't eligible for the public plugin directory".
- "Plugins aren't available in the IDE extension."
- The minimum Codex version for plugins, marketplaces, skills and hooks is **not stated** in
  the documentation, so this was verified against 0.162.1 only.
- Whether an installed plugin can ship an `AGENTS.md` that Codex loads automatically is
  **not documented** — skills, MCP servers, hooks and assets are the documented parts.
