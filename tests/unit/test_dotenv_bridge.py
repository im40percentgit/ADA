"""
Tests for the .env → os.environ bridge introduced in ada/__main__.py.

Acceptance criteria (DEC-CORE-004):
  1. A value written to a .env file reaches os.environ after load_dotenv() runs.
  2. Shell-exported values (already in os.environ) are NOT overridden by .env
     because load_dotenv(override=False) is used.
  3. The bridge works for all secret var names used by Ada: ANTHROPIC_API_KEY,
     OPENAI_API_KEY, ADA_JWT_SECRET, ADA_VAPID_PRIVATE_KEY.

These tests call load_dotenv() directly (the same function used by __main__.py)
so they test the real implementation without spawning a subprocess.  The test
isolation strategy uses monkeypatch to restore os.environ after each test.

@decision DEC-CORE-004
@title load_dotenv bridges .env into os.environ before startup
@status accepted
@rationale See ada/__main__.py for full rationale. Tests here prove the two
    invariants: (a) .env values reach os.environ, (b) existing env vars win
    over .env values when override=False.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_env_file(path: Path, content: str) -> None:
    """Write a minimal .env file with the given content."""
    path.write_text(content)


# ---------------------------------------------------------------------------
# Core bridge behaviour
# ---------------------------------------------------------------------------

class TestDotenvBridge:

    def test_dotenv_value_reaches_os_environ(self, tmp_path, monkeypatch):
        """A value in .env must be visible via os.environ.get() after load_dotenv."""
        env_file = tmp_path / ".env"
        _write_env_file(env_file, "ANTHROPIC_API_KEY=sk-ant-test-key-123\n")

        # Ensure the var is not already set so we get a clean result
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        load_dotenv(dotenv_path=env_file, override=False)

        assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-test-key-123"

    def test_existing_env_var_wins_over_dotenv(self, tmp_path, monkeypatch):
        """override=False: shell-exported value must not be clobbered by .env."""
        env_file = tmp_path / ".env"
        _write_env_file(env_file, "ANTHROPIC_API_KEY=sk-ant-from-dotenv\n")

        # Simulate a shell-exported value already present
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-shell")

        load_dotenv(dotenv_path=env_file, override=False)

        assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-from-shell"

    def test_openai_key_reaches_os_environ(self, tmp_path, monkeypatch):
        """OPENAI_API_KEY in .env must populate os.environ."""
        env_file = tmp_path / ".env"
        _write_env_file(env_file, "OPENAI_API_KEY=sk-openai-test\n")

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        load_dotenv(dotenv_path=env_file, override=False)

        assert os.environ.get("OPENAI_API_KEY") == "sk-openai-test"

    def test_ada_jwt_secret_reaches_os_environ(self, tmp_path, monkeypatch):
        """ADA_JWT_SECRET in .env must populate os.environ."""
        env_file = tmp_path / ".env"
        _write_env_file(env_file, "ADA_JWT_SECRET=super-secret-jwt-value\n")

        monkeypatch.delenv("ADA_JWT_SECRET", raising=False)

        load_dotenv(dotenv_path=env_file, override=False)

        assert os.environ.get("ADA_JWT_SECRET") == "super-secret-jwt-value"

    def test_vapid_private_key_reaches_os_environ(self, tmp_path, monkeypatch):
        """ADA_VAPID_PRIVATE_KEY in .env must populate os.environ."""
        env_file = tmp_path / ".env"
        _write_env_file(env_file, "ADA_VAPID_PRIVATE_KEY=vapid-private-test\n")

        monkeypatch.delenv("ADA_VAPID_PRIVATE_KEY", raising=False)

        load_dotenv(dotenv_path=env_file, override=False)

        assert os.environ.get("ADA_VAPID_PRIVATE_KEY") == "vapid-private-test"

    def test_multiple_vars_all_loaded(self, tmp_path, monkeypatch):
        """Multiple secret vars in one .env file must all reach os.environ."""
        env_file = tmp_path / ".env"
        _write_env_file(
            env_file,
            "ANTHROPIC_API_KEY=sk-ant-multi\n"
            "ADA_JWT_SECRET=jwt-multi\n"
            "ADA_VAPID_PRIVATE_KEY=vapid-multi\n",
        )

        for var in ("ANTHROPIC_API_KEY", "ADA_JWT_SECRET", "ADA_VAPID_PRIVATE_KEY"):
            monkeypatch.delenv(var, raising=False)

        load_dotenv(dotenv_path=env_file, override=False)

        assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-multi"
        assert os.environ.get("ADA_JWT_SECRET") == "jwt-multi"
        assert os.environ.get("ADA_VAPID_PRIVATE_KEY") == "vapid-multi"

    def test_missing_dotenv_file_does_not_raise(self, tmp_path, monkeypatch):
        """load_dotenv() with a nonexistent path must not raise — server must boot."""
        nonexistent = tmp_path / "does_not_exist.env"
        # Should complete without exception
        load_dotenv(dotenv_path=nonexistent, override=False)


# ---------------------------------------------------------------------------
# ClaudeConfig integration: api_key property reads from os.environ
# ---------------------------------------------------------------------------

class TestClaudeConfigReadsFromEnviron:
    """Verify that ClaudeConfig.api_key (the real property) picks up the bridged value."""

    def test_claude_api_key_property_sees_bridged_value(self, tmp_path, monkeypatch):
        """After load_dotenv(), ClaudeConfig.api_key must return the .env value."""
        from ada.core.config import ClaudeConfig

        env_file = tmp_path / ".env"
        _write_env_file(env_file, "ANTHROPIC_API_KEY=sk-ant-via-bridge\n")

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        load_dotenv(dotenv_path=env_file, override=False)

        cfg = ClaudeConfig()
        assert cfg.api_key == "sk-ant-via-bridge"

    def test_shell_exported_key_still_wins(self, tmp_path, monkeypatch):
        """Shell export must beat .env even after load_dotenv() runs."""
        from ada.core.config import ClaudeConfig

        env_file = tmp_path / ".env"
        _write_env_file(env_file, "ANTHROPIC_API_KEY=sk-ant-from-dotenv\n")

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-shell")
        load_dotenv(dotenv_path=env_file, override=False)

        cfg = ClaudeConfig()
        assert cfg.api_key == "sk-ant-from-shell"
