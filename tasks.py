"""Cross-platform tasks for FloodSense EU.

Windows PowerShell 5.x, PowerShell 7, cmd, macOS, and Linux. Stdlib only.
No Make and no shell, so PowerShell 5 (which has no &&) can run every command.

    python tasks.py <command>
    py tasks.py <command>

Docker commands always pass -p floodsense-app, plus an explicit compose file
and project directory. An exported COMPOSE_PROJECT_NAME or COMPOSE_FILE
cannot attach this stack to another project, such as a local Zetaris stack.
`down` does not delete volumes and does not need pgvector/.env.
"""

from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = "floodsense-app"

# Posix relative paths. Path() accepts these on Windows.
ENV_EXAMPLES: tuple[str, ...] = (
    ".env.example",
    "api/.env.example",
    "agents/.env.example",
    "ui/.env.example",
    "ingestion/.env.example",
    "pgvector/.env.example",
)
REQUIRED_ENV: tuple[str, ...] = ("api/.env", "agents/.env", "ui/.env")
PGVECTOR_ENV = "pgvector/.env"

# argv, cwd. Callers pass a list so nothing is parsed by a shell.
Runner = Callable[[list[str], Path], int]


def compose_argv(root: Path, *args: str) -> list[str]:
    """Pin project, file, and directory. Flags stay in front of the subcommand."""
    return [
        "docker",
        "compose",
        "-p",
        PROJECT,
        "--project-directory",
        str(root),
        "-f",
        str(root / "compose.yaml"),
        *args,
    ]


def up_argv(root: Path) -> list[str]:
    return compose_argv(root, "up", "-d", "--build")


def up_all_argv(root: Path) -> list[str]:
    return compose_argv(
        root,
        "--profile",
        "rag",
        "--profile",
        "cache",
        "up",
        "-d",
        "--build",
    )


def down_argv(root: Path) -> list[str]:
    # Profiles so optional containers stop too. No -v / --volumes.
    return compose_argv(root, "--profile", "rag", "--profile", "cache", "down")


def config_argv(root: Path) -> list[str]:
    return compose_argv(root, "--profile", "rag", "--profile", "cache", "config")


def missing_env(root: Path, *, require_pgvector: bool = False) -> list[str]:
    needed = list(REQUIRED_ENV)
    if require_pgvector:
        needed.append(PGVECTOR_ENV)
    return [rel for rel in needed if not (root / rel).is_file()]


def check_env(root: Path, *, require_pgvector: bool = False, quiet_ok: bool = False) -> int:
    missing = missing_env(root, require_pgvector=require_pgvector)
    if not missing:
        if not quiet_ok:
            print("env files present")
        return 0
    launcher = Path(sys.executable).name
    print("Missing env files. They are git-ignored. Create them with:", file=sys.stderr)
    print(f"  {launcher} tasks.py init-env", file=sys.stderr)
    for rel in missing:
        example = Path(rel).with_name(".env.example").as_posix()
        print(f"  missing {rel} (example {example})", file=sys.stderr)
    return 1


def init_env(root: Path) -> int:
    """Copy each missing example to .env. Never overwrites an existing file."""
    planned: list[tuple[str, Path, Path]] = []
    for rel in ENV_EXAMPLES:
        src = root / rel
        if not src.is_file():
            print(f"Missing example {rel}", file=sys.stderr)
            return 1
        planned.append((rel, src, src.with_name(".env")))

    copied = 0
    kept = 0
    for rel, src, dest in planned:
        dest_rel = dest.relative_to(root).as_posix()
        if dest.exists():
            print(f"keep   {dest_rel}")
            kept += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        print(f"copy   {rel} -> {dest_rel}")
        copied += 1
    print(
        f"init-env: copied {copied}, kept {kept}. "
        "Fill secrets in the copies. Do not commit .env files."
    )
    return 0


def execute(argv: list[str], cwd: Path) -> int:
    print("+ " + shlex.join(argv), flush=True)
    try:
        completed = subprocess.run(argv, cwd=cwd, check=False)
    except FileNotFoundError:
        print(
            f"Command not found: {argv[0]}. Install it and put it on PATH.",
            file=sys.stderr,
        )
        return 127
    return int(completed.returncode)


def cmd_up(root: Path, runner: Runner) -> int:
    code = check_env(root, quiet_ok=True)
    if code != 0:
        return code
    return runner(up_argv(root), root)


def cmd_up_all(root: Path, runner: Runner) -> int:
    code = check_env(root, require_pgvector=True, quiet_ok=True)
    if code != 0:
        return code
    return runner(up_all_argv(root), root)


def cmd_down(root: Path, runner: Runner) -> int:
    # No env check. A missing pgvector/.env must not trap a running stack.
    return runner(down_argv(root), root)


def cmd_config(root: Path, runner: Runner) -> int:
    print(
        "config prints resolved environment. Do not log it when .env files hold real tokens.",
        file=sys.stderr,
    )
    return runner(config_argv(root), root)


def cmd_zetaris_sync(root: Path, runner: Runner) -> int:
    script = root / "scripts" / "zetaris_sync.py"
    return runner([sys.executable, str(script)], root)


def test_steps(root: Path) -> list[tuple[Path, list[str]]]:
    exe = sys.executable
    return [
        (
            root,
            [
                exe,
                "-m",
                "compileall",
                "-q",
                "api/app",
                "agents/floodsense_agents",
                "scripts",
                "tests",
                "tasks.py",
            ],
        ),
        (root / "api", [exe, "-m", "unittest", "discover", "-s", "tests", "-v"]),
        (root / "agents", [exe, "-m", "unittest", "discover", "-s", "tests", "-v"]),
        (root, [exe, "-m", "unittest", "discover", "-s", "scripts/tests", "-v"]),
        (root, [exe, "-m", "unittest", "discover", "-s", "tests", "-v"]),
    ]


def cmd_test(root: Path, runner: Runner) -> int:
    for cwd, argv in test_steps(root):
        code = runner(argv, cwd)
        if code != 0:
            return code
    return 0


def cmd_lint() -> int:
    print("TODO: lint is not wired yet (ruff, mypy, ui tsc). CI is a later branch.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tasks.py",
        description=(
            "FloodSense EU tasks for Windows, macOS, and Linux. "
            "Docker commands pin project floodsense-app."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-env", help="Copy each missing .env.example to .env. Never overwrites.")
    sub.add_parser("check-env", help="Exit 1 if api/.env, agents/.env, or ui/.env is missing.")
    sub.add_parser("up", help="Build and start API, agents, and UI. Does not start Zetaris.")
    sub.add_parser("up-all", help="up, plus the rag (pgvector) and cache (Redis) profiles.")
    sub.add_parser("down", help="Stop this project, including optional profiles. Keeps volumes.")
    sub.add_parser("config", help="Render the compose file. Prints secrets if .env is filled.")
    sub.add_parser("zetaris-sync", help="Run the Zetaris sync stub. Applies no SQL.")
    sub.add_parser("test", help="Compile and run unit tests with this interpreter.")
    sub.add_parser("lint", help="TODO stub. Exits 0 until the CI branch.")
    return parser


def main(
    argv: list[str] | None = None,
    *,
    root: Path | None = None,
    runner: Runner | None = None,
) -> int:
    root = ROOT if root is None else root
    run = execute if runner is None else runner
    command = build_parser().parse_args(argv).command
    if command == "init-env":
        return init_env(root)
    if command == "check-env":
        return check_env(root)
    if command == "up":
        return cmd_up(root, run)
    if command == "up-all":
        return cmd_up_all(root, run)
    if command == "down":
        return cmd_down(root, run)
    if command == "config":
        return cmd_config(root, run)
    if command == "zetaris-sync":
        return cmd_zetaris_sync(root, run)
    if command == "test":
        return cmd_test(root, run)
    if command == "lint":
        return cmd_lint()
    print(f"Unknown command: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
