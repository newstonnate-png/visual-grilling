"""Serve one round of visual grilling and collect the answers.

Run it as a monitored job. It serves the round's page on loopback and collects exactly
one submission: the first line it prints is the URL, and the last carries the answers, so
nothing needs checking afterwards.

Where the round lives. `--dir` names the round's directory — its page, its `answers.json`,
its `url.txt` and (under Claude Code) its `round.json`. It defaults to this file's own
directory, which is what a copied layout wants; an installed plugin passes the round's
scratch directory instead, so one copy of this server serves every round and no copy of
it is ever stale. `--page` overrides the page's path; the default is `page.html` in that
directory.

Arms the round for the session that started it: `round.json` records the owner and the
Stop hook is pointed at this directory under that session's key, so a second session's
round is a second pointer and neither hook can reach the other's. The key is
`CLAUDE_CODE_SESSION_ID` when the harness sets it, the working directory otherwise;
`stop-hook.py` beside this file derives the same key and says why it is written out twice.

A tab that outlives its round cannot post into the next one: every served page carries
this round's token, and a submission without it is refused with a page saying so. The OS
assigns the loopback port, so two rounds cannot share an origin however many are live.
"""

import argparse
import hashlib
import http.server
import json
import os
import secrets
import sys
import time
import urllib.parse
import webbrowser

# Bump when a round's contract changes, and say what changed. Round state is now named by
# --dir rather than read from beside the server, so this file is run from where it is
# installed and a round never carries a copy of it. Protocol 3.
PROTOCOL = 3

HERE = os.path.dirname(os.path.abspath(__file__))

# One round, one token, injected into the page as it is served and required back on
# submission. A tab left open from an earlier round keeps its origin, so a later round
# could be handed a stale page's answers, which nothing about the request would otherwise
# reveal. The token is what makes those answers refusable instead of silently accepted.
ROUND_TOKEN = secrets.token_hex(8)

TOKEN_FIELD = "round_token"

DONE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Answers sent</title>
<style>
  body{margin:0;min-height:100vh;display:grid;place-items:center;background:#111820;color:#e6ecf2;
       font:16px/1.6 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;padding:2rem;text-align:center}
  h1{font-size:1.3rem;margin:0 0 .5rem}
  p{margin:0;color:#93a2b1}
</style></head>
<body><div><h1>Answers sent</h1><p>You can close this tab.</p></div></body></html>
"""


STALE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>This page is from an earlier round</title>
<style>
  body{margin:0;min-height:100vh;display:grid;place-items:center;background:#111820;color:#e6ecf2;
       font:16px/1.6 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;padding:2rem;text-align:center}
  h1{font-size:1.3rem;margin:0 0 .5rem}
  p{margin:.4rem 0;color:#93a2b1}
  a{color:#7fc0a8}
</style></head>
<body><div><h1>These answers were not sent</h1>
<p>This tab is a page from an earlier round, and the round now running is a different one.</p>
<p>Your answers would have gone to the wrong decision. Open <a href="%s">%s</a> and answer there.</p>
</div></body></html>
"""


def served_page(page_file):
    """The page with this round's token in it, so a submission can be traced to a round."""
    with open(page_file, encoding="utf-8") as handle:
        body = handle.read()
    field = '<input type="hidden" name="%s" value="%s">' % (TOKEN_FIELD, ROUND_TOKEN)
    start = body.find("<form")
    if start != -1:
        end = body.find(">", start)
        if end != -1:
            body = body[:end + 1] + field + body[end + 1:]
    # The round id in the tab title, so two tabs on one machine are told apart by eye.
    return body.replace("<title>", "<title>[%s] " % ROUND_TOKEN[:6], 1)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # the transcript is not the place for request noise

    def _html(self, code, body):
        raw = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path.startswith("/favicon"):
            self.send_response(204)
            self.end_headers()
            return
        # Read on every request, so an edit to the page shows on a reload.
        self._html(200, served_page(self.server.page_file))

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8")
        fields = urllib.parse.parse_qs(raw, keep_blank_values=True)
        sent = (fields.pop(TOKEN_FIELD, [""]) or [""])[0]
        if sent != ROUND_TOKEN:
            # A submission from a page this round did not serve. Refused, not accepted,
            # and the round stays open so the reader can answer the page that is live.
            self._html(409, STALE % (self.server.url, self.server.url))
            print("REFUSED a submission from another round (token %r)" % sent[:12], flush=True)
            return
        # A checklist posts one name repeatedly: join, never take the first.
        answers = {k: ", ".join(v) for k, v in fields.items() if v and any(v)}
        with open(self.server.answers, "w", encoding="utf-8") as handle:
            json.dump({"answers": answers, "submittedAt": time.time()}, handle, indent=2)
        self._html(200, DONE)
        self.server.collected = answers


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    collected = None
    url = ""
    round_dir = HERE
    page_file = os.path.join(HERE, "page.html")
    answers = os.path.join(HERE, "answers.json")
    # Windows sets SO_REUSEADDR by default here, and it lets a second server bind a port
    # another process is already serving on: two live rounds, one origin, connections
    # split between them by luck, and each round's page served from whichever socket the
    # browser happened to reach. The OS assigns the port (see main) and a round may not
    # share one, so the conflict is removed rather than detected.
    allow_reuse_address = False
    allow_reuse_port = False


def temp_root():
    return os.environ.get("TEMP") or os.environ.get("TMP") or "."


def session_key():
    """The key this round is armed under: one session, one pointer.

    Mirrors `stop-hook.py`'s derivation. The session id when the harness gives it
    (Claude Code sets CLAUDE_CODE_SESSION_ID for the shell this runs in and for the
    hook), the working directory otherwise — which two sessions in one project would
    share, so the id is asked for first and the directory is only the fallback.
    """
    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if session_id and session_id.strip():
        return "session:" + session_id.strip()
    return "cwd:" + os.path.normcase(os.path.abspath(os.getcwd()))


def pointer_path(key):
    """Where the pointer for one session's armed round lives. Mirrors stop-hook.py."""
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return os.path.join(temp_root(), "visual-grilling", "live", digest + ".txt")


def main():
    parser = argparse.ArgumentParser(description="Serve one visual-grilling round.")
    parser.add_argument(
        "--harness", choices=("claude", "codex"), default="claude",
        help="Select Claude Stop Hook handoff or Codex file/session handoff.",
    )
    parser.add_argument(
        "--dir", default=HERE,
        help="The round's directory: its page, answers.json, url.txt and round.json. "
             "Defaults to this file's own directory.",
    )
    parser.add_argument(
        "--page", default=None,
        help="The page to serve. Defaults to page.html in the round's directory.",
    )
    parser.add_argument(
        "--no-browser", action="store_true",
        help="Do not open a browser tab: for a check that drives the page itself.",
    )
    args = parser.parse_args()

    round_dir = os.path.abspath(args.dir)
    os.makedirs(round_dir, exist_ok=True)
    page_file = os.path.abspath(args.page) if args.page else os.path.join(round_dir, "page.html")
    answers = os.path.join(round_dir, "answers.json")
    url_file = os.path.join(round_dir, "url.txt")
    if not os.path.exists(page_file):
        sys.exit("no page to serve at %s — write the round's page first" % page_file)

    # The OS picks the port, and it picks a free one: a fixed range is what let a second
    # round land on a live round's port, and no scan can be trusted on Windows, where a
    # bind to a busy port succeeds. Bound before the browser opens, or the first load
    # races the listener.
    try:
        server = Server(("127.0.0.1", 0), Handler)
    except OSError as exc:
        sys.exit("no loopback port could be bound: %s" % exc)
    url = "http://127.0.0.1:%d/" % server.server_address[1]
    server.url = url
    server.round_dir = round_dir
    server.page_file = page_file
    server.answers = answers
    with open(url_file, "w", encoding="utf-8") as handle:
        handle.write(url + "\n")

    if args.harness == "claude":
        # Arm the Claude Stop Hook under THIS session's key. Codex mode leaves these
        # markers and every pointer untouched.
        # The previous round's submission is not this round's: remove it, so an old
        # answers.json cannot be read as an answer to the page now being served.
        try:
            os.remove(answers)
        except OSError:
            pass
        owner = session_key()
        with open(os.path.join(round_dir, "round.json"), "w", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid(), "startedAt": time.time(), "url": url, "owner": owner,
                       "protocol": PROTOCOL,
                       "sessionId": os.environ.get("CLAUDE_CODE_SESSION_ID", ""),
                       "cwd": os.getcwd()}, handle, indent=2)
        pointer = pointer_path(owner)
        os.makedirs(os.path.dirname(pointer), exist_ok=True)
        with open(pointer, "w", encoding="utf-8") as handle:
            handle.write(round_dir + "\n")
    print("serving %s" % url, flush=True)
    print("round %s" % ROUND_TOKEN[:6], flush=True)   # the id the live tab shows in its title
    print("protocol %d" % PROTOCOL, flush=True)
    if not args.no_browser:
        webbrowser.open(url)

    # One submission, then stop. The loop is not `handle_request()` once: a
    # browser asks for /favicon.ico too, and a single request would be spent on
    # that and exit before anyone answered.
    while server.collected is None:
        server.handle_request()

    server.server_close()
    print("ANSWERS ARRIVED: " + json.dumps(server.collected, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
