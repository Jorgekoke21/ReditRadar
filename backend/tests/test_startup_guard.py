"""The APP_ENV=production + AUTH_MODE=development guard runs at MODULE
IMPORT time (app/main.py), so it can't be exercised by importing app.main
in-process (the test process has already imported it once with the test
env). Spawn a real, separate Python process instead — this is the only way
to genuinely prove "the backend refuses to start", not just that a function
would raise if called.
"""

import os
import subprocess
import sys


def _run_import_in_subprocess(env_overrides: dict) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update(env_overrides)
    # Force SQLite so this doesn't need a real Postgres to prove the point —
    # the guard fires before any database connection is attempted.
    env["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    env["DATABASE_APP_URL"] = ""
    env["DATABASE_MIGRATION_URL"] = ""
    env["DATABASE_WORKER_URL"] = ""
    return subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd="/app",
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_production_with_development_auth_refuses_to_start():
    result = _run_import_in_subprocess({"APP_ENV": "production", "AUTH_MODE": "development"})
    assert result.returncode != 0
    assert "Refusing to start" in result.stderr
    assert "AUTH_MODE=development" in result.stderr


def test_production_with_supabase_auth_and_secret_starts_fine():
    result = _run_import_in_subprocess(
        {
            "APP_ENV": "production",
            "AUTH_MODE": "supabase",
            "SUPABASE_URL": "https://real-project.supabase.co",
            "SUPABASE_JWT_SECRET": "a-real-looking-secret",
        }
    )
    assert result.returncode == 0, result.stderr


def test_supabase_mode_without_jwt_secret_refuses_to_start():
    result = _run_import_in_subprocess({"APP_ENV": "local", "AUTH_MODE": "supabase", "SUPABASE_JWT_SECRET": ""})
    assert result.returncode != 0
    assert "Refusing to start" in result.stderr
    assert "SUPABASE_JWT_SECRET" in result.stderr


def test_local_development_mode_starts_fine():
    result = _run_import_in_subprocess({"APP_ENV": "local", "AUTH_MODE": "development"})
    assert result.returncode == 0, result.stderr
