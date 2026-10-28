"""
test_terminal_autoclose.py - Unit tests for the terminal auto-close countdown.

The countdown in ``main._handle_existing_instance_autoclose`` polls the keyboard
through ``msvcrt`` and measures elapsed time with ``time.monotonic`` /
``time.sleep``. Both are replaced here with deterministic fakes so the tests run
instantly and never touch a real console window.
"""

import importlib.util
import io
import itertools
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_root_main():
    """Loads the project-root ``main.py`` (``import main`` would hit ``src/main.py``).

    ``main.py`` registers its own source directories in ``sys.path`` on import.
    That global change would alter import resolution for every test module that
    runs afterwards (``config`` vs ``src.core.config`` resolve to different module
    objects), so the import is performed in a sandbox and fully rolled back.
    """
    spec = importlib.util.spec_from_file_location(
        "tasks_root_main", PROJECT_ROOT / "main.py"
    )
    module = importlib.util.module_from_spec(spec)
    saved_path = list(sys.path)
    saved_modules = set(sys.modules)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = saved_path
        for name in set(sys.modules) - saved_modules - {spec.name}:
            sys.modules.pop(name, None)
    return module


main = _load_root_main()


class _FakeClock:
    """Deterministic replacement for the ``time`` module used inside ``main``."""

    def __init__(self, max_sleeps: int = 5000):
        self.now = 0.0
        self.sleeps = 0
        self.max_sleeps = max_sleeps

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps += 1
        if self.sleeps > self.max_sleeps:
            raise AssertionError("countdown never terminated")
        # Rounding keeps the accumulated float sum exact (e.g. 200 * 0.05 == 10.0).
        self.now = round(self.now + max(seconds, 0.0), 9)


class TerminalAutocloseTest(unittest.TestCase):
    """Behaviour of the 10-second "[ENTER] to cancel" countdown."""

    def _run(self, clock, kbhit, getwch, timeout_seconds=3):
        """Runs the countdown with mocked time/msvcrt and returns (stdout, close_mock)."""
        msvcrt_stub = MagicMock()
        msvcrt_stub.kbhit.side_effect = kbhit
        msvcrt_stub.getwch.side_effect = getwch
        stdout = io.StringIO()

        with patch.object(main, "time", clock), \
                patch.object(main, "msvcrt", msvcrt_stub), \
                patch.object(main, "_close_current_terminal_window") as close_mock, \
                redirect_stdout(stdout):
            try:
                main._handle_existing_instance_autoclose(timeout_seconds=timeout_seconds)
            except SystemExit as exc:
                self.assertEqual(exc.code, 0)
        return stdout.getvalue(), close_mock

    def test_enter_cancels_autoclose(self):
        """[ENTER] aborts the countdown and keeps the terminal open."""
        clock = _FakeClock()
        output, close_mock = self._run(clock, kbhit=[False, False, True], getwch="\r")

        close_mock.assert_not_called()
        self.assertIn("Restoring window...", output)
        self.assertIn("Window succesfully restored.", output)
        self.assertIn("Close cancelled. Terminal remains open.", output)
        self.assertNotIn("Closing terminal...", output)
        # Cancelled long before the timeout expired.
        self.assertLess(clock.now, 3.0)

    def test_enter_newline_also_cancels(self):
        """A line feed (``\\n``) counts as [ENTER] as well."""
        clock = _FakeClock()
        output, close_mock = self._run(clock, kbhit=lambda: True, getwch=lambda: "\n")

        close_mock.assert_not_called()
        self.assertIn("Close cancelled. Terminal remains open.", output)

    def test_other_keys_ignored(self):
        """Any key other than [ENTER] is ignored; the countdown keeps ticking."""
        clock = _FakeClock()
        ignored_keys = itertools.cycle(["a", " ", "\x1b", "\x00", "\xe0", "x"])
        output, close_mock = self._run(
            clock, kbhit=True, getwch=lambda: next(ignored_keys), timeout_seconds=3
        )

        self.assertNotIn("Close cancelled. Terminal remains open.", output)
        self.assertIn("Closing terminal...", output)
        close_mock.assert_called_once()
        # The whole countdown ran to completion despite the key presses.
        self.assertGreaterEqual(clock.now, 3.0)
        # In-place updates counted down through every second.
        for second in (3, 2, 1):
            self.assertIn(f"This terminal will close in {second}s", output)

    def test_timeout_triggers_terminal_close(self):
        """Without [ENTER] the terminal is closed and the process exits with 0."""
        clock = _FakeClock()
        output, close_mock = self._run(clock, kbhit=False, getwch="", timeout_seconds=2)

        close_mock.assert_called_once()
        self.assertIn("Closing terminal...", output)
        self.assertIn("This terminal will close in 2s. Press [ENTER] to cancel...", output)
        self.assertIn("This terminal will close in 1s. Press [ENTER] to cancel...", output)
        self.assertGreaterEqual(clock.now, 2.0)
        self.assertLess(clock.now, 2.5)

    def test_countdown_starts_at_ten_seconds_by_default(self):
        """The default timeout is 10 seconds, shown from the very first tick."""
        clock = _FakeClock()
        output, close_mock = self._run(clock, kbhit=False, getwch="", timeout_seconds=10)

        close_mock.assert_called_once()
        self.assertIn("This terminal will close in 10s", output)
        self.assertIn("This terminal will close in 1s", output)
        self.assertGreaterEqual(clock.now, 10.0)


if __name__ == "__main__":
    unittest.main()
