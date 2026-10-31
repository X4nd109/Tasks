"""
test_terminal_autoclose.py - Unit tests for the immediate terminal auto-close.

When Tasks is already running in the background and 'tasks' is invoked from a
terminal, the background window is signaled to show itself and this second
terminal window is closed immediately and silently.
"""

import importlib.util
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

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


class TerminalAutocloseTest(unittest.TestCase):
    """Behavior of immediate terminal close on background instance restoration."""

    def test_autoclose_calls_close_window_immediately(self):
        """_handle_existing_instance_autoclose immediately requests window close and exits with 0."""
        stdout = io.StringIO()
        with patch.object(main, "_close_current_terminal_window") as close_mock, \
                redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as ctx:
                main._handle_existing_instance_autoclose()

            self.assertEqual(ctx.exception.code, 0)
            close_mock.assert_called_once()

    def test_autoclose_is_completely_silent(self):
        """No output is printed to stdout when closing the secondary terminal."""
        stdout = io.StringIO()
        with patch.object(main, "_close_current_terminal_window"), \
                redirect_stdout(stdout):
            try:
                main._handle_existing_instance_autoclose()
            except SystemExit:
                pass

        self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
