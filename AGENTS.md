# AGENTS.md

Applies to every session working in this repository. Recorded 2026-10-12.

This repo *is* the visual-grilling plugin: the skill, the round server, the Stop hook and
the doctor. A change here reaches every session that installs it, so the checks below are
the work, not a formality.

## Before you change anything

- Run the checks and see them pass first: `python tests/test-isolation.py`. They drive the
  real `serve.py` and `stop-hook.py`, so a break in either shows up here.
- `python bin/visual-grilling.py doctor` reads the installed toolkit and the armed rounds on
  this machine. Run it after a change that touches the hook, the server or the protocol.
- Read `skills/visual-grilling/SKILL.md` before touching the template: it is what an agent
  actually follows, and the template's comments say which fault each guard came from.

## Rules that hold here

- **The protocol constant is a contract.** `PROTOCOL` in `template/serve.py` and in
  `hooks-handlers/stop-hook.py` must move together, and a bump says what changed. The doctor
  fails when they disagree, and a round records the protocol it was armed under.
- **`answers.json` is never deleted by delivery.** The hook retires `round.json` and its own
  pointer; the answers stay for the agent to reconcile from. A change that deletes answers
  re-creates the bug this plugin exists to fix.
- **A round is only touched by the session that can prove it armed it.** Ownership is the
  recorded owner key, and a foreign round is left exactly as found.
- **The server is never copied.** It is run from where it is installed with `--dir`, so one
  copy serves every round and nothing goes stale.
- **Manifests are validated, not assumed:** `claude plugin validate <path> --strict` for
  both `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`.
- **Every change updates the Markdown it invalidates** — the README, the skill, the harness
  handoff — in the same change.

## Layout

`skills/visual-grilling/` the skill and its page template; `hooks/hooks.json` the
registration; `hooks-handlers/` the hook; `bin/` the doctor; `codex/` what Codex reads;
`tests/` the checks.
