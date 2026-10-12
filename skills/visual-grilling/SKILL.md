---
name: visual-grilling
description: Draw a decision as a page the reader can see and answer on — the tree, each branch with what it costs, and a recommendation with its reasoning. Use when the reader asks to see the options visually, or when verbal framing has not settled a decision.
---

# Visual grilling

Interview the reader until you share an understanding, and show the decision as a picture rather than a paragraph. Map the subject as a decision tree: every decision branches into the decisions that hang off it. The frontier is every decision whose prerequisites have been answered — the questions you can ask now without guessing at answers you have not heard. An answer is the reader's position as it stands, and their positions change: every branch stays open to being reopened.

Ask the whole frontier in one round: number the questions, recommend an answer to each, and wait. The answers push the frontier outward, so a question that depends on another still open belongs to a later round — and back inward when an answer reopens something already taken. The interview ends with the frontier empty, every branch visited and nothing left silently assumed.

Finding facts is your job, never the reader's: look them up instead of asking. The decisions are the reader's: put each to them and wait.

## The page

Reach for a page once a round carries two or more questions. A single question, or one with no comparison in it, belongs in the reply. Serve that page from one small loopback process that also collects the answers, so the page and the endpoint share an origin and the reader never pastes. Keep one page for the whole interview and update it as the frontier moves, so the reader holds it open and watches it change. Its source is a scratch file you name once and remove when the interview ends.

A question carries a heading, its options, and beside each option what taking it costs. The recommended option comes first, marked as a recommendation, with the reasoning next to it. A free-text field sits beside the options on every question, whatever shape they take.

## The template

template/page.html sits beside this file, carrying the faults these rounds cost: an inert Enter beside a working Ctrl+Enter, labels wired to their own field, repeated fields joined rather than collapsed to the first, a confirmation naming what was sent before the page closes, and colours declared in all three theme scopes. Copy it into a named scratch directory and replace the sample question with the round's own — the round owns that page. Guard the submission, because a one-shot form gives no second chance: Enter inside a free-text field returns a newline or nothing, never the round, so the deliberate send (Ctrl+Enter, named under the fields) sits beside the button, and the confirmation states what was sent before the page closes. The server is not copied: `template/serve.py` is run from where it is installed, told where the round lives by `--dir`, so one copy serves every round and no copy of it goes stale.

A round belongs to the session that armed it. serve.py points the Stop hook at its directory under that session's own key, and the hook acts only on a round whose recorded owner is one of its own: another session's round is never held for, delivered or deleted. The hook is `hooks-handlers/stop-hook.py`, registered by the plugin's own `hooks/hooks.json`, so installing the plugin installs the hook and there is nothing else to wire. `python bin/visual-grilling.py doctor` checks that the hook, the server and the protocol agree, and says what to fix when they do not; `tests/test-isolation.py` runs two sessions against both and pins the isolation.

## Collect the answers

Serve the page on loopback and keep its scratch directory and server session available until the round is collected. Before launching the server, read references/runtime-handoffs.md and follow the instructions for the active harness — each harness spells the plugin's own directory differently, and the file gives the command for the one in hand. The server takes a loopback port of its own — the OS assigns it, so two rounds live at once cannot share an origin — and serves the page carrying that round's token, which is also the id it puts in the tab title; its first lines are the URL, the round id and the protocol it speaks. The server writes each submission to answers.json and prints it before exiting, and arming a round removes the previous round's answers.json for you. Treat answers.json as the durable result and the server output as the quick handoff: the hook never deletes it, so it is what reconciles a round whose delivery went astray — read it in the scratch directory, where url.txt names the page to reload. Every question stays answerable by silence, so a reader who agrees with a recommendation can submit without touching it.

When anything about the round looks wrong — no hold, an answers file nobody delivered, a protocol that does not match the skill — run `python bin/visual-grilling.py doctor` from the plugin. It reads the hook, the server and the live rounds, and names the fix.

A tab that outlives its round cannot answer the next one: a submission carrying a token this round did not serve is refused, with a page naming the live URL, and nothing is written. The same page opened twice is two tabs on one round, which is fine; two rounds are never one page, and a stale tab is the case to watch for.

A round's scratch directory is left exactly where it is when the round ends, including a round whose session is gone: deleting by age is the act that caused this, so it is done by hand (Owner, 2026-10-12).

## Check the answers against each other

Read a round's answers together, and against the branches already taken, before the frontier moves: two answers that cannot both hold, or one that contradicts a decision already made, are a conflict. Surface it — both sides, one line each, in the reader's own words — and ask which one gives way. Settling it is the reader's call; a conflict you resolve silently is an answer they never gave.

A conflict also reopens a branch. When a later answer changes an earlier decision, put that branch back on the frontier, mark it open again on the page, and let the next round carry what follows from the change.

## Draw the difference

Draw what the reader is choosing between rather than the options' names: the hop one branch adds, the store the other drops, what changes if this goes the other way. Label each arrow with what crosses it. Size the drawing to what the decision turns on, and where a sentence says it faster, write the sentence.

Where the page draws inline SVG, hand-author it: size by `viewBox`, take strokes and text from `currentColor` so both themes read, hold labels to a word or three, and wrap it in a `<figure>` whose `<figcaption>` and `aria-label` state the one claim it makes.

## Match the control to the answer

- one choice from a set — a radio list
- several from a set — a checklist
- a judgement — a scale with both ends named
- an order — a list the reader arranges
- an answer outside the options — the free-text field

Where the shape is unclear, show both. Where several answers can hold at once, the control is a checklist, whether or not the reader settles on one: a single-answer control discards the rest without saying so.

The whole frontier sits on the page at once, and every question stays answerable in the round it appears in.

## Where the page cannot be written

Where the harness can serve no page, say so in one line and draw the same map as a text flow in the reply, taking the answers as typed turns.

## References

Copies of the artifact skills sit in `references/`, beside this file. Read the one whose subject the page is: `artifact-design` for palette, type and layout; `artifact-diagramming` for drawing a mechanism; `artifact-report`, `artifact-explainer` and `artifact-data-table` for those page shapes. Each carries a stamp naming the instructions that do not hold for a page written to a file; `README.md` records where they came from and what is missing from them.

## Closing

With the frontier empty the page carries the map. Ask whether it matches the reader's intent — that confirmation is what holds it, and any branch in it can still be reopened — and start on the work only once they confirm.
