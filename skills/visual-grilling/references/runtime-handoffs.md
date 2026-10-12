Applies to visual-grilling rounds run in Claude Code or Codex Desktop; recorded 2026-10-12.
Paths beginning with template/ are relative to the visual-grilling skill directory; page.html and answers.json are relative to the active scratch directory.

# Runtime handoffs

Use the instructions for the active harness. The shared server takes a loopback port of its own — assigned by the OS, so two rounds cannot share one — serves the page carrying that round's token, saves one submission in answers.json, prints it, and exits; a submission from a page this round did not serve is refused, so a stale tab cannot answer a decision it never showed. The server is run from the plugin and told where the round is, so nothing is copied and nothing goes stale. For each later round, replace the page in the same scratch directory, restart the server for it, and reload the existing review tab at the URL recorded in url.txt; arming a round removes the previous answers.json.

## Claude Code

Use the Stop hook the plugin installed. Installing the plugin registered `hooks/hooks.json`'s Stop hook, so this harness needs no wiring of its own; `python bin/visual-grilling.py doctor` says whether it is registered and whether an older hook from `~/.claude/settings.json` still points at this toolkit as well. Run the copied page's round like this, `${CLAUDE_PLUGIN_ROOT}` being the plugin's own directory in this harness:

    python "${CLAUDE_PLUGIN_ROOT}/skills/visual-grilling/template/serve.py" --dir "<scratch>" --harness claude

Run the server as a monitored process and retain its output. The registered Stop Hook is the automatic handoff. If it is unavailable, if the turn has already resumed without delivering the response, or if the round was armed before rounds recorded an owner (whose round.json has no owner field, and is therefore never claimed), read answers.json from the scratch directory and continue from those exact answers. Preserve the hook implementation and its registration when adding support for another harness.

## Codex Desktop

Codex Desktop does not use the Claude Code Stop Hook for this workflow. Leave that hook and its Claude registration untouched. Use a fresh scratch directory that is not holding an armed Claude round. Start the copied server with python serve.py --harness codex as a monitored foreground tool session; this mode does not create round.json and arms no hook, so nothing delivers for it and the answers are read from the file. Retain the session ID, scratch path, and URL. Open the URL in the Codex browser panel when available; otherwise provide the loopback link.

Keep the turn active by polling the server session in intervals of 30 seconds or less while the reader uses the page. Let new user input interrupt a poll and do not send progress messages when nothing changed. When the server prints ANSWERS ARRIVED, read and reconcile every selected value and free-text answer from the output or answers.json. If the turn has already ended, a message such as “submitted” is enough to resume collection: read the saved file and never ask the reader to re-enter their choices. A browser submission by itself does not start a Codex turn.
