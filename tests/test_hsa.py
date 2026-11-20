"""Offline tests for bin/hsa using tests/fake_hermes.py instead of a real Hermes install."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import sqlite3

import pytest

ROOT = Path(__file__).resolve().parent.parent
HSA = ROOT / "skill" / "hermes-subagents" / "bin" / "hsa"
FAKE = Path(__file__).resolve().parent / "fake_hermes.py"


@pytest.fixture()
def env(tmp_path):
    fake = tmp_path / "hermes"
    fake.write_text(f"#!/bin/sh\nexec {sys.executable} {FAKE} \"$@\"\n")
    fake.chmod(0o755)
    return {**os.environ, "HSA_RUNS_DIR": str(tmp_path / "runs"), "HSA_HERMES_BIN": str(fake),
            "HERMES_HOME": str(tmp_path / "no-hermes-home")}


def make_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    for argv in (["init", "-q", "-b", "main"], ["-c", "user.name=t", "-c", "user.email=t@example.com",
                                                "commit", "-q", "--allow-empty", "-m", "init"]):
        subprocess.run(["git", "-C", str(path), *argv], check=True)
    return path


def hsa(env, *args, check=True):
    proc = subprocess.run([sys.executable, str(HSA), *args], env=env, capture_output=True, text=True, timeout=60)
    if check and proc.returncode != 0:
        raise AssertionError(f"hsa {args} rc={proc.returncode}\n{proc.stdout}\n{proc.stderr}")
    return proc


def brief(tmp_path, text="do the thing"):
    path = tmp_path / "brief.md"
    path.write_text(text)
    return str(path)


def calls(workdir: Path) -> list:
    return [json.loads(line) for line in (workdir / "fake-calls.log").read_text().splitlines()]


def test_dispatch_wait_review_roundtrip(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    hsa(env, "dispatch", "t1", str(wd), brief(tmp_path))
    hsa(env, "wait", "t1", "--timeout", "30")
    review = hsa(env, "review", "t1").stdout
    assert "state=done" in review and "STATUS: DONE" in review
    prompt = calls(wd)[0][1]
    assert "Worker rules" in prompt and "do the thing" in prompt and "Task id: t1" in prompt


def test_dispatch_excludes_scratch_dir_from_git(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    hsa(env, "dispatch", "t1", str(wd), brief(tmp_path))
    hsa(env, "wait", "t1", "--timeout", "30")
    (wd / ".hsa-tmp").mkdir()
    (wd / ".hsa-tmp" / "x").write_text("scratch")
    status = subprocess.run(["git", "-C", str(wd), "status", "--short"], capture_output=True, text=True).stdout
    assert ".hsa-tmp" not in status


def test_followup_resumes_same_session(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    hsa(env, "dispatch", "t1", str(wd), brief(tmp_path))
    hsa(env, "wait", "t1", "--timeout", "30")
    hsa(env, "followup", "t1", "phase two please")
    hsa(env, "wait", "t1", "--timeout", "30")
    first, second = calls(wd)
    assert "--resume" not in first
    session = json.loads((Path(env["HSA_RUNS_DIR"]) / "t1" / "turn-1.usage").read_text())["session_id"]
    assert second[second.index("--resume") + 1] == session
    assert second[1].startswith("phase two please") and "must START with the `STATUS:` line" in second[1]


def test_followup_refused_while_running(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    slow = {**env, "FAKE_HERMES_SLEEP": "20"}
    hsa(slow, "dispatch", "t1", str(wd), brief(tmp_path))
    proc = hsa(env, "followup", "t1", "more", check=False)
    assert proc.returncode != 0 and "still running" in proc.stderr
    hsa(env, "stop", "t1")


def test_second_worker_in_busy_workdir_refused(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    slow = {**env, "FAKE_HERMES_SLEEP": "20"}
    hsa(slow, "dispatch", "a", str(wd), brief(tmp_path))
    proc = hsa(env, "dispatch", "b", str(wd), brief(tmp_path), check=False)
    assert proc.returncode != 0 and "already has a running worker" in proc.stderr
    hsa(env, "stop", "a")


def test_stop_kills_process_group_and_marks_stopped(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    hsa({**env, "FAKE_HERMES_SLEEP": "60"}, "dispatch", "t1", str(wd), brief(tmp_path))
    pid = json.loads((Path(env["HSA_RUNS_DIR"]) / "t1" / "meta.json").read_text())["pid"]
    hsa(env, "stop", "t1")
    hsa(env, "wait", "t1", "--timeout", "30")
    assert not Path(f"/proc/{pid}").exists() or "Z" in Path(f"/proc/{pid}/stat").read_text().split(") ")[-1][:1]
    assert "stopped" in hsa(env, "status", "t1").stdout


def test_budget_timeout_marks_failed(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    hsa({**env, "FAKE_HERMES_SLEEP": "30"}, "dispatch", "t1", str(wd), brief(tmp_path), "--budget", "2")
    hsa(env, "wait", "t1", "--timeout", "60")
    assert "failed" in hsa(env, "status", "t1").stdout


def test_loop_feeds_verify_failure_back_until_pass(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    verify = tmp_path / "verify.sh"
    verify.write_text('n=$(wc -l < fake-calls.log); [ "$n" -ge 2 ] || { echo "need more: hidden case"; exit 1; }\n')
    hsa(env, "dispatch", "t1", str(wd), brief(tmp_path), "--verify", str(verify))
    out = hsa(env, "loop", "t1", "--max-fixes", "2").stdout
    assert "LOOP PASS" in out
    second = calls(wd)[1][1]
    assert "FAILED" in second and "need more: hidden case" in second


def test_loop_gives_up_after_max_fixes(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    verify = tmp_path / "verify.sh"
    verify.write_text("echo never; exit 1\n")
    hsa(env, "dispatch", "t1", str(wd), brief(tmp_path), "--verify", str(verify))
    proc = hsa(env, "loop", "t1", "--max-fixes", "1", check=False)
    assert proc.returncode == 1 and "LOOP FAIL" in proc.stdout
    assert len(calls(wd)) == 2


def test_failed_worker_exit_code_is_reported(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    hsa({**env, "FAKE_HERMES_RC": "3"}, "dispatch", "t1", str(wd), brief(tmp_path))
    hsa(env, "wait", "t1", "--timeout", "30")
    assert "failed" in hsa(env, "status", "t1").stdout


def test_worktree_creates_isolated_branch(env, tmp_path):
    repo = make_repo(tmp_path / "repo")
    path = hsa(env, "worktree", str(repo), "hsa/x").stdout.strip()
    branch = subprocess.run(["git", "-C", path, "branch", "--show-current"], capture_output=True, text=True).stdout
    assert branch.strip() == "hsa/x" and Path(path).name == "wt-hsa-x"


def test_unknown_run_is_an_error(env):
    proc = hsa(env, "review", "nope", check=False)
    assert proc.returncode != 0 and "no run named" in proc.stderr


def test_stop_kills_descendants_in_other_sessions(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    hsa({**env, "FAKE_HERMES_SLEEP": "60", "FAKE_HERMES_GRANDCHILD": "1"}, "dispatch", "t1", str(wd), brief(tmp_path))
    deadline = time.time() + 20
    while not (wd / "grandchild.pid").exists() and time.time() < deadline:
        time.sleep(0.2)
    grandchild = int((wd / "grandchild.pid").read_text())
    hsa(env, "stop", "t1")
    time.sleep(1)
    alive = Path(f"/proc/{grandchild}").exists() and not Path(f"/proc/{grandchild}/stat").read_text().split(") ")[-1].startswith("Z")
    assert not alive


def test_followup_raw_sends_message_verbatim(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    hsa(env, "dispatch", "t1", str(wd), brief(tmp_path))
    hsa(env, "wait", "t1", "--timeout", "30")
    hsa(env, "followup", "t1", "just this", "--raw")
    hsa(env, "wait", "t1", "--timeout", "30")
    assert calls(wd)[1][1] == "just this"


def test_report_falls_back_to_session_message_with_status(env, tmp_path):
    """Hermes 'evidence' nudges can make the final answer an evidence reply; the report is an earlier message."""
    wd = make_repo(tmp_path / "wd")
    noisy = {**env, "FAKE_HERMES_OUT": "Evidence: ran the script again, all good.\n" + "x" * 500}
    hsa(noisy, "dispatch", "t1", str(wd), brief(tmp_path))
    hsa(env, "wait", "t1", "--timeout", "30")
    meta = json.loads((Path(env["HSA_RUNS_DIR"]) / "t1" / "meta.json").read_text())
    home = Path(env["HERMES_HOME"]); home.mkdir()
    db = sqlite3.connect(home / "state.db")
    db.execute("create table sessions (id text, cwd text, started_at real, api_call_count int, tool_call_count int,"
               " input_tokens int, output_tokens int, last_activity_at real, last_activity_description text,"
               " ended_at real, end_reason text)")
    db.execute("create table messages (id integer primary key, session_id text, role text, content text,"
               " tool_name text, tool_calls text, timestamp real)")
    sid = json.loads((Path(env["HSA_RUNS_DIR"]) / "t1" / "turn-1.usage").read_text())["session_id"]
    db.execute("insert into messages (session_id, role, content, timestamp) values (?,?,?,?)",
               (sid, "assistant", "Done.\nSTATUS: DONE\nCOMMITS: abc123 feat: x", meta["turn_started_at"] + 1))
    db.execute("insert into messages (session_id, role, content, timestamp) values (?,?,?,?)",
               (sid, "assistant", "Evidence: ran the script again, all good.", meta["turn_started_at"] + 2))
    db.commit()
    report = hsa(env, "report", "t1").stdout
    assert report.startswith("STATUS: DONE") and "abc123" in report


def test_doctor_detects_gateway_hosting_and_env_forwarding(env, tmp_path):
    gateway_like = {**env, "FAKE_HERMES_OUT": "probe=forwarded ppid=1"}
    out = hsa(gateway_like, "doctor", "--timeout", "60").stdout
    assert "env forwarded : yes" in out and "Hermes gateway" in out and "gateway-hosted" in out


def test_doctor_detects_in_process_without_env(env, tmp_path):
    in_process = {**env, "FAKE_HERMES_OUT": "probe=unset ppid=999999999"}
    out = hsa(in_process, "doctor", "--timeout", "60").stdout
    assert "env forwarded : NO" in out and "in-process" in out


def test_doctor_without_probe_makes_no_model_call(env, tmp_path):
    out = hsa(env, "doctor", "--no-probe").stdout
    assert "hermes binary" in out and "probe run" not in out


def start_fake_gateway(tmp_path: Path, workdir: Path) -> subprocess.Popen:
    """A long-lived process named exactly `hermes` (like the real gateway) that runs a command in workdir."""
    link = tmp_path / "gw" / "hermes"
    link.parent.mkdir()
    link.symlink_to(sys.executable)
    code = ("import subprocess, sys, time; c = subprocess.Popen(['sleep', '300'], cwd=sys.argv[1]); "
            "open(sys.argv[2], 'w').write(str(c.pid)); time.sleep(300)")
    return subprocess.Popen([str(link), "-c", code, str(workdir), str(tmp_path / "gw" / "child.pid")])


def wait_for_file(path: Path, seconds: float = 20) -> None:
    deadline = time.time() + seconds
    while not path.exists() and time.time() < deadline:
        time.sleep(0.1)
    assert path.exists(), f"{path} never appeared"


def alive(pid: int) -> bool:
    stat = Path(f"/proc/{pid}/stat")
    return stat.exists() and not stat.read_text().split(") ")[-1].startswith("Z")


def test_stop_sweeps_gateway_commands_but_spares_bystanders(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    bystander = subprocess.Popen(["sleep", "300"], cwd=wd)  # in the workdir, not started by hermes
    hsa({**env, "FAKE_HERMES_SLEEP": "60"}, "dispatch", "t1", str(wd), brief(tmp_path))
    gateway = start_fake_gateway(tmp_path, wd)
    try:
        wait_for_file(tmp_path / "gw" / "child.pid")
        gateway_child = int((tmp_path / "gw" / "child.pid").read_text())
        out = hsa(env, "stop", "t1").stdout
        time.sleep(1)
        assert "1 Hermes-spawned commands" in out
        assert not alive(gateway_child)
        assert alive(bystander.pid) and gateway.poll() is None
    finally:
        for proc in (bystander, gateway):
            proc.kill()
            proc.wait()


def test_stop_never_kills_its_own_ancestors(env, tmp_path):
    """hsa run from a shell that sits in the workdir under a process named `hermes` must not kill that shell."""
    wd = make_repo(tmp_path / "wd")
    hsa({**env, "FAKE_HERMES_SLEEP": "60"}, "dispatch", "t1", str(wd), brief(tmp_path))
    link = tmp_path / "shell" / "hermes"
    link.parent.mkdir()
    link.symlink_to(sys.executable)
    code = ("import subprocess, sys; subprocess.run(['bash', '-c', sys.executable + ' ' + sys.argv[1] + "
            "' stop t1 >/dev/null; echo parent-survived $?'], cwd=sys.argv[2])")
    proc = subprocess.run([str(link), "-c", code, str(HSA), str(wd)], env=env,
                          capture_output=True, text=True, timeout=60)
    assert "parent-survived 0" in proc.stdout


def test_dispatch_warns_for_broad_workdir(env, tmp_path):
    fake_home = make_repo(tmp_path / "home")
    proc = hsa({**env, "HOME": str(fake_home)}, "dispatch", "t1", str(fake_home), brief(tmp_path))
    assert "broad directory" in proc.stderr
    hsa({**env, "HOME": str(fake_home)}, "wait", "t1", "--timeout", "30")


def test_concurrent_status_never_rolls_back_a_followup_turn(env, tmp_path):
    """`hsa status` (which records the session id) racing a follow-up must not write back a stale turn."""
    wd = make_repo(tmp_path / "wd")
    hsa(env, "dispatch", "t1", str(wd), brief(tmp_path))
    hsa(env, "wait", "t1", "--timeout", "30")
    pollers = [subprocess.Popen([sys.executable, str(HSA), "status", "t1"], env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for _ in range(8)]
    hsa({**env, "FAKE_HERMES_SLEEP": "3"}, "followup", "t1", "next")
    for proc in pollers:
        proc.wait()
    meta = json.loads((Path(env["HSA_RUNS_DIR"]) / "t1" / "meta.json").read_text())
    assert meta["turn"] == 2 and len(meta["turns"]) == 2
    hsa(env, "wait", "t1", "--timeout", "30")
    assert "done" in hsa(env, "status", "t1").stdout
