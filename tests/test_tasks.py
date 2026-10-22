"""Non-Docker behaviour of tasks.py. These tests do not need Docker or Make."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tasks  # noqa: E402


class TaskTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for rel in tasks.ENV_EXAMPLES:
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"example {rel}\n".encode())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_init_env_copies_missing_and_does_not_overwrite(self) -> None:
        existing = self.root / "api" / ".env"
        existing.write_bytes(b"keep-me\n")
        out = io.StringIO()
        with redirect_stdout(out):
            code = tasks.init_env(self.root)
            again = tasks.init_env(self.root)
        self.assertEqual(code, 0)
        self.assertEqual(again, 0)
        self.assertEqual(existing.read_bytes(), b"keep-me\n")
        for rel in tasks.ENV_EXAMPLES:
            dest = (self.root / rel).with_name(".env")
            self.assertTrue(dest.is_file(), rel)
        root_env = (self.root / ".env").read_bytes()
        self.assertEqual(root_env, b"example .env.example\n")
        self.assertIn("copied 5, kept 1", out.getvalue())
        self.assertIn("copied 0, kept 6", out.getvalue())

    def test_init_env_stops_when_an_example_is_missing(self) -> None:
        (self.root / "ui" / ".env.example").unlink()
        err = io.StringIO()
        with redirect_stderr(err):
            code = tasks.init_env(self.root)
        self.assertEqual(code, 1)
        self.assertIn("ui/.env.example", err.getvalue())
        self.assertFalse((self.root / ".env").exists())
        self.assertFalse((self.root / "api" / ".env").exists())

    def test_check_env_names_every_missing_file(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err):
            code = tasks.check_env(self.root)
        text = err.getvalue()
        self.assertEqual(code, 1)
        for rel in tasks.REQUIRED_ENV:
            self.assertIn(rel, text)
        self.assertIn("init-env", text)
        self.assertNotIn(tasks.PGVECTOR_ENV, text)

    def test_check_env_passes_without_pgvector(self) -> None:
        for rel in tasks.REQUIRED_ENV:
            (self.root / rel).write_bytes(b"x\n")
        out = io.StringIO()
        with redirect_stdout(out):
            code = tasks.check_env(self.root)
        self.assertEqual(code, 0)
        self.assertIn("env files present", out.getvalue())

    def test_up_all_requires_pgvector_env(self) -> None:
        for rel in tasks.REQUIRED_ENV:
            (self.root / rel).write_bytes(b"x\n")

        def runner(argv: list[str], cwd: Path) -> int:
            raise AssertionError(argv)

        err = io.StringIO()
        with redirect_stderr(err):
            code = tasks.cmd_up_all(self.root, runner)
        self.assertEqual(code, 1)
        self.assertIn(tasks.PGVECTOR_ENV, err.getvalue())

    def test_up_does_not_call_docker_when_env_is_missing(self) -> None:
        def runner(argv: list[str], cwd: Path) -> int:
            raise AssertionError(argv)

        with redirect_stderr(io.StringIO()):
            code = tasks.cmd_up(self.root, runner)
        self.assertEqual(code, 1)

    def test_down_pins_project_and_keeps_volumes_without_env_files(self) -> None:
        calls: list[tuple[list[str], Path]] = []

        def runner(argv: list[str], cwd: Path) -> int:
            calls.append((argv, cwd))
            return 0

        self.assertEqual(tasks.cmd_down(self.root, runner), 0)
        self.assertEqual(len(calls), 1)
        argv, cwd = calls[0]
        self.assertEqual(cwd, self.root)
        self.assertEqual(argv[:4], ["docker", "compose", "-p", "floodsense-app"])
        self.assertEqual(argv[4], "--project-directory")
        self.assertEqual(argv[5], str(self.root))
        self.assertEqual(argv[6], "-f")
        self.assertEqual(argv[7], str(self.root / "compose.yaml"))
        self.assertEqual(
            argv[8:],
            ["--profile", "rag", "--profile", "cache", "down"],
        )
        self.assertNotIn("-v", argv)
        self.assertNotIn("--volumes", argv)

    def test_up_argv_has_no_profiles(self) -> None:
        for rel in tasks.REQUIRED_ENV:
            (self.root / rel).write_bytes(b"x\n")
        seen: list[list[str]] = []

        def runner(argv: list[str], cwd: Path) -> int:
            seen.append(argv)
            return 0

        with redirect_stdout(io.StringIO()):
            self.assertEqual(tasks.cmd_up(self.root, runner), 0)
        self.assertEqual(seen[0][-3:], ["up", "-d", "--build"])
        self.assertNotIn("--profile", seen[0])
        self.assertIn("-p", seen[0])
        self.assertIn("floodsense-app", seen[0])

    def test_zetaris_sync_uses_this_interpreter(self) -> None:
        seen: list[list[str]] = []

        def runner(argv: list[str], cwd: Path) -> int:
            seen.append(argv)
            return 0

        self.assertEqual(tasks.cmd_zetaris_sync(self.root, runner), 0)
        self.assertEqual(seen[0][0], sys.executable)
        self.assertEqual(seen[0][1], str(self.root / "scripts" / "zetaris_sync.py"))

    def test_test_steps_use_this_interpreter_and_include_task_tests(self) -> None:
        steps = tasks.test_steps(self.root)
        self.assertTrue(all(argv[0] == sys.executable for _, argv in steps))
        self.assertIn(self.root / "api", [cwd for cwd, _ in steps])
        self.assertIn(self.root / "agents", [cwd for cwd, _ in steps])
        discovered = [(cwd, argv) for cwd, argv in steps if "discover" in argv]
        starts = [(cwd, argv[argv.index("-s") + 1]) for cwd, argv in discovered]
        self.assertIn((self.root / "api", "tests"), starts)
        self.assertIn((self.root, "scripts/tests"), starts)
        self.assertIn((self.root, "tests"), starts)

    def test_lint_is_a_zero_exit_stub(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = tasks.main(["lint"], root=self.root, runner=self._fail_runner)
        self.assertEqual(code, 0)
        self.assertIn("TODO", out.getvalue())

    def test_unknown_command_exits_nonzero(self) -> None:
        with self.assertRaises(SystemExit) as caught, redirect_stderr(io.StringIO()):
            tasks.main(["nope"], root=self.root)
        self.assertNotEqual(caught.exception.code, 0)

    def test_missing_executable_returns_127(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = tasks.execute(
                ["floodsense-missing-bin-9f3a", "--version"],
                self.root,
            )
        self.assertEqual(code, 127)
        self.assertIn("Command not found", err.getvalue())

    def test_runner_source_does_not_invoke_a_shell(self) -> None:
        source = Path(tasks.__file__).read_text(encoding="utf-8")
        self.assertNotIn("shell=True", source)
        self.assertNotIn("os.system", source)
        self.assertNotIn("python3", source)

    @staticmethod
    def _fail_runner(argv: list[str], cwd: Path) -> int:
        raise AssertionError(argv)


if __name__ == "__main__":
    unittest.main()
