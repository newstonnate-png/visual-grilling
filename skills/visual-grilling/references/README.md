# References

Copies of the artifact skills bundled in the Claude Code CLI, kept beside `visual-grilling` so its pages
inherit real design substance instead of invented rules. Read the one whose subject the page is.

**They are not skills.** Nothing here is loaded or invoked; `SKILL.md` one level up is the only live skill
in this folder.

## Where each came from

| File | Source |
| --- | --- |
| `artifact-components.md` | extracted byte-exact from `bin\claude.exe` (offset 257801605) |
| `artifact-diagramming.md` | extracted byte-exact from `bin\claude.exe` (offset 257854210) |
| `artifact-data-table.md` | extracted byte-exact from `bin\claude.exe` (offset 257858268) |
| `artifact-explainer.md` | extracted byte-exact from `bin\claude.exe` (offset 257867969) |
| `artifact-report.md` | extracted byte-exact from `bin\claude.exe` (offset 257880488) |
| `artifact-design.md` | transcribed from the text the skill delivered into a session on 2026-10-11 — faithful, but not verified byte-exact |

`artifact-capabilities` is referenced by several of these and does not exist in this build: the string is in
the binary, there is no skill body, and invoking it returns `Unknown skill`.

## What does not apply here

These were written for pages the claude.ai Artifact tool publishes. Every instruction below is dead in this
environment, and following one wastes the turn:

- **The companion files.** Four skills open with "read `template.html` from this skill's base directory", and
  `artifact-components` names `decision/skeleton.html`, `theme-script.html`, `decisions-script.html`,
  `component.css` and `tokens.css`. Extraction recovered the `SKILL.md` text only; those sibling files were
  not pulled out, so there is no file behind any of those steps.
- **The publish machinery.** The publish verifier and its blessed script hashes, `capabilities`,
  `read_page_data`, the ws-decisions island, `ArtifactCheck` previews, `ArtifactData` and the `db`
  capability, the `icon` parameter, the gallery, and the auto-update that reaches open viewers.
- **The frame's limits.** The CDN/CSP allowlist, the 16MB ceiling, the blocks on popups, downloads, print and
  device APIs, and the rule against offering a file through a link. A page written to a local file and opened
  in a browser is under none of them — a local page may load any stylesheet, print, and offer a real download.

## What carries over

The design substance, and it is most of the text: layout, typographic hierarchy, the token/theme structure,
colour, contrast, sparse-vs-dense choices, chart scale, table and data rules, prose and copy rules, the
anti-templated-design list, and all of `artifact-diagramming`.

## Corrections made to these copies

**First pass — four instructions asserted something untrue for a page written to a local file,** and were rewritten:

- `artifact-design.md`, `artifact-data-table.md`, `artifact-explainer.md`, `artifact-report.md` — each closed
  with a note that the page is a body fragment, because "the Artifact tool adds its own skeleton at publish
  time". Nothing adds a skeleton here, so a page written that way lands in quirks mode with no viewport.
  Those notes now state the wrapper to write instead.
- `artifact-explainer.md` — "give every SVG a fixed `viewBox` and no width/height attributes — the template
  scales it". With no template, an SVG given neither collapses; the rule now names the CSS that scales it.

**Second pass — the harmful layer removed from `artifact-design.md`.** Four passages described the publish
platform's constraints as rules a page must obey. Following them would have cost a local page real capability,
so each now states what holds locally: the CDN/CSP allowlist, the frame limits that made downloads, `mailto:`
and print dead, the 16 MB ceiling, and the `icon` parameter, which is gone with nothing put in its place.
Three frame rules survived because they hold in an ordinary browser too — forms submit normally, a clipboard
write needs the click handler with a select fallback, and device APIs and audio need a gesture.

Everything else is left exactly as shipped, including the inert instructions that only describe machinery —
verifier hashes, `read_page_data`, `ArtifactCheck`, the `capabilities` and `db` path, the `template.html`
pointers whose companion files were never extracted. The point of a reference is to preserve the original, and
the stamp at the top of each file flags the rest.
