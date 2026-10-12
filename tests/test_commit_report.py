"""scripts/commit-report.sh when two runs build the same commit.

Reproduces build #2 on 2026-10-12: two runs started for the merge of PR #1,
the first pushed its report, and the second's `git pull --rebase` hit a
conflict in reports/last-build.md and failed the job.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from tickets import config

SCRIPT = config.ROOT / "scripts/commit-report.sh"


def git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


def runner(tmp: Path, name: str, origin: Path) -> Path:
    d = tmp / name
    git(tmp, "clone", "-q", str(origin), name)
    return d


def write_build(d: Path, label: str) -> None:
    (d / "reports/last-build.md").write_text(f"# Last build\n\n- {label}\n")
    (d / "state/page-hashes.json").write_text('{\n"https://hoopsmatic.com/tickets/": ["%s", "2026-10-12"]\n}\n' % label)


def commit_report(d: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(SCRIPT)], cwd=d, env={**os.environ, "GITHUB_ACTIONS": "true"},
                          capture_output=True, text=True)


def test_second_run_on_same_commit_pushes_its_report(tmp_path):
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    seed = runner(tmp_path, "seed", origin)
    (seed / "reports").mkdir()
    (seed / "state").mkdir()
    write_build(seed, "merge")
    (seed / "code.txt").write_text("generator\n")
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "merge")
    git(seed, "push", "-q", "origin", "HEAD:main")

    # Both runs check out the merge commit before either pushes.
    run1 = runner(tmp_path, "run1", origin)
    run2 = runner(tmp_path, "run2", origin)
    write_build(run1, "run1")
    assert commit_report(run1).returncode == 0
    write_build(run2, "run2")
    res = commit_report(run2)
    assert res.returncode == 0, res.stderr

    check = runner(tmp_path, "check", origin)
    assert "run2" in (check / "reports/last-build.md").read_text()
    assert "run2" in (check / "state/page-hashes.json").read_text()
    log = git(check, "log", "--format=%s").splitlines()
    assert len(log) == 3 and all("[skip ci]" in m for m in log[:2])
    # Only the two files were ever committed by the runs.
    changed = git(check, "diff", "--name-only", "HEAD~2", "HEAD").split()
    assert sorted(changed) == ["reports/last-build.md", "state/page-hashes.json"]


def test_refuses_to_run_outside_ci(tmp_path):
    res = subprocess.run(["bash", str(SCRIPT)], cwd=tmp_path, env={k: v for k, v in os.environ.items()
                                                                   if k != "GITHUB_ACTIONS"},
                         capture_output=True, text=True)
    assert res.returncode == 1 and "CI only" in res.stderr


def test_workflow_refreshes_hashes_before_build():
    wf = (config.ROOT / ".github/workflows/build.yml").read_text()
    refresh = wf.index("git checkout origin/main -- state/page-hashes.json")
    assert refresh < wf.index("python -m tickets build")
