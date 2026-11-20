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
    assert "HSA_BASE=" in second, "the worker must re-run verify against the same base"
    assert "LOOP PASS: t1 verified on turn 2 after 1 fix round(s)" in out


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


# ------------------------------------------------------------ hardening tests
def runs_dir(env) -> Path:
    return Path(env["HSA_RUNS_DIR"])


def read_meta(env, run_id) -> dict:
    return json.loads((runs_dir(env) / run_id / "meta.json").read_text())


def write_meta(env, run_id, **fields) -> Path:
    run_dir = runs_dir(env) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "meta.json").write_text(json.dumps({"id": run_id, **fields}))
    return run_dir


def session_of(env, run_id, turn=1) -> str:
    path = runs_dir(env) / run_id / f"turn-{turn}.usage"
    wait_for_file(path)
    return json.loads(path.read_text())["session_id"]


def spawn_sleep(cwd, session=None) -> subprocess.Popen:
    sleep_env = {k: v for k, v in os.environ.items() if k != "HERMES_SESSION_ID"}
    if session:
        sleep_env["HERMES_SESSION_ID"] = session
    return subprocess.Popen(["sleep", "300"], cwd=cwd, env=sleep_env)


def reap(*procs) -> None:
    for proc in procs:
        proc.kill()
        proc.wait()


@pytest.mark.parametrize("bad", [".", "..", "a/b", "_x", ".hidden", "x" * 65, ""])
def test_dispatch_rejects_invalid_run_ids(env, tmp_path, bad):
    wd = make_repo(tmp_path / "wd")
    runs_dir(env).mkdir()
    marker = runs_dir(env) / "keep.txt"
    marker.write_text("x")
    proc = hsa(env, "dispatch", bad, str(wd), brief(tmp_path), "--force", check=False)
    assert proc.returncode != 0 and "invalid run id" in proc.stderr
    assert marker.exists()


def test_status_skips_non_run_dirs_and_corrupt_meta(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    hsa(env, "dispatch", "good", str(wd), brief(tmp_path))
    hsa(env, "wait", "good", "--timeout", "30")
    write_meta(env, "_doctor", turn=1)
    bad = runs_dir(env) / "bad"
    bad.mkdir()
    (bad / "meta.json").write_text("{not json")
    proc = hsa(env, "status")
    assert "good" in proc.stdout and "bad" not in proc.stdout.replace("bad-", "") and "_doctor" not in proc.stdout
    assert proc.stderr.count("bad") == 1


def test_dispatch_checks_inputs_before_touching_run_dir(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    missing = hsa(env, "dispatch", "t1", str(wd), str(tmp_path / "nope.md"), check=False)
    assert missing.returncode != 0 and "brief" in missing.stderr
    no_verify = hsa(env, "dispatch", "t1", str(wd), brief(tmp_path), "--verify", str(tmp_path / "nope.sh"), check=False)
    assert no_verify.returncode != 0 and "verify" in no_verify.stderr
    huge = hsa(env, "dispatch", "t1", str(wd), brief(tmp_path, "x" * 120_000), check=False)
    assert huge.returncode != 0 and "128 KiB" in huge.stderr
    assert not (runs_dir(env) / "t1").exists()


def test_followup_refuses_oversized_prompt(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    hsa(env, "dispatch", "t1", str(wd), brief(tmp_path))
    hsa(env, "wait", "t1", "--timeout", "30")
    proc = hsa(env, "followup", "t1", "y" * 120_000, check=False)
    assert proc.returncode != 0 and "128 KiB" in proc.stderr
    assert read_meta(env, "t1")["turn"] == 1


def test_force_refuses_running_run_and_foreign_dirs(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    hsa({**env, "FAKE_HERMES_SLEEP": "60"}, "dispatch", "t1", str(wd), brief(tmp_path))
    try:
        proc = hsa(env, "dispatch", "t1", str(wd), brief(tmp_path), "--force", check=False)
        assert proc.returncode != 0 and "running" in proc.stderr
    finally:
        hsa(env, "stop", "t1")
    foreign = runs_dir(env) / "foreign"
    foreign.mkdir()
    (foreign / "precious.txt").write_text("keep")
    other = make_repo(tmp_path / "wd2")
    proc = hsa(env, "dispatch", "foreign", str(other), brief(tmp_path), "--force", check=False)
    assert proc.returncode != 0 and "not an hsa run dir" in proc.stderr
    assert (foreign / "precious.txt").exists()
    (foreign / "precious.txt").unlink()
    hsa(env, "dispatch", "foreign", str(other), brief(tmp_path))
    hsa(env, "wait", "foreign", "--timeout", "30")


def test_prompt_header_names_base_commit_and_meta_has_verify_timeout(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    head = subprocess.run(["git", "-C", str(wd), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    hsa(env, "dispatch", "t1", str(wd), brief(tmp_path), "--verify-timeout", "7")
    hsa(env, "wait", "t1", "--timeout", "30")
    assert f"Base commit: {head}" in calls(wd)[0][1]
    assert read_meta(env, "t1")["verify_timeout_s"] == 7


def test_stop_sweep_uses_session_tag_and_spares_everything_else(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    outside = tmp_path / "outside"
    outside.mkdir()
    hsa({**env, "FAKE_HERMES_SLEEP": "60", "FAKE_HERMES_EARLY_USAGE": "1"}, "dispatch", "t1", str(wd), brief(tmp_path))
    sid = session_of(env, "t1")
    tagged, helper, other_worker, untagged = (spawn_sleep(wd, sid), spawn_sleep(outside, sid),
                                              spawn_sleep(wd, "someone-else"), spawn_sleep(wd))
    try:
        out = hsa(env, "stop", "t1").stdout
        time.sleep(1)
        assert f"swept 1 commands tagged with session {sid}" in out
        assert not alive(tagged.pid)
        assert alive(helper.pid) and alive(other_worker.pid) and alive(untagged.pid)
    finally:
        reap(tagged, helper, other_worker, untagged)


def test_stop_fallback_skipped_when_workdir_is_shared(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    slow = {**env, "FAKE_HERMES_SLEEP": "60"}
    hsa(slow, "dispatch", "a", str(wd), brief(tmp_path))
    hsa(slow, "dispatch", "b", str(wd), brief(tmp_path), "--share-workdir")
    gateway = start_fake_gateway(tmp_path, wd)
    try:
        wait_for_file(tmp_path / "gw" / "child.pid")
        child = int((tmp_path / "gw" / "child.pid").read_text())
        out = hsa(env, "stop", "a").stdout
        time.sleep(1)
        assert "no sweep" in out and alive(child)
    finally:
        reap(gateway)
        hsa(env, "stop", "b")
        os.kill(child, 9)


def test_broad_directories_are_never_swept(env, tmp_path):
    home = tmp_path / "home"
    wd = home / "src"
    make_repo(wd / "one")
    make_repo(wd / "two")
    hsa({**env, "HOME": str(home), "FAKE_HERMES_SLEEP": "60"}, "dispatch", "t1", str(wd), brief(tmp_path))
    out = hsa({**env, "HOME": str(home)}, "stop", "t1").stdout
    assert "no sweep" in out and "broad" in out


def test_repo_with_submodule_checkout_is_not_broad(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    (wd / "sub").mkdir()
    (wd / "sub" / ".git").write_text("gitdir: ../.git/modules/sub\n")
    proc = hsa(env, "dispatch", "t1", str(wd), brief(tmp_path))
    hsa(env, "wait", "t1", "--timeout", "30")
    assert "broad" not in proc.stderr


def test_state_of_run_whose_pid_was_reused_is_crashed(env, tmp_path):
    imposter = subprocess.Popen(["sleep", "300"])
    try:
        write_meta(env, "t1", workdir=str(tmp_path), turn=1, pid=imposter.pid,
                   turn_started_at=time.time() - 1000, budget_s=60)
        rows = json.loads(hsa(env, "status", "--json").stdout)
        assert rows[0]["state"] == "crashed"
    finally:
        reap(imposter)


def test_stop_never_signals_finished_turn_or_reused_pid(env, tmp_path):
    imposter = subprocess.Popen(["sleep", "300"])
    try:
        run_dir = write_meta(env, "t1", workdir=str(tmp_path), turn=1, pid=imposter.pid,
                             turn_started_at=time.time(), budget_s=60)
        (run_dir / "turn-1.done").write_text("0 1\n")
        out = hsa(env, "stop", "t1").stdout
        assert "not running" in out and alive(imposter.pid)
        assert "stopped" not in read_meta(env, "t1") or not read_meta(env, "t1")["stopped"]
    finally:
        reap(imposter)


def test_wait_without_timeout_gives_up_past_budget(env, tmp_path):
    runner = subprocess.Popen(["bash", "-c", "sleep 300; true"], start_new_session=True)
    try:
        time.sleep(0.3)
        started = time.time()
        write_meta(env, "t1", workdir=str(tmp_path), turn=1, pid=runner.pid, turn_started_at=started, budget_s=-700)
        proc = hsa(env, "wait", "t1", check=False)
        assert proc.returncode != 0 and "still running past budget + 10 min" in proc.stderr
    finally:
        os.killpg(runner.pid, 9)
        runner.wait()


def test_loop_requires_verify_script(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    hsa(env, "dispatch", "t1", str(wd), brief(tmp_path))
    proc = hsa(env, "loop", "t1", check=False)
    assert proc.returncode == 2 and "no verify script" in proc.stderr


def test_loop_does_not_restart_a_stopped_worker(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    verify = tmp_path / "verify.sh"
    verify.write_text("exit 1\n")
    hsa({**env, "FAKE_HERMES_SLEEP": "60"}, "dispatch", "t1", str(wd), brief(tmp_path), "--verify", str(verify))
    hsa(env, "stop", "t1")
    proc = hsa(env, "loop", "t1", check=False)
    assert proc.returncode == 2 and "stopped" in proc.stdout
    assert len(calls(wd)) == 1


def test_loop_retries_one_crash_then_fails(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    verify = tmp_path / "verify.sh"
    verify.write_text("exit 1\n")
    crashing = {**env, "FAKE_HERMES_CRASH": "1"}
    hsa(crashing, "dispatch", "t1", str(wd), brief(tmp_path), "--verify", str(verify))
    proc = hsa(crashing, "loop", "t1", "--max-fixes", "3", check=False)
    assert proc.returncode == 1 and "LOOP FAIL (crashed twice)" in proc.stdout
    assert len(calls(wd)) == 2


def test_verify_timeout_reports_rc_124(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    verify = tmp_path / "verify.sh"
    verify.write_text("echo partial; sleep 30\n")
    hsa(env, "dispatch", "t1", str(wd), brief(tmp_path), "--verify", str(verify), "--verify-timeout", "1")
    proc = hsa(env, "verify", "t1", check=False)
    assert proc.returncode == 124 and "verify timed out after 1 s" in proc.stdout and "partial" in proc.stdout


def test_loop_exits_2_when_verify_script_vanishes(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    verify = tmp_path / "verify.sh"
    verify.write_text("exit 1\n")
    hsa(env, "dispatch", "t1", str(wd), brief(tmp_path), "--verify", str(verify))
    hsa(env, "wait", "t1", "--timeout", "30")
    verify.unlink()
    proc = hsa(env, "loop", "t1", check=False)
    assert proc.returncode == 2 and "not found" in proc.stderr
    assert len(calls(wd)) == 1


def make_state_db(home: Path, sessions_cwd=None, started_at=0.0, ids=()) -> None:
    home.mkdir(exist_ok=True)
    db = sqlite3.connect(home / "state.db")
    db.execute("create table sessions (id text, cwd text, started_at real, api_call_count int, tool_call_count int,"
               " input_tokens int, output_tokens int, last_activity_at real, last_activity_description text,"
               " ended_at real, end_reason text)")
    for sid in ids:
        db.execute("insert into sessions (id, cwd, started_at) values (?,?,?)", (sid, sessions_cwd, started_at))
    db.commit()
    db.close()


def test_session_id_ambiguous_state_db_is_not_guessed(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    write_meta(env, "t1", workdir=str(wd), turn=1, pid=0, turn_started_at=time.time() - 10, budget_s=60)
    make_state_db(Path(env["HERMES_HOME"]), str(wd), time.time(), ["s1", "s2"])
    proc = hsa(env, "status", "t1")
    assert "session_id" not in read_meta(env, "t1") and "not guessing" in proc.stderr
    assert proc.stderr.count("not guessing") == 1


def test_usage_session_id_overrides_state_db_guess(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    run_dir = write_meta(env, "t1", workdir=str(wd), turn=1, pid=0, turn_started_at=time.time() - 10, budget_s=60)
    make_state_db(Path(env["HERMES_HOME"]), str(wd), time.time(), ["guess"])
    hsa(env, "status", "t1")
    assert read_meta(env, "t1")["session_id"] == "guess"
    (run_dir / "turn-1.usage").write_text(json.dumps({"session_id": "real"}))
    hsa(env, "status", "t1")
    meta = read_meta(env, "t1")
    assert meta["session_id"] == "real" and meta["session_source"] == "usage"


def test_concurrent_followups_launch_one_turn(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    hsa(env, "dispatch", "t1", str(wd), brief(tmp_path))
    hsa(env, "wait", "t1", "--timeout", "30")
    slow = {**env, "FAKE_HERMES_SLEEP": "6"}
    procs = [subprocess.Popen([sys.executable, str(HSA), "followup", "t1", "go"], env=slow,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    results = [(p.wait(timeout=60), p.stderr.read()) for p in procs]
    codes = sorted(rc for rc, _ in results)
    assert codes[0] == 0 and codes[1] != 0
    assert any("still running" in err for _, err in results)
    assert [t["turn"] for t in read_meta(env, "t1")["turns"]] == [1, 2]
    hsa(env, "stop", "t1")


def test_unreadable_state_db_degrades_to_one_warning(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    hsa(env, "dispatch", "t1", str(wd), brief(tmp_path))
    hsa(env, "wait", "t1", "--timeout", "30")
    home = Path(env["HERMES_HOME"])
    home.mkdir()
    sqlite3.connect(home / "state.db").execute("create table unrelated (x int)").connection.close()
    for cmd in ("status", "tail", "review"):
        proc = hsa(env, cmd, "t1")
        assert proc.stderr.count("cannot read Hermes state.db") <= 1
    assert "cannot read Hermes state.db" in hsa(env, "tail", "t1").stderr


@pytest.mark.parametrize("content", ["", "[]", "{broken"])
def test_bad_usage_files_are_tolerated(env, tmp_path, content):
    wd = make_repo(tmp_path / "wd")
    hsa(env, "dispatch", "t1", str(wd), brief(tmp_path))
    hsa(env, "wait", "t1", "--timeout", "30")
    (runs_dir(env) / "t1" / "turn-1.usage").write_text(content)
    meta_path = runs_dir(env) / "t1" / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta.pop("session_id", None)
    meta.pop("session_source", None)
    meta_path.write_text(json.dumps(meta))
    for cmd in ("status", "review", "report", "tail"):
        hsa(env, cmd, "t1")


def test_garbled_done_marker_counts_as_failed(env, tmp_path):
    run_dir = write_meta(env, "t1", workdir=str(tmp_path), turn=1, pid=0, turn_started_at=time.time(), budget_s=60)
    (run_dir / "turn-1.done").write_text("")
    assert json.loads(hsa(env, "status", "--json").stdout)[0]["state"] == "failed"
    (run_dir / "turn-1.done").write_text("garbage\n")
    assert json.loads(hsa(env, "status", "--json").stdout)[0]["state"] == "failed"


def test_stop_keeps_wrappers_marker_and_skips_finished_turns(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    hsa(env, "dispatch", "t1", str(wd), brief(tmp_path))
    hsa(env, "wait", "t1", "--timeout", "30")
    out = hsa(env, "stop", "t1").stdout
    assert "not running" in out
    assert (runs_dir(env) / "t1" / "turn-1.done").read_text().startswith("0 ")


def test_followup_after_stop_clears_stopped_flags(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    hsa({**env, "FAKE_HERMES_SLEEP": "60", "FAKE_HERMES_EARLY_USAGE": "1"}, "dispatch", "t1", str(wd), brief(tmp_path))
    session_of(env, "t1")
    hsa(env, "stop", "t1")
    assert read_meta(env, "t1")["stopped"] and "stopped_at" in read_meta(env, "t1")
    hsa(env, "followup", "t1", "again")
    meta = read_meta(env, "t1")
    assert meta["stopped"] is False and "stopped_at" not in meta
    hsa(env, "wait", "t1", "--timeout", "30")


def test_minimal_meta_never_raises_keyerror(env, tmp_path):
    write_meta(env, "t1", turn=1)
    for cmd in ("status", "review", "report", "tail"):
        proc = hsa(env, cmd, "t1")
        assert "Traceback" not in proc.stderr
    assert "-" in hsa(env, "status", "t1").stdout


def test_tail_prints_placeholder_for_missing_timestamp(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    hsa(env, "dispatch", "t1", str(wd), brief(tmp_path))
    hsa(env, "wait", "t1", "--timeout", "30")
    sid = session_of(env, "t1")
    home = Path(env["HERMES_HOME"])
    make_state_db(home)
    db = sqlite3.connect(home / "state.db")
    db.execute("create table messages (id integer primary key, session_id text, role text, content text,"
               " tool_name text, tool_calls text, timestamp real)")
    db.execute("insert into messages (session_id, role, content, timestamp) values (?,?,?,NULL)", (sid, "user", "hi"))
    db.commit()
    db.close()
    assert "--:--:-- USER: hi" in hsa(env, "tail", "t1").stdout


def slow_hermes(tmp_path) -> str:
    fake = tmp_path / "slow-hermes"
    fake.write_text("#!/bin/sh\nsleep 30\n")
    fake.chmod(0o755)
    return str(fake)


def test_doctor_timeouts_do_not_traceback(env, tmp_path):
    proc = hsa({**env, "HSA_HERMES_BIN": slow_hermes(tmp_path)},
               "doctor", "--timeout", "1", check=False)
    assert "Traceback" not in proc.stderr
    assert "hermes --version timed out" in proc.stdout and "probe timed out after 1 s" in proc.stdout


def test_doctor_reports_session_tagging(env, tmp_path):
    tagged = {**env, "FAKE_HERMES_SESSION": "sess-42", "FAKE_HERMES_OUT": "probe=forwarded ppid=1 sid=sess-42"}
    assert "session-tagged : yes" in hsa(tagged, "doctor", "--timeout", "60").stdout
    untagged = {**env, "FAKE_HERMES_SESSION": "sess-42", "FAKE_HERMES_OUT": "probe=forwarded ppid=1 sid=unset"}
    assert "session-tagged : no" in hsa(untagged, "doctor", "--timeout", "60").stdout


def test_review_flags_untracked_files(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    hsa(env, "dispatch", "t1", str(wd), brief(tmp_path))
    hsa(env, "wait", "t1", "--timeout", "30")
    (wd / "fake-calls.log").unlink()
    assert "red flags in added lines: none" in hsa(env, "review", "t1").stdout
    (wd / "new.py").write_text("x = 1  # TODO later\n")
    (wd / ".hsa-tmp").mkdir()
    (wd / ".hsa-tmp" / "scratch.txt").write_text("FIXME")
    (wd / "blob.bin").write_bytes(b"\xff\xfe\x00")
    out = hsa(env, "review", "t1").stdout
    assert "red flags in added lines: TODO" in out


def test_second_stop_sweeps_commands_a_ghost_restarted(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    hsa({**env, "FAKE_HERMES_SLEEP": "60", "FAKE_HERMES_EARLY_USAGE": "1"}, "dispatch", "t1", str(wd), brief(tmp_path))
    sid = session_of(env, "t1")
    hsa(env, "stop", "t1")
    revived = spawn_sleep(wd, sid)
    try:
        out = hsa(env, "stop", "t1").stdout
        time.sleep(1)
        assert "client not running" in out and f"swept 1 commands tagged with session {sid}" in out
        assert not alive(revived.pid)
    finally:
        reap(revived)


def test_stop_refuses_to_sweep_next_to_a_gateway(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    hsa({**env, "FAKE_HERMES_SLEEP": "60", "FAKE_HERMES_EARLY_USAGE": "1"}, "dispatch", "t1", str(wd), brief(tmp_path))
    sid = session_of(env, "t1")
    link = tmp_path / "gw" / "hermes"
    link.parent.mkdir()
    link.symlink_to(sys.executable)
    gateway = subprocess.Popen([str(link), "-c", "import time; time.sleep(300)", "gateway", "run"], cwd=wd)
    tagged = spawn_sleep(wd, sid)
    try:
        time.sleep(0.5)
        out = hsa(env, "stop", "t1").stdout
        assert "no sweep" in out and "gateway" in out and alive(tagged.pid)
    finally:
        reap(gateway, tagged)


def test_loop_passes_when_verify_passes_even_if_worker_crashed(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    verify = tmp_path / "verify.sh"
    verify.write_text("exit 0\n")
    crashing = {**env, "FAKE_HERMES_CRASH": "1"}
    hsa(crashing, "dispatch", "t1", str(wd), brief(tmp_path), "--verify", str(verify))
    proc = hsa(crashing, "loop", "t1")
    assert "LOOP PASS: t1 verified on turn 1 after 0 fix round(s) (verify passed; worker turn ended crashed)" in proc.stdout
    assert len(calls(wd)) == 1


def test_non_utf8_done_marker_is_failed_not_a_crash(env, tmp_path):
    run_dir = write_meta(env, "t1", workdir=str(tmp_path), turn=1, pid=0, turn_started_at=time.time(), budget_s=60)
    (run_dir / "turn-1.done").write_bytes(b"\xff\xfe\x80")
    proc = hsa(env, "status", "--json")
    assert json.loads(proc.stdout)[0]["state"] == "failed"


def test_meta_without_pid_is_starting_only_briefly(env, tmp_path):
    write_meta(env, "fresh", workdir=str(tmp_path), turn=1, created_at=time.time())
    write_meta(env, "old", workdir=str(tmp_path), turn=1, created_at=time.time() - 3600)
    states = {r["id"]: r["state"] for r in json.loads(hsa(env, "status", "--json").stdout)}
    assert states == {"fresh": "starting", "old": "crashed"}


def test_force_replaces_run_whose_dispatch_died_before_launch(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    write_meta(env, "t1", workdir=str(wd), turn=1, created_at=time.time() - 3600)
    hsa(env, "dispatch", "t1", str(wd), brief(tmp_path), "--force")
    hsa(env, "wait", "t1", "--timeout", "30")


def test_verify_pass_is_not_blocked_by_a_daemon_it_leaves_behind(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    verify = tmp_path / "verify.sh"
    verify.write_text("setsid sleep 29.123 &\nexit 0\n")
    hsa(env, "dispatch", "t1", str(wd), brief(tmp_path), "--verify", str(verify), "--verify-timeout", "10")
    hsa(env, "wait", "t1", "--timeout", "30")
    started = time.time()
    try:
        proc = hsa(env, "verify", "t1", check=False)
        assert proc.returncode == 0 and "VERIFY PASS" in proc.stdout and time.time() - started < 8
    finally:
        subprocess.run(["pkill", "-f", "sleep 29.123"])


def test_stop_never_signals_live_non_wrapper_without_marker(env, tmp_path):
    imposter = subprocess.Popen(["sleep", "300"])
    try:
        write_meta(env, "t1", workdir=str(tmp_path), turn=1, pid=imposter.pid,
                   turn_started_at=time.time() - 1000, budget_s=60)
        out = hsa(env, "stop", "t1").stdout
        assert "client not running" in out and alive(imposter.pid)
        assert read_meta(env, "t1")["stopped"] is True
        assert json.loads(hsa(env, "status", "--json").stdout)[0]["state"] == "stopped"
    finally:
        reap(imposter)


def test_followup_tolerates_meta_without_turn(env, tmp_path):
    wd = make_repo(tmp_path / "wd")
    write_meta(env, "t1", workdir=str(wd), reasoning="low", budget_s=60, terminal_timeout_s=60,
               session_id="s-1", created_at=time.time() - 3600)
    proc = hsa(env, "followup", "t1", "go")
    assert "Traceback" not in proc.stderr and read_meta(env, "t1")["turn"] == 2
    hsa(env, "wait", "t1", "--timeout", "30")
