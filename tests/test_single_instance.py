"""
test_single_instance.py - Unit tests for the single-instance IPC layer.

The tests use real local IPC (named pipe on Windows, localhost TCP as portable
fallback), but never contact any external network endpoint.
"""

import unittest
from unittest.mock import MagicMock, patch

import src.core.single_instance as single_instance
from src.core.single_instance import (
    SingleInstanceServer,
    create_default_handler,
    send_instance_command,
)


class TestSingleInstanceEcho(unittest.TestCase):
    """Exercises the real transport with an echo-style command handler."""

    def setUp(self):
        def handler(command: str):
            if command == "STATUS":
                return None
            if command == "EMPTY":
                return ""
            return f"ECHO:{command}"

        self.server = SingleInstanceServer(handler)
        self.assertTrue(self.server.start())
        self.addCleanup(self.server.stop)

    def test_server_is_running_and_has_transport(self):
        self.assertTrue(self.server.is_running)
        self.assertIn(self.server.transport, ("pipe", "socket"))

    def test_echo_command(self):
        self.assertEqual(send_instance_command("PING"), "ECHO:PING")

    def test_echo_show_and_quit_commands(self):
        self.assertEqual(send_instance_command("SHOW"), "ECHO:SHOW")
        self.assertEqual(send_instance_command("QUIT"), "ECHO:QUIT")

    def test_status_falls_back_to_running(self):
        self.assertEqual(send_instance_command("STATUS"), "RUNNING")

    def test_empty_response_falls_back_to_ok(self):
        self.assertEqual(send_instance_command("EMPTY"), "OK")

    def test_invalid_empty_command(self):
        self.assertIsNone(send_instance_command(""))
        self.assertIsNone(send_instance_command("   "))

    def test_stop_shuts_down_server(self):
        self.server.stop()

        self.assertFalse(self.server.is_running)
        self.assertIsNone(self.server.transport)
        self.assertIsNone(send_instance_command("STATUS", timeout=0.3))


class TestSingleInstanceDefaultHandler(unittest.TestCase):
    def setUp(self):
        self.on_show = MagicMock()
        self.on_quit = MagicMock()
        self.status_provider = MagicMock(return_value="RUNNING|5 open")

        handler = create_default_handler(
            on_show=self.on_show,
            on_quit=self.on_quit,
            status_provider=self.status_provider,
        )
        self.server = SingleInstanceServer(handler)
        self.assertTrue(self.server.start())
        self.addCleanup(self.server.stop)

    def test_show_restores_window(self):
        self.assertEqual(send_instance_command("SHOW"), "OK")
        self.on_show.assert_called_once()

    def test_quit_terminates_app(self):
        self.assertEqual(send_instance_command("QUIT"), "OK")
        self.on_quit.assert_called_once()

    def test_status_returns_stats(self):
        self.assertEqual(send_instance_command("STATUS"), "RUNNING|5 open")
        self.status_provider.assert_called_once()

    def test_unknown_command(self):
        self.assertEqual(send_instance_command("DO_SOMETHING"), "UNKNOWN_COMMAND")


class TestSingleInstanceSocketFallback(unittest.TestCase):
    """Verifies the portable localhost-socket transport."""

    def setUp(self):
        patcher = patch.object(single_instance, "_use_named_pipe", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.server = SingleInstanceServer(lambda command: f"ECHO:{command}")
        self.assertTrue(self.server.start())
        self.addCleanup(self.server.stop)

    def test_socket_transport_echo(self):
        self.assertEqual(self.server.transport, "socket")
        self.assertEqual(send_instance_command("PING"), "ECHO:PING")

    def test_no_server_returns_none(self):
        self.server.stop()

        self.assertIsNone(send_instance_command("STATUS", timeout=0.3))


if __name__ == "__main__":
    unittest.main()
