"""Safety checks for the guided installer (no downloads or real app data)."""

import gzip
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import setup_app


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="baby buddy setup ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.version = patch.object(setup_app.sys, "version_info", (3, 14, 0))
        self.version.start()
        self.addCleanup(self.version.stop)
        for name in (
            "manage.py",
            "requirements.lock",
            "static/babybuddy/css/app.css",
            "static/babybuddy/js/app.js",
            "static/babybuddy/js/graph.js",
        ):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture")

    def test_fresh_check_does_not_create_data(self):
        self.assertIsNone(setup_app.preflight(self.root))
        self.assertFalse((self.root / "data").exists())

    def test_existing_database_is_untouched(self):
        database = self.root / "data/db.sqlite3"
        database.parent.mkdir()
        database.write_bytes(b"important existing data")
        with self.assertRaisesRegex(RuntimeError, "existing database"):
            setup_app.setup(self.root)
        self.assertEqual(database.read_bytes(), b"important existing data")
        self.assertFalse((database.parent / setup_app.STATE_NAME).exists())

    def test_custom_config_is_untouched(self):
        (self.root / ".env").write_text("DB_NAME=somewhere-else")
        with self.assertRaisesRegex(RuntimeError, "custom configuration"):
            setup_app.preflight(self.root)
        self.assertEqual((self.root / ".env").read_text(), "DB_NAME=somewhere-else")

    def test_environment_database_is_rejected(self):
        with patch.dict(os.environ, {"DB_NAME": "elsewhere"}):
            with self.assertRaisesRegex(RuntimeError, "custom configuration"):
                setup_app.preflight(self.root)

    def test_dependency_failure_can_be_resumed_without_reset(self):
        with patch.object(
            setup_app, "run", side_effect=subprocess.CalledProcessError(1, "pip")
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                setup_app.setup(self.root)
        self.assertEqual(setup_app.read_state(self.root)["status"], "installing")
        with patch.object(setup_app, "run") as run:
            setup_app.setup(self.root)
        commands = [call.args[1] for call in run.call_args_list]
        self.assertTrue(any("--require-hashes" in command for command in commands))
        self.assertEqual(commands[-1][-1], "configure")
        self.assertFalse((self.root / "data/db.sqlite3").exists())

    def test_ready_setup_does_not_reinstall_or_reset_account(self):
        setup_app.save_state(self.root, "ready")
        (self.root / "data/db.sqlite3").write_bytes(b"household")
        with patch.object(setup_app, "run") as run:
            setup_app.setup(self.root)
        run.assert_not_called()
        self.assertEqual((self.root / "data/db.sqlite3").read_bytes(), b"household")

    def test_lost_database_is_not_recreated(self):
        setup_app.save_state(self.root, "ready")
        with self.assertRaisesRegex(RuntimeError, "database is missing"):
            setup_app.setup(self.root)
        self.assertFalse((self.root / "data/db.sqlite3").exists())

    def test_setup_cannot_overlap(self):
        with setup_app.setup_lock(self.root):
            with self.assertRaisesRegex(RuntimeError, "already running"):
                with setup_app.setup_lock(self.root):
                    self.fail("Second installer acquired the lock")
        with setup_app.setup_lock(self.root):
            pass

    def test_invalid_state_is_not_accepted(self):
        (self.root / "data").mkdir()
        (self.root / "data" / setup_app.STATE_NAME).write_text("[]")
        with self.assertRaisesRegex(RuntimeError, "Invalid setup state"):
            setup_app.preflight(self.root)

    def test_missing_assets_stop_before_database_changes(self):
        (self.root / "static/babybuddy/js/graph.js").unlink()
        with self.assertRaisesRegex(RuntimeError, "complete fork ZIP"):
            setup_app.setup(self.root)
        self.assertFalse((self.root / "data").exists())

    def test_stale_compressed_assets_match_current_ui(self):
        source = self.root / "static/babybuddy/js/app.js"
        compressed = source.with_suffix(".js.gz")
        compressed.write_bytes(gzip.compress(b"old UI"))
        setup_app.refresh_assets(self.root)
        self.assertEqual(gzip.decompress(compressed.read_bytes()), source.read_bytes())

    def test_busy_port_does_not_stop_someone_elses_server(self):
        with socket.socket() as busy:
            busy.bind(("127.0.0.1", 0))
            port = busy.getsockname()[1]
            chosen = setup_app.available_port(port)
            self.assertNotEqual(chosen, port)
            self.assertLess(chosen, port + 20)

    def test_child_process_uses_local_settings_without_dotenv(self):
        env = setup_app.environment()
        self.assertEqual(env["PYTHON_DOTENV_DISABLED"], "1")
        self.assertEqual(env["DJANGO_SETTINGS_MODULE"], "babybuddy.settings.local")


if __name__ == "__main__":
    unittest.main()
