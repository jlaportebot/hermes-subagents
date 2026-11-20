#!/usr/bin/env python3
"""Hidden acceptance check for one eval task: verify.py <task-dir-name>  (cwd = worker's workdir).

Copies the worktree to a temp dir, adds the hidden test (never visible to the worker), runs the full suite.
For t3-tests it instead mutation-tests the worker's test file. Exit 0 = pass.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TASKS = Path(__file__).resolve().parent / "tasks"
MUTANTS = [  # (description, old, new) applied to textkit/stats.py
    ("ties reverse-alphabetical", "(-kv[1], kv[0])", "(-kv[1], tuple(-ord(c) for c in kv[0]))"),
    ("case-sensitive top_words", "w.lower() for w", "w for w"),
    ("apostrophe not a word char", "[A-Za-z']+", "[A-Za-z]+"),
    ("default n=2", "n: int = 3", "n: int = 2"),
    ("off-by-one slice", "[:n]", "[:n + 1]"),
    ("least common first", "(-kv[1], kv[0])", "(kv[1], kv[0])"),
    ("digits count as words", "[A-Za-z']+", "[A-Za-z0-9']+"),
]


def pytest(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
                          cwd=cwd, capture_output=True, text=True)


def copy_tree(src: Path) -> Path:
    dst = Path(tempfile.mkdtemp(prefix="hsa-verify-"))
    shutil.copytree(src, dst / "w", ignore=shutil.ignore_patterns(".git", ".hsa-tmp", "__pycache__"))
    return dst / "w"


def check_suite(work: Path, task: str) -> int:
    hidden = TASKS / task / "hidden_test.py"
    if hidden.exists():
        shutil.copy(hidden, work / "tests" / "test_zz_hidden.py")
    extra = [] if task == "t1-bugfix" else ["--deselect", "tests/test_basic.py::test_slugify_simple"]
    proc = pytest(work, *extra)
    print(proc.stdout[-3000:], proc.stderr[-1000:])
    return proc.returncode


def check_mutants(work: Path) -> int:
    tests = work / "tests" / "test_stats.py"
    if not tests.exists():
        print("tests/test_stats.py missing")
        return 1
    base = pytest(work, "tests/test_stats.py")
    count = base.stdout.count("passed")
    print("baseline:", base.stdout.strip().splitlines()[-1] if base.stdout.strip() else base.stderr[-500:])
    if base.returncode != 0:
        return 1
    source = (work / "textkit" / "stats.py").read_text()
    survivors = []
    for desc, old, new in MUTANTS:
        if old not in source:
            print(f"mutant '{desc}': pattern missing (stats.py was modified?)")
            return 1
        (work / "textkit" / "stats.py").write_text(source.replace(old, new, 1))
        killed = pytest(work, "tests/test_stats.py").returncode != 0
        print(f"mutant '{desc}': {'killed' if killed else 'SURVIVED'}")
        if not killed:
            survivors.append(desc)
    (work / "textkit" / "stats.py").write_text(source)
    print(f"mutants killed {len(MUTANTS) - len(survivors)}/{len(MUTANTS)}" + (f"; survivors: {survivors}" if survivors else ""))
    return 1 if survivors or count == 0 else 0


def main() -> int:
    task = sys.argv[1]
    work = copy_tree(Path.cwd())
    try:
        if task == "t3-tests":
            return check_mutants(work) or check_suite(work, task)
        return check_suite(work, task)
    finally:
        shutil.rmtree(work.parent, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
