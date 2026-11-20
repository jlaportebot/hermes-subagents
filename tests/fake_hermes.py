#!/usr/bin/env python3
"""Stand-in for `hermes -z`: records argv, honours FAKE_HERMES_SLEEP, writes a usage file, prints a report.

Env knobs: FAKE_HERMES_SESSION forces the session id; FAKE_HERMES_EARLY_USAGE writes the usage file before
sleeping (the real Hermes writes it only at turn end, but this lets tests learn the id); FAKE_HERMES_CRASH
kills the shell wrapper (after writing usage) so the turn ends without a done marker."""
import json, os, signal, sys, time, uuid
from pathlib import Path

args = sys.argv[1:]
usage = args[args.index("--usage-file") + 1]
resume = args[args.index("--resume") + 1] if "--resume" in args else None
workdir = args[args.index("--in") + 1]
session = os.environ.get("FAKE_HERMES_SESSION") or resume or f"local-{uuid.uuid4().hex}"


def write_usage() -> None:
    Path(usage).write_text(json.dumps({"session_id": session, "api_calls": 2,
                                       "turn_exit_reason": "text_response(finish_reason=stop)",
                                       "completed": True, "failed": False}))


Path(workdir, "fake-calls.log").open("a").write(json.dumps(args) + "\n")
if os.environ.get("FAKE_HERMES_EARLY_USAGE") or os.environ.get("FAKE_HERMES_CRASH"):
    write_usage()
if os.environ.get("FAKE_HERMES_CRASH"):
    parent = os.getppid()
    wrapper = int(Path(f"/proc/{parent}/stat").read_text().rsplit(") ", 1)[1].split()[1])
    os.kill(wrapper, signal.SIGKILL)
    sys.exit(1)
if os.environ.get("FAKE_HERMES_GRANDCHILD"):
    import subprocess
    child = subprocess.Popen(["sleep", "300"], start_new_session=True, cwd=workdir)
    Path(workdir, "grandchild.pid").write_text(str(child.pid))
time.sleep(float(os.environ.get("FAKE_HERMES_SLEEP", "0")))
write_usage()
print(os.environ.get("FAKE_HERMES_OUT") or "STATUS: DONE\nCOMMITS: none\nCHANGES:\n- none\nACCEPTANCE:\n- `true` -> 0\nTESTS ADDED: none\nNOT DONE / RISKS: none")
sys.exit(int(os.environ.get("FAKE_HERMES_RC", "0")))
