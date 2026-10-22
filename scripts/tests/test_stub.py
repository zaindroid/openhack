"""The sync stub applies nothing and must not echo arguments."""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from zetaris_sync import main  # noqa: E402


class SyncStubTest(unittest.TestCase):
    def test_exits_clean_and_does_not_echo_arguments(self) -> None:
        secret = "super-secret-token-value"
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main([secret, "--token", secret])
        text = buf.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("No SQL was sent", text)
        self.assertIn("ingestion/.env", text)
        self.assertNotIn(secret, text)


if __name__ == "__main__":
    unittest.main()
