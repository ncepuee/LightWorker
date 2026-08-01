import subprocess
from pathlib import Path

from lightworker.config import Config
from lightworker.worktree import create_worktree


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_execute_worktree_is_isolated(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "lightworker@example.invalid")
    git(repo, "config", "user.name", "LightWorker Test")
    (repo / "value.txt").write_text("main\n", encoding="utf-8")
    git(repo, "add", "value.txt")
    git(repo, "commit", "-m", "initial")
    cfg = Config(home=tmp_path / "state")
    cfg.ensure_dirs()
    info = create_worktree(repo, "task-isolation", cfg)
    worktree = Path(info.path)
    assert worktree.exists()
    assert (worktree / "value.txt").read_text(encoding="utf-8") == "main\n"
    (worktree / "value.txt").write_text("worker\n", encoding="utf-8")
    assert (repo / "value.txt").read_text(encoding="utf-8") == "main\n"
    assert info.branch == "lightworker/task-isolation"


def test_subdirectory_workspace_stays_scoped_in_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    workspace = repo / "packages" / "app"
    workspace.mkdir(parents=True)
    git(repo, "init")
    git(repo, "config", "user.email", "lightworker@example.invalid")
    git(repo, "config", "user.name", "LightWorker Test")
    (repo / "root.txt").write_text("root\n", encoding="utf-8")
    (workspace / "app.txt").write_text("app\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")
    cfg = Config(home=tmp_path / "state")
    cfg.ensure_dirs()

    info = create_worktree(workspace, "task-subdirectory", cfg)

    isolated_workspace = Path(info.path)
    assert isolated_workspace.relative_to(cfg.worktrees_dir) == Path(
        "task-subdirectory", "packages", "app"
    )
    assert (isolated_workspace / "app.txt").read_text(encoding="utf-8") == "app\n"
    assert not (isolated_workspace / "root.txt").exists()
