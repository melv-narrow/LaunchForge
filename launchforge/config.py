"""Pydantic v2 configuration models and TOML loading for LaunchForge."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator


class ProgramConfig(BaseModel):
    """Configuration for a single managed program."""

    name: str
    path: str
    delay: float = Field(default=0.0, ge=0)
    retry_delay: float = Field(default=5.0, ge=0)
    args: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    group: str = "default"
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Program name must not be empty")
        return v

    @field_validator("path")
    @classmethod
    def path_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Program path must not be empty")
        return v


class SettingsConfig(BaseModel):
    """Global LaunchForge settings."""

    health_check_interval: float = Field(default=30.0, ge=1)
    max_retries: int = Field(default=3, ge=0)
    profile: str = "default"
    log_file: str = "launchforge.log"
    log_max_bytes: int = Field(default=5_242_880, ge=0)  # 5 MB
    log_backup_count: int = Field(default=3, ge=0)


class LaunchForgeConfig(BaseModel):
    """Root configuration model for LaunchForge."""

    settings: SettingsConfig = Field(default_factory=SettingsConfig)
    programs: list[ProgramConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dependency_names(self) -> LaunchForgeConfig:
        names = {p.name for p in self.programs}
        for program in self.programs:
            for dep in program.depends_on:
                if dep not in names:
                    raise ValueError(
                        f"Program '{program.name}' depends on '{dep}', "
                        f"which is not defined in the config."
                    )
        return self

    @model_validator(mode="after")
    def validate_no_circular_dependencies(self) -> LaunchForgeConfig:
        """Detect circular dependency chains."""
        graph: dict[str, list[str]] = {p.name: list(p.depends_on) for p in self.programs}

        def has_cycle(node: str, visited: set[str], stack: set[str]) -> bool:
            visited.add(node)
            stack.add(node)
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor, visited, stack):
                        return True
                elif neighbor in stack:
                    return True
            stack.discard(node)
            return False

        visited: set[str] = set()
        for name in graph:
            if name not in visited and has_cycle(name, visited, set()):
                raise ValueError(
                    f"Circular dependency detected involving program '{name}'."
                )
        return self


def load_config(path: Path, profile: str | None = None) -> LaunchForgeConfig:
    """Load and validate a TOML configuration file.

    Args:
        path: Path to the ``config.toml`` file.
        profile: Optional profile name to filter programs by (``group`` field).

    Returns:
        A validated :class:`LaunchForgeConfig` instance.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If the config is invalid.
    """
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    config = LaunchForgeConfig.model_validate(raw)

    # Override profile from CLI flag when provided
    if profile is not None:
        config.settings.profile = profile

    # Filter programs by profile/group if a non-default profile is active
    active_profile = config.settings.profile
    if active_profile and active_profile != "default":
        config.programs = [
            p for p in config.programs if p.group == active_profile or not p.group
        ]

    return config
