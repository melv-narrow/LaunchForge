"""Tests for launchforge.config — Pydantic models and TOML loading."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from launchforge.config import (
    LaunchForgeConfig,
    ProgramConfig,
    SettingsConfig,
    load_config,
)

# ---------------------------------------------------------------------------
# ProgramConfig validation
# ---------------------------------------------------------------------------

class TestProgramConfig:
    def test_minimal_valid(self):
        prog = ProgramConfig(name="App", path="/usr/bin/app")
        assert prog.name == "App"
        assert prog.delay == 0.0
        assert prog.retry_delay == 5.0
        assert prog.args == []
        assert prog.depends_on == []
        assert prog.group == "default"
        assert prog.enabled is True

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="name must not be empty"):
            ProgramConfig(name="  ", path="/usr/bin/app")

    def test_empty_path_raises(self):
        with pytest.raises(ValueError, match="path must not be empty"):
            ProgramConfig(name="App", path="  ")

    def test_negative_delay_raises(self):
        with pytest.raises(ValueError):
            ProgramConfig(name="App", path="/bin/app", delay=-1)

    def test_args_list(self):
        prog = ProgramConfig(name="App", path="/bin/app", args=["--flag", "value"])
        assert prog.args == ["--flag", "value"]


# ---------------------------------------------------------------------------
# SettingsConfig validation
# ---------------------------------------------------------------------------

class TestSettingsConfig:
    def test_defaults(self):
        s = SettingsConfig()
        assert s.health_check_interval == 30.0
        assert s.max_retries == 3
        assert s.profile == "default"

    def test_custom_values(self):
        s = SettingsConfig(health_check_interval=60, max_retries=5, profile="gaming")
        assert s.health_check_interval == 60.0
        assert s.max_retries == 5
        assert s.profile == "gaming"

    def test_interval_below_1_raises(self):
        with pytest.raises(ValueError):
            SettingsConfig(health_check_interval=0)


# ---------------------------------------------------------------------------
# LaunchForgeConfig validation
# ---------------------------------------------------------------------------

class TestLaunchForgeConfig:
    def test_empty_programs(self):
        cfg = LaunchForgeConfig()
        assert cfg.programs == []

    def test_valid_dependency(self):
        cfg = LaunchForgeConfig(
            programs=[
                ProgramConfig(name="A", path="/bin/a"),
                ProgramConfig(name="B", path="/bin/b", depends_on=["A"]),
            ]
        )
        assert len(cfg.programs) == 2

    def test_unknown_dependency_raises(self):
        with pytest.raises(ValueError, match="depends on 'Ghost'"):
            LaunchForgeConfig(
                programs=[
                    ProgramConfig(name="App", path="/bin/app", depends_on=["Ghost"]),
                ]
            )

    def test_circular_dependency_raises(self):
        with pytest.raises(ValueError, match="Circular dependency"):
            LaunchForgeConfig(
                programs=[
                    ProgramConfig(name="A", path="/bin/a", depends_on=["B"]),
                    ProgramConfig(name="B", path="/bin/b", depends_on=["A"]),
                ]
            )


# ---------------------------------------------------------------------------
# load_config — TOML file loading
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def _write_toml(self, tmp_path: Path, content: str) -> Path:
        p = tmp_path / "config.toml"
        p.write_text(textwrap.dedent(content))
        return p

    def test_load_minimal(self, tmp_path: Path):
        p = self._write_toml(tmp_path, """\
            [settings]
            profile = "default"

            [[programs]]
            name = "App"
            path = "/usr/bin/app"
        """)
        cfg = load_config(p)
        assert len(cfg.programs) == 1
        assert cfg.programs[0].name == "App"

    def test_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.toml")

    def test_profile_override_filters_programs(self, tmp_path: Path):
        p = self._write_toml(tmp_path, """\
            [settings]
            profile = "default"

            [[programs]]
            name = "AudioApp"
            path = "/bin/audio"
            group = "audio"

            [[programs]]
            name = "GameApp"
            path = "/bin/game"
            group = "gaming"
        """)
        cfg = load_config(p, profile="audio")
        assert len(cfg.programs) == 1
        assert cfg.programs[0].name == "AudioApp"

    def test_default_profile_returns_all(self, tmp_path: Path):
        p = self._write_toml(tmp_path, """\
            [settings]
            profile = "default"

            [[programs]]
            name = "A"
            path = "/bin/a"
            group = "audio"

            [[programs]]
            name = "B"
            path = "/bin/b"
            group = "gaming"
        """)
        cfg = load_config(p)
        assert len(cfg.programs) == 2

    def test_settings_values(self, tmp_path: Path):
        p = self._write_toml(tmp_path, """\
            [settings]
            health_check_interval = 60
            max_retries = 5
            profile = "work"
        """)
        cfg = load_config(p)
        # profile "work" doesn't match any group so all programs (none) returned
        assert cfg.settings.health_check_interval == 60.0
        assert cfg.settings.max_retries == 5

    def test_load_full_config_toml(self):
        """Ensure the shipped config.toml is valid."""
        repo_root = Path(__file__).parent.parent
        cfg_path = repo_root / "config.toml"
        if cfg_path.exists():
            cfg = load_config(cfg_path)
            assert len(cfg.programs) > 0
