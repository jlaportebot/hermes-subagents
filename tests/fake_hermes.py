#!/usr/bin/env python3
"""Stand-in for `hermes -z`: records argv, honours FAKE_HERMES_SLEEP, writes a usage file, prints a report."""
import json, os, sys, time, uuid
from pathlib import Path

args = sys.argv[1:]
usage = args[args.index("--usage-file") + 1]
resume = args[args.index("--resume") + 1] if "--resume" in args else None
workdir = args[args.index("--in") + 1]
Path(workdir, "fake-calls.log").open("a").write(json.dumps(args) + "\n")
if os.environ.get("FAKE_HERMES_GRANDCHILD"):
    import subprocess
    child = subprocess.Popen(["sleep", "300"], start_new_session=True, cwd=workdir)
    Path(workdir, "grandchild.pid").write_text(str(child.pid))
time.sleep(float(os.environ.get("FAKE_HERMES_SLEEP", "0")))
session = resume or f"local-{uuid.uuid4().hex}"
Path(usage).write_text(json.dumps({"session_id": session, "api_calls": 2, "turn_exit_reason": "text_response(finish_reason=stop)",
                                   "completed": True, "failed": False}))
print(os.environ.get("FAKE_HERMES_OUT") or "STATUS: DONE\nCOMMITS: none\nCHANGES:\n- none\nACCEPTANCE:\n- `true` -> 0\nTESTS ADDED: none\nNOT DONE / RISKS: none")
sys.exit(int(os.environ.get("FAKE_HERMES_RC", "0")))
