"""Two sessions, two rounds: neither may see, deliver or delete the other's.

The bug this pins: one machine-global pointer meant the last session to arm a round owned
it for every session, so an unrelated session's Stop hook delivered that round's answers
and deleted its files. A second pinned bug sits beside it: two rounds on one port, which
Windows allowed because `http.server` sets SO_REUSEADDR, so a submission could reach a
server that never served its page. Run it after touching the server or the hook:

    python tests/test-isolation.py

It exercises the plugin's real `serve.py` and `stop-hook.py`, runs the hook the way the
registration does (`python -I`) and the server the way the skill does (`--dir`), and uses
a TEMP sandbox of its own, so it never touches a live round. Exit status 0 when isolation
holds.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                                     # the plugin root
SERVE = os.path.join(ROOT, "skills", "visual-grilling", "template", "serve.py")
HOOK = os.path.join(ROOT, "hooks-handlers", "stop-hook.py")
DOCTOR = os.path.join(ROOT, "bin", "visual-grilling.py")


def load_serve():
    spec = importlib.util.spec_from_file_location("vg_serve_under_test", SERVE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def arm(serve, sandbox, session_id, cwd, scratch, with_answers=False, owner="auto", started=None):
    """Write a round the way serve.py arms one, under `session_id`."""
    os.environ["TEMP"] = sandbox
    os.environ["TMP"] = sandbox
    os.environ["CLAUDE_CODE_SESSION_ID"] = session_id
    cwd_before = os.getcwd()
    os.chdir(cwd)
    try:
        key = serve.session_key()
        pointer = serve.pointer_path(key)
    finally:
        os.chdir(cwd_before)
    os.makedirs(scratch, exist_ok=True)
    os.makedirs(os.path.dirname(pointer), exist_ok=True)
    with open(pointer, "w", encoding="utf-8") as handle:
        handle.write(scratch + "\n")
    record = {"pid": 0, "startedAt": started or time.time(), "url": "http://127.0.0.1:0/"}
    if owner == "auto":
        record["owner"] = key
    elif owner is not None:
        record["owner"] = owner
    with open(os.path.join(scratch, "round.json"), "w", encoding="utf-8") as handle:
        json.dump(record, handle)
    if with_answers:
        with open(os.path.join(scratch, "answers.json"), "w", encoding="utf-8") as handle:
            json.dump({"answers": {"q1": session_id + "-answer"}, "submittedAt": time.time()}, handle)
    return pointer, key


def run_hook(sandbox, session_id, cwd, timeout=20):
    """Stop the way the harness stops: payload on stdin, session in the environment."""
    env = dict(os.environ, TEMP=sandbox, TMP=sandbox, CLAUDE_CODE_SESSION_ID=session_id)
    payload = json.dumps({"session_id": session_id, "cwd": cwd, "hook_event_name": "Stop"})
    done = subprocess.run([sys.executable, "-I", HOOK], input=payload, capture_output=True,
                          text=True, env=env, timeout=timeout)
    return done.returncode, done.stdout.strip()


def check(name, condition, detail=""):
    if condition:
        print("PASS  " + name)
        return True
    print("FAIL  " + name + ("  -- " + detail if detail else ""))
    return False


PAGE = ('<!DOCTYPE html><html><head><meta charset="utf-8"><title>R</title></head><body>'
        '<form method="post" action="/answers"><input type="radio" name="q1" id="a" value="A">'
        '<label for="a">A</label><button type="submit">Send</button></form></body></html>')


def start_round(sandbox, name):
    """Serve a round from the plugin, the way the skill does: (process, port, dir).

    Codex mode on purpose: it arms no hook and writes no pointer, so this drives the
    server and nothing else. Only the page is per-round — the server is run from where
    it is installed and told where the round lives.
    """
    import re

    round_dir = os.path.join(sandbox, name)
    os.makedirs(round_dir, exist_ok=True)
    with open(os.path.join(round_dir, "page.html"), "w", encoding="utf-8") as handle:
        handle.write(PAGE)
    env = dict(os.environ, TEMP=sandbox, TMP=sandbox, PYTHONUTF8="1")
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    process = subprocess.Popen([sys.executable, "-I", SERVE, "--dir", round_dir,
                                "--harness", "codex", "--no-browser"],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    first = process.stdout.readline().strip()
    # The startup contract an agent reads: the URL, the round id, and the protocol the
    # server speaks — the last is how a plugin that has moved on is noticed.
    process.startup = [first, process.stdout.readline().strip(), process.stdout.readline().strip()]
    match = re.search(r"http://127\.0\.0\.1:(\d+)/", first)
    return process, (int(match.group(1)) if match else None), round_dir


def check_two_live_rounds_get_distinct_ports(sandbox):
    """Two rounds running at once must not end up on one origin.

    The live failure: Windows sets SO_REUSEADDR for http.server, so the second round's
    bind to a port the first round was serving on *succeeded* — two url.txt files both
    saying 8477, two live servers behind one origin, and the browser reaching whichever
    socket it landed on.
    """
    processes, ports = [], []
    try:
        for name in ("port-round-a", "port-round-b"):
            process, port, _ = start_round(sandbox, name)
            processes.append(process)
            ports.append(port)
        ok = check("two live rounds serve two origins",
                   None not in ports and ports[0] != ports[1], "ports=%s" % ports)
        template_protocol = load_serve().PROTOCOL
        ok &= check("each round says which protocol its copy speaks",
                    all(("protocol %d" % template_protocol) in p.startup[-1] for p in processes),
                    "; ".join(p.startup[-1] for p in processes))
        return ok
    finally:
        for process in processes:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


def check_a_stale_tab_is_refused(sandbox):
    """A page from an earlier round must not be able to answer this one.

    The live failure this pins: a round's answers.json came back holding another round's
    questions answered, because the submission arrived from a page this round never
    served. Nothing about that request looked wrong.
    """
    import http.client
    import re
    import urllib.parse

    server, port, round_dir = start_round(sandbox, "stale-tab-round")
    try:
        if not port:
            return check("a round serves a page", False, "no port parsed from the server's output")

        def post(body):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            conn.request("POST", "/answers", urllib.parse.urlencode(body),
                         {"Content-Type": "application/x-www-form-urlencoded"})
            response = conn.getresponse()
            payload = response.read().decode("utf-8")
            conn.close()
            return response.status, payload

        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("GET", "/")
        page = conn.getresponse().read().decode("utf-8")
        conn.close()
        served = re.search(r'name="round_token" value="([0-9a-f]+)"', page)
        ok = check("the served page carries this round's token", bool(served))
        if not served:
            return ok
        token = served.group(1)
        ok &= check("the tab title names the round", "[%s]" % token[:6] in page)

        status, payload = post({"q1": "an earlier round's answer"})
        ok &= check("an untokened submission is refused", status == 409, "status=%s" % status)
        ok &= check("a refused submission writes nothing",
                    not os.path.exists(os.path.join(round_dir, "answers.json")))
        ok &= check("the refusal tells the reader where the live page is",
                    "not sent" in payload and str(port) in payload)

        status, _ = post({"q1": "this round's answer", "round_token": token})
        ok &= check("the live page's submission is accepted", status == 200, "status=%s" % status)
        stored = json.loads(open(os.path.join(round_dir, "answers.json"), encoding="utf-8").read())
        ok &= check("the stored answers are the reader's, with no token in them",
                    stored.get("answers") == {"q1": "this round's answer"}, repr(stored))
        return ok
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()


def main():
    serve = load_serve()
    sandbox = tempfile.mkdtemp(prefix="vg-isolation-")
    ok = True
    try:
        a_dir = os.path.join(sandbox, "proj-a")
        b_dir = os.path.join(sandbox, "proj-b")
        for path in (a_dir, b_dir):
            os.makedirs(path, exist_ok=True)
        a_scratch = os.path.join(sandbox, "round-a")
        b_scratch = os.path.join(sandbox, "round-b")

        # 1. B armed, A stopping: A must deliver nothing and must leave B's round alone.
        arm(serve, sandbox, "session-B", b_dir, b_scratch, with_answers=True)
        code, out = run_hook(sandbox, "session-A", a_dir)
        ok &= check("a session with no round of its own is not held", code == 0 and out == "",
                    "exit=%s output=%r" % (code, out[:200]))
        ok &= check("another session's round is left armed", os.path.exists(os.path.join(b_scratch, "round.json")))
        ok &= check("another session's answers are left on disk", os.path.exists(os.path.join(b_scratch, "answers.json")))

        # 2. Both armed in the same project directory: still no crossing.
        a_same = os.path.join(sandbox, "round-a-samecwd")
        arm(serve, sandbox, "session-A", a_dir, a_same, with_answers=True)
        code, out = run_hook(sandbox, "session-B", a_dir)
        ok &= check("two sessions in one directory do not cross",
                    "session-A-answer" not in out, "B was handed A's answers: %r" % out[:200])

        # 3. A's own round: held, delivered, and its answers survive the delivery.
        code, out = run_hook(sandbox, "session-A", a_dir)
        delivered = "session-A-answer" in out and '"decision": "block"' in out.replace("'", '"')
        ok &= check("a session's own round is delivered", code == 0 and delivered, "output=%r" % out[:200])
        ok &= check("the delivered round is disarmed", not os.path.exists(os.path.join(a_same, "round.json")))
        ok &= check("answers.json outlives the delivery", os.path.exists(os.path.join(a_same, "answers.json")))

        # 4. A round armed before rounds carried an owner: never claimed, never deleted.
        legacy = os.path.join(sandbox, "round-legacy")
        arm(serve, sandbox, "session-A", a_dir, legacy, with_answers=True, owner=None)
        code, out = run_hook(sandbox, "session-A", a_dir, timeout=10)
        ok &= check("an ownerless round is not delivered", out == "", "output=%r" % out[:200])
        ok &= check("an ownerless round is not deleted",
                    os.path.exists(os.path.join(legacy, "round.json")) and
                    os.path.exists(os.path.join(legacy, "answers.json")))

        # 5. No session id anywhere: the directory key carries the round, on both sides.
        fallback = os.path.join(sandbox, "round-fallback")
        arm(serve, sandbox, "", a_dir, fallback, with_answers=True)
        no_env = dict(os.environ, TEMP=sandbox, TMP=sandbox)
        no_env.pop("CLAUDE_CODE_SESSION_ID", None)
        payload = json.dumps({"session_id": None, "cwd": a_dir, "hook_event_name": "Stop"})
        done = subprocess.run([sys.executable, "-I", HOOK], input=payload, capture_output=True,
                              text=True, env=no_env, timeout=20)
        ok &= check("with no session id anywhere, the directory key still matches",
                    done.returncode == 0 and "q1" in done.stdout, "output=%r" % done.stdout[:200])

        # 6. Two rounds at once, and a tab left over from an earlier round.
        ok &= check_two_live_rounds_get_distinct_ports(sandbox)
        ok &= check_a_stale_tab_is_refused(sandbox)

        # 7. The toolkit's own doctor, and the plugin manifests it depends on.
        doctor = subprocess.run([sys.executable, DOCTOR, "doctor"], capture_output=True, text=True)
        ok &= check("the doctor finds the toolkit whole", doctor.returncode == 0,
                    "\n".join(doctor.stdout.splitlines()[-4:]))
        if shutil.which("claude"):
            for manifest in (os.path.join(ROOT, ".claude-plugin", "plugin.json"),
                             os.path.join(ROOT, ".claude-plugin", "marketplace.json")):
                # Through the shell: on Windows the CLI is an npm shim, which CreateProcess
                # cannot start directly.
                validation = subprocess.run(
                    'claude plugin validate "%s" --strict' % manifest,
                    capture_output=True, text=True, shell=True)
                ok &= check("validates: %s" % os.path.basename(manifest), validation.returncode == 0,
                            (validation.stdout or validation.stderr).strip().splitlines()[-1]
                            if (validation.stdout or validation.stderr).strip() else "")
        else:
            print("skip  claude CLI not on PATH: manifests not validated here")
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)

    print("\n" + ("isolation holds" if ok else "ISOLATION BROKEN"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
