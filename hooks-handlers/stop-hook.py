"""Hold the turn open until the reader answers a live round.

Registered as a Stop hook: it runs when the agent tries to end its turn. While this
session's round is armed it does not let the turn end — it waits for `answers.json` in
the live round's directory and, when it appears, blocks the stop with the answers as
the reason, which continues the turn and hands them to the agent. With no round of its
own armed it exits silently, so an ordinary stop is untouched.

One pointer per session, never one for the machine
-------------------------------------------------
`serve.py` writes a pointer to its round under a key derived from the session that
armed it, and this hook looks only under its own keys. A shared pointer is what let a
session with no round of its own be handed another session's answers: the last round
armed owned the pointer for every session on the machine.

The key is derived the same way on both sides — `CLAUDE_CODE_SESSION_ID` when the
harness sets it, the session's working directory otherwise. This hook is registered by
the plugin's own `hooks/hooks.json`, and `serve.py` is run from the plugin rather than
copied, so both are one file each and neither can be stale. A hook runs under `python -I`,
which cannot import a sibling module, so the derivation is written out in both; keep them
in step, and `tests/test-isolation.py` in the plugin goes red if they drift.

A round this session cannot prove is its own is never held for and never touched: no
answers delivered, no file deleted. That covers a round whose `round.json` carries no
`owner` — armed by a version of the toolkit that predates the per-session pointer — whose
answers stay on disk for the agent to read, which is the fallback `runtime-handoffs.md`
names. A round armed by a different protocol is delivered, with the mismatch said in the
reason rather than swallowed, since the answers are readable either way.
"""

import hashlib
import json
import os
import sys
import time

DEADLINE_SECONDS = 1800      # how long one hold may last, matched by the hook's timeout
POLL_SECONDS = 0.4
STALE_HOURS = 2              # a round older than this is a leftover, not a live reader
PROTOCOL = 3                 # the round contract this hook speaks; see serve.py


def temp_root():
    return os.environ.get("TEMP") or os.environ.get("TMP") or "."


def pointer_path(key):
    """Where the pointer for one session's armed round lives. Mirrors serve.py."""
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return os.path.join(temp_root(), "visual-grilling", "live", digest + ".txt")


def own_keys(payload):
    """Every key this session may be identified by, strongest first.

    The strongest is the session id the harness gives both this hook (in its stdin
    payload and in the environment) and the shell that starts `serve.py`. The working
    directory is the fallback for a harness that gives neither, and it identifies the
    session less precisely, so it never outranks a session id.
    """
    keys = []

    def add(key):
        if key and key not in keys:
            keys.append(key)

    add(_session_key(os.environ.get("CLAUDE_CODE_SESSION_ID")))
    add(_session_key(payload.get("session_id")))
    add(_transcript_key(payload.get("transcript_path")))
    add(_cwd_key(payload.get("cwd") or os.getcwd()))
    return keys


def _session_key(value):
    return "session:" + value.strip() if isinstance(value, str) and value.strip() else None


def _transcript_key(value):
    # A transcript file is named after its session and never shared between them.
    return "transcript:" + os.path.normcase(os.path.abspath(value)) if isinstance(value, str) and value.strip() else None


def _cwd_key(value):
    return "cwd:" + os.path.normcase(os.path.abspath(str(value)))


def read_stdin_payload():
    """The harness's JSON payload, or {} when there is none.

    A hook is handed its payload on stdin. Running this file by hand has no payload,
    and must not block waiting for one, so a terminal is skipped rather than read.
    """
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return {}
        raw = sys.stdin.read(1 << 20)
    except (OSError, ValueError):
        return {}
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def owned_round(keys):
    """This session's armed round, or None.

    A round counts as this session's only when the key its `serve.py` recorded is one
    of this session's own. Anything else — another session's round, or one armed
    before rounds carried an owner — is left exactly as it was found.
    """
    for key in keys:
        try:
            with open(pointer_path(key), encoding="utf-8") as handle:
                path = handle.read().strip()
        except OSError:
            continue
        if not path or not os.path.isdir(path):
            continue
        armed = read_json(os.path.join(path, "round.json"))
        if not armed or armed.get("owner") not in keys:
            continue
        return path, armed, key
    return None, None, None


def disarm(round_path, key=None):
    """Retire the round without destroying its answers.

    `answers.json` is the durable result the skill tells the agent to read, so it stays;
    only the arm markers go, which is what leaves later stops alone. The pointer goes with
    them: one left behind names a round that has already been collected, and the next
    reader of the pointer directory would take it for an armed round nobody is serving.
    Doing this the other way round — answers first — is how a reader's answers were
    deleted before anyone read them.
    """
    try:
        os.remove(os.path.join(round_path, "round.json"))
    except OSError:
        pass
    if key:
        try:
            os.remove(pointer_path(key))
        except OSError:
            pass


def deliver(answers, round_path, url=None, protocol=None):
    where = " The round was " + round_path + (" (page " + url + ")" if url else "") + \
            "; answers.json there is the durable copy, and url.txt beside it holds the page to reload."
    if protocol is not None and protocol != PROTOCOL:
        where += (" That round was armed by protocol %s while this hook speaks %d: the answers are "
                  "readable, but the toolkit around them has moved." % (protocol, PROTOCOL))
    print(json.dumps({
        "decision": "block",
        "reason": ("The reader answered the live grilling round. These are their answers, "
                   "as the page submitted them: " + json.dumps(answers, sort_keys=True) + "." + where +
                   " Continue the round from them — do not wait for a chat message."),
    }))
    sys.stdout.flush()


def main():
    # The reason carries the reader's own words, which are arbitrary text: a Windows
    # console codec would mangle or refuse them. JSON on stdout is UTF-8 by contract.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    payload = read_stdin_payload()
    round_path, armed, key = owned_round(own_keys(payload))
    if not round_path:
        return 0

    started = armed.get("startedAt") or 0
    if time.time() - started > STALE_HOURS * 3600:
        disarm(round_path, key)     # a leftover of our own: retire it rather than hold for it
        return 0

    answers_path = os.path.join(round_path, "answers.json")
    deadline = time.time() + DEADLINE_SECONDS
    while True:
        answers = read_json(answers_path)
        if answers:
            disarm(round_path, key)  # delivered once; later stops are left alone
            deliver(answers.get("answers", answers), round_path, armed.get("url"), armed.get("protocol"))
            return 0
        if time.time() >= deadline:
            return 0                # give up quietly; the answers stay on disk either way
        if not os.path.exists(os.path.join(round_path, "round.json")):
            return 0                # the round ended some other way
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
