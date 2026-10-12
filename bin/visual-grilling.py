"""The visual-grilling toolkit's own entry point: status, doctor, install.

Run it from the plugin directory:

    python bin/visual-grilling.py status
    python bin/visual-grilling.py doctor [--fix]
    python bin/visual-grilling.py install [--harness claude|codex|auto]

`doctor` is the point of this file: a round depends on several files agreeing across two
harnesses, and a disagreement fails quietly — a hook that watches a directory nothing
writes to, a round whose answers nobody collects, two copies of a server that disagree on
the round's shape. Every check below names what it looked at and what to do about it, and
the exit status is 0 only when the toolkit is whole.

`status` prints the same picture without judging it. Neither command writes anything
except where `--fix` says so, and `--fix` only touches this toolkit's own scratch state;
registration in a harness's settings is reported as the command that would change it.
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_DIR = os.path.join(PLUGIN_ROOT, "skills", "visual-grilling")
TEMPLATE_DIR = os.path.join(SKILL_DIR, "template")
SERVE = os.path.join(TEMPLATE_DIR, "serve.py")
PAGE = os.path.join(TEMPLATE_DIR, "page.html")
HOOK = os.path.join(PLUGIN_ROOT, "hooks-handlers", "stop-hook.py")
HOOKS_JSON = os.path.join(PLUGIN_ROOT, "hooks", "hooks.json")
CODEX_HOME = os.path.join(os.path.expanduser("~"), ".codex")
CLAUDE_SETTINGS = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")

MARKER = "visual-grilling"      # what identifies our entry in a harness's config


def temp_root():
    return os.environ.get("TEMP") or os.environ.get("TMP") or "."


def live_dir():
    return os.path.join(temp_root(), "visual-grilling", "live")


def which_harness():
    """Which harness this process is running inside, as far as it can tell.

    Claude Code sets CLAUDE_CODE_* for the shell and for hooks. Codex sets CODEX_HOME and
    runs inside its own home directory. Neither is certain from one variable, so the
    answer is 'claude', 'codex', 'both' or 'unknown' rather than a guess at one.
    """
    claude = any(os.environ.get(name) for name in
                 ("CLAUDE_CODE_SESSION_ID", "CLAUDE_PLUGIN_ROOT", "CLAUDE_CODE_ENTRYPOINT", "CLAUDECODE"))
    codex = bool(os.environ.get("CODEX_HOME")) or bool(os.environ.get("CODEX_SANDBOX")) or \
        os.path.isdir(os.path.join(os.getcwd(), ".codex"))
    if claude and codex:
        return "both"
    if claude:
        return "claude"
    if codex:
        return "codex"
    return "unknown"


def load_constant(path, name):
    """A module-level constant from a file, without importing anything else it does."""
    import re
    try:
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
    except OSError:
        return None
    match = re.search(r"^%s\s*=\s*(\S+)" % name, source, re.M)
    if not match:
        return None
    value = match.group(1)
    try:
        return int(value)
    except ValueError:
        return value.strip('"\'')


def compiles(path):
    done = subprocess.run([sys.executable, "-m", "py_compile", path], capture_output=True, text=True)
    return done.returncode == 0, (done.stderr or "").strip().splitlines()[-1:] or [""]


def read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def live_rounds():
    """Every armed round on this machine: its directory, owner, protocol and age.

    Read from the pointers, which is where a round is discovered — never by scanning
    scratch directories, since a directory nothing points at is not an armed round.
    """
    rounds = []
    for pointer in sorted(glob.glob(os.path.join(live_dir(), "*.txt"))):
        try:
            with open(pointer, encoding="utf-8") as handle:
                target = handle.read().strip()
        except OSError:
            continue
        armed = read_json(os.path.join(target, "round.json")) if target else None
        answers = os.path.join(target, "answers.json") if target else None
        rounds.append({
            "pointer": pointer,
            "dir": target,
            "armed": armed,
            "exists": bool(target) and os.path.isdir(target),
            "has_answers": bool(answers) and os.path.exists(answers),
        })
    return rounds


def claude_registrations():
    """Every Stop-hook command in the user's Claude settings that names this toolkit."""
    settings = read_json(CLAUDE_SETTINGS)
    if not settings:
        return []
    found = []
    for entry in (settings.get("hooks") or {}).get("Stop") or []:
        for hook in entry.get("hooks") or []:
            command = hook.get("command") or ""
            if MARKER in command:
                found.append(command)
    return found


def codex_registration():
    """What Codex can be checked for without a Codex session.

    Codex reads hooks from `~/.codex/hooks.json` (and a project's `.codex/hooks.json`), with
    the same JSON shape Claude Code uses; its handler takes `command` and an optional
    `commandWindows`, because a Codex handler has no `args` and no plugin-root variable. So
    the registered command has to name this hook by absolute path, and trust is recorded per
    hook hash — a new or edited hook is skipped until the person approves it in `/hooks`.
    """
    path = os.path.join(CODEX_HOME, "hooks.json")
    data = read_json(path) or {}
    ours = []
    for group in (data.get("hooks") or {}).get("Stop") or []:
        for hook in group.get("hooks") or []:
            text = "%s %s" % (hook.get("command") or "", hook.get("commandWindows") or "")
            if HOOK.replace("\\", "/") in text.replace("\\", "/") or MARKER in text:
                ours.append(text.strip())
    return {
        "home": CODEX_HOME,
        "hooks_file": path,
        "hooks_present": os.path.exists(path),
        "registered": ours,
    }


def install_codex(link_skills=False):
    """Merge this toolkit's Stop hook into the person's Codex hooks, and touch nothing else.

    Merging, not writing: a Codex user usually has hooks of their own in that file, and a
    Stop group of their own in particular. Only a group that already names this hook is
    replaced, so running this twice leaves one entry rather than two.
    """
    written = []
    path = os.path.join(CODEX_HOME, "hooks.json")
    os.makedirs(CODEX_HOME, exist_ok=True)
    data = read_json(path) or {}
    hooks = data.setdefault("hooks", {})
    groups = hooks.setdefault("Stop", [])

    def ours(group):
        for hook in group.get("hooks") or []:
            text = "%s %s" % (hook.get("command") or "", hook.get("commandWindows") or "")
            if HOOK.replace("\\", "/") in text.replace("\\", "/"):
                return True
        return False

    groups[:] = [group for group in groups if not ours(group)]
    command = 'python -I "%s"' % HOOK
    groups.append({"hooks": [{
        "type": "command",
        "command": command,
        "commandWindows": command,          # a Codex handler has no args and no plugin root
        "timeout": 1900,
        "statusMessage": "waiting for the round's answers",
    }]})
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
    written.append(path)

    if link_skills:
        # Codex discovers skills under ~/.agents/skills. A pointer file keeps one source of
        # truth: the repo's skill, not a second copy that drifts.
        target = os.path.join(os.path.expanduser("~"), ".agents", "skills", "visual-grilling")
        os.makedirs(target, exist_ok=True)
        with open(os.path.join(target, "SKILL.md"), "w", encoding="utf-8") as handle:
            handle.write("---\nname: visual-grilling\n"
                         "description: Grill a decision on a page the reader answers on, holding the turn "
                         "open until they submit. Use when the reader asks to see the options visually, or "
                         "when verbal framing has not settled a decision.\n---\n\n"
                         "Read and follow the skill at %s — this file is a pointer to it, so there is\n"
                         "one copy of the instructions and it cannot go stale.\n" % SKILL_DIR)
        written.append(target)
    return written


def report(label, ok, detail, fix=None):
    mark = "ok  " if ok else "FAIL"
    print("%s  %-46s %s" % (mark, label, detail))
    if not ok and fix:
        print("      fix: %s" % fix)
    return ok


def cmd_status(_args):
    print("plugin root   %s" % PLUGIN_ROOT)
    print("harness       %s   (this process)" % which_harness())
    print("template      %s" % ("present" if os.path.exists(SERVE) else "MISSING"))
    print("protocol      serve %s / hook %s" % (load_constant(SERVE, "PROTOCOL"),
                                               load_constant(HOOK, "PROTOCOL")))
    print("hook file     %s" % ("present" if os.path.exists(HOOK) else "MISSING"))
    print("hooks.json    %s" % (json.dumps(read_json(HOOKS_JSON) or {}, separators=(",", ":"))[:120]))
    print("claude hooks  %s" % (claude_registrations() or "none naming this toolkit"))
    codex = codex_registration()
    print("codex home    %s" % codex["home"])
    print("codex hooks   %s%s" % (codex["hooks_file"],
                                  "" if codex["hooks_present"] else "  (no hooks.json)"))
    print("codex wired   %s" % (codex["registered"] or "none naming this toolkit"))
    rounds = live_rounds()
    print("armed rounds  %d" % len(rounds))
    for entry in rounds:
        armed = entry["armed"] or {}
        age = int((time.time() - (armed.get("startedAt") or 0)) / 60) if armed else -1
        print("  %s  owner=%s protocol=%s age=%smin answers=%s" % (
            entry["dir"], (armed.get("owner") or "NONE")[:28], armed.get("protocol", "?"),
            age if age >= 0 else "?", entry["has_answers"]))
    return 0


def cmd_doctor(args):
    ok = True
    print("visual-grilling doctor — %s\n" % PLUGIN_ROOT)

    version = "%d.%d.%d" % sys.version_info[:3]
    ok &= report("python", sys.version_info >= (3, 8), version,
                 "install Python 3.8 or newer and put it on PATH")

    for label, path in (("template/serve.py", SERVE), ("template/page.html", PAGE),
                        ("hooks-handlers/stop-hook.py", HOOK), ("hooks/hooks.json", HOOKS_JSON)):
        ok &= report(label, os.path.exists(path), "present" if os.path.exists(path) else "missing",
                     "reinstall the plugin: claude plugin update visual-grilling")

    for label, path in (("serve.py compiles", SERVE), ("stop-hook.py compiles", HOOK)):
        if os.path.exists(path):
            good, why = compiles(path)
            ok &= report(label, good, why[0] if why else "")

    serve_protocol = load_constant(SERVE, "PROTOCOL")
    hook_protocol = load_constant(HOOK, "PROTOCOL")
    ok &= report("protocols agree", serve_protocol is not None and serve_protocol == hook_protocol,
                 "serve %s / hook %s" % (serve_protocol, hook_protocol),
                 "update the plugin: claude plugin update visual-grilling")

    hooks_config = read_json(HOOKS_JSON) or {}
    stop_hooks = (hooks_config.get("hooks") or {}).get("Stop") or []
    command = ""
    for entry in stop_hooks:
        for hook in entry.get("hooks") or []:
            # Exec form puts the path in `args` and leaves `command` as the program, which
            # is the form the docs recommend for ${CLAUDE_PLUGIN_ROOT}; read both.
            command = " ".join([hook.get("command") or ""] + list(hook.get("args") or [])) or command
    ok &= report("hooks.json registers a Stop hook", bool(command.strip()), command.strip() or "none",
                 "the plugin's hooks/hooks.json is the registration for a plugin install")
    ok &= report("the registered command is at the plugin root",
                 "${CLAUDE_PLUGIN_ROOT}" in command, command.strip() or "none",
                 "a hard path breaks when the plugin moves")

    registered = claude_registrations()
    if registered:
        # A plugin install and a settings entry can both fire. Harmless on a round the
        # first one already disarmed, but it is a sign the migration is half done.
        report("no second registration in ~/.claude/settings.json", False,
               "%d Stop hook(s) naming this toolkit" % len(registered),
               "remove the old settings entry once the plugin is installed — two hooks "
               "watch the same pointer, and the second one finds the round already delivered")
        print("      (this is expected if you have not migrated to the plugin install yet)")

    rounds = live_rounds()
    for entry in rounds:
        armed = entry["armed"] or {}
        owner = armed.get("owner")
        age = (time.time() - (armed.get("startedAt") or 0)) / 60 if armed else 0
        if not entry["exists"]:
            ok &= report("armed round %s" % entry["dir"], False, "the pointer names a directory that is gone",
                         "remove the pointer: %s" % entry["pointer"])
        elif not armed:
            # A pointer whose round.json is gone: the round was delivered or retired, and
            # only the pointer is left. Not an armed round, and not a failure either.
            print("note  pointer to a finished round: %s" % entry["dir"])
            if args.fix:
                try:
                    os.remove(entry["pointer"])
                    print("      fixed: removed %s" % entry["pointer"])
                except OSError as exc:
                    print("      could not remove it: %s" % exc)
        elif not owner:
            print("warn  a round with no owner is never delivered: %s" % entry["dir"])
            print("      fix: read answers.json there, then re-arm with the current server")
        elif armed.get("protocol") not in (None, serve_protocol):
            print("warn  round armed by protocol %s while the plugin speaks %s: %s"
                  % (armed.get("protocol"), serve_protocol, entry["dir"]))
        elif age > 120:
            print("note  an armed round is %.0f minutes old: %s" % (age, entry["dir"]))

    strays = []
    for base in (temp_root(), os.path.join(temp_root(), "visual-grilling")):
        for candidate in glob.glob(os.path.join(base, "grill*")):
            if os.path.isdir(candidate) and os.path.exists(os.path.join(candidate, "serve.py")):
                strays.append(candidate)
            elif os.path.isdir(candidate):
                for inner in glob.glob(os.path.join(candidate, "*")):
                    if os.path.isdir(inner) and os.path.exists(os.path.join(inner, "serve.py")):
                        strays.append(inner)
    if strays:
        print("warn  %d scratch directory(ies) hold their own copy of serve.py, the layout that "
              "went stale: %s" % (len(strays), ", ".join(strays[:3])))
        print("      they still work; a round started from one is on the old protocol. "
              "Left in place on the Owner's decision (2026-10-12).")

    pointer_dir = live_dir()
    writable = os.access(os.path.dirname(pointer_dir), os.W_OK) if os.path.exists(os.path.dirname(pointer_dir)) \
        else os.access(temp_root(), os.W_OK)
    ok &= report("the pointer directory is writable", writable, pointer_dir,
                 "check TEMP permissions")
    if args.fix and not os.path.isdir(pointer_dir):
        os.makedirs(pointer_dir, exist_ok=True)
        print("      fixed: created %s" % pointer_dir)

    codex = codex_registration()
    if os.path.isdir(CODEX_HOME):
        print("\ncodex: home %s, hooks %s, our Stop hook %s"
              % (codex["home"], "present" if codex["hooks_present"] else "absent",
                 "registered" if codex["registered"] else "not registered"))
        if not codex["registered"]:
            print("      fix: python bin/visual-grilling.py install --harness codex")
        else:
            print("      reminder: Codex records trust against the hook's hash — approve it in "
                  "`/hooks` after any change to the hook, or it is skipped")

    print("\n%s" % ("the toolkit is whole" if ok else "SOMETHING IS BROKEN — see the fix lines above"))
    return 0 if ok else 1


def cmd_install(args):
    """Wire this toolkit into the harnesses present on this machine.

    Claude Code: the plugin's own hooks/hooks.json is the registration, so an install is
    the plugin install itself; printing the commands is the honest report, since a plugin
    cannot add itself to a person's marketplaces.
    """
    harness = args.harness
    if harness == "auto":
        harness = which_harness()
        if harness == "unknown":
            harness = "claude+codex"
    print("harness: %s\n" % harness)
    if "claude" in harness:
        print("Claude Code — install the plugin, which brings the Stop hook with it:")
        print("  claude plugin marketplace add <owner>/visual-grilling")
        print("  claude plugin install visual-grilling@visual-grilling")
        print("  claude plugin validate %s --strict" % PLUGIN_ROOT)
        print("If an older shell hook is still registered in ~/.claude/settings.json, remove it "
              "once a round delivers through the plugin.\n")
    if "codex" in harness:
        print("Codex — hooks live in ~/.codex/hooks.json, with the same shape Claude Code uses;")
        print("a Codex handler takes no args and has no plugin-root variable, so the command")
        print("names this hook by absolute path. Merging, never replacing your own entries.\n")
        written = install_codex(link_skills=getattr(args, "link_skills", False))
        for line in written:
            print("  wrote %s" % line)
        print("\n  Next: in Codex, run /hooks and trust the new Stop hook. Codex records trust")
        print("  against the hook's hash, so an unapproved hook is skipped rather than run.")
        print("  See codex/README.md for what Codex does and does not support here.")
    return 0


def main():
    parser = argparse.ArgumentParser(prog="visual-grilling", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="what is installed, and where").set_defaults(func=cmd_status)

    doctor = sub.add_parser("doctor", help="check the whole toolkit and say what to fix")
    doctor.add_argument("--fix", action="store_true", help="repair this toolkit's own scratch state")
    doctor.set_defaults(func=cmd_doctor)

    install = sub.add_parser("install", help="wire the toolkit into a harness")
    install.add_argument("--harness", choices=("claude", "codex", "auto", "claude+codex"), default="auto")
    install.add_argument("--link-skills", action="store_true",
                         help="Codex: also write the pointer that makes ~/.agents/skills/visual-grilling "
                              "follow this plugin's skill, so there is one copy of the instructions")
    install.set_defaults(func=cmd_install)

    args = parser.parse_args()
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
