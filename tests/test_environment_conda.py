from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from psypyenv import cli, config, environment
from psypyenv.models import EnvironmentReport
from psypyenv.requirements import parse_requirement_text


def test_find_conda_executable_returns_none_when_absent(monkeypatch) -> None:
    monkeypatch.setattr(environment, "load_conda_path", lambda: None)
    monkeypatch.setattr(environment, "save_conda_path", lambda path: None)
    monkeypatch.setattr(environment, "load_conda_search_paths", lambda: [])
    monkeypatch.setattr(environment, "_default_conda_locations", lambda: [])
    monkeypatch.delenv("CONDA_EXE", raising=False)
    monkeypatch.setenv("PATH", "")

    result = environment.find_conda_executable()

    assert result is None


def test_find_conda_executable_uses_custom_paths(tmp_path, monkeypatch) -> None:
    custom_dir = tmp_path / "custom"
    custom_dir.mkdir()
    executable_name = "conda.exe" if sys.platform == "win32" else "conda"
    candidate = custom_dir / executable_name
    candidate.write_text("#!/bin/sh\necho 'conda 24.1'\n")
    candidate.chmod(0o755)

    saves: list[str] = []

    monkeypatch.setattr(environment, "load_conda_path", lambda: None)
    monkeypatch.setattr(environment, "save_conda_path", lambda path: saves.append(path))
    monkeypatch.setattr(environment, "load_conda_search_paths", lambda: [str(custom_dir)])
    monkeypatch.setattr(environment, "_default_conda_locations", lambda: [])
    monkeypatch.delenv("CONDA_EXE", raising=False)
    monkeypatch.setenv("PATH", "")

    resolved = environment.find_conda_executable()

    assert resolved == candidate.resolve()
    assert saves and Path(saves[0]) == resolved


def test_cli_include_conda_envs_reports_and_caches(tmp_path, monkeypatch, capsys, caplog) -> None:
    requirements_path = tmp_path / "requirements.txt"
    requirements_path.write_text("requests==2.31.0\n")

    settings_path = tmp_path / "settings.ini"
    monkeypatch.setattr(config, "_config_file", lambda: settings_path)

    fake_conda = tmp_path / "conda"
    fake_conda.write_text("#!/bin/sh\n")
    fake_conda.chmod(0o755)
    monkeypatch.setattr(cli, "find_conda_executable", lambda candidate=None: fake_conda)

    env_root = tmp_path / "envs"
    env_root.mkdir()
    python_paths: dict[Path, Path] = {}
    environments = []
    for name in ("alpha", "beta"):
        env_dir = env_root / name
        env_dir.mkdir()
        python_path = env_dir / "python"
        python_path.write_text("#!/bin/sh\n")
        python_path.chmod(0o755)
        environments.append(env_dir)
        python_paths[env_dir] = python_path

    manual_env = tmp_path / "manual" / "custom"
    manual_env.mkdir(parents=True)
    manual_python = manual_env / "python"
    manual_python.write_text("#!/bin/sh\n")
    manual_python.chmod(0o755)

    monkeypatch.setattr(cli, "list_conda_environments", lambda _conda: environments)
    monkeypatch.setattr(cli, "resolve_python_executable", lambda env: python_paths.get(env))

    def fake_inspect(name: str, path: Path, requirements):
        return EnvironmentReport(
            name=name,
            python_executable=path,
            python_version="3.10",
            compatibility=100.0,
            matching=[requirement.name for requirement in requirements],
            missing=[],
            mismatched=[],
            total_requirements=len(requirements),
        )

    monkeypatch.setattr(cli, "inspect_environment", fake_inspect)

    caplog.set_level(logging.INFO)
    exit_code = cli.main(
        [
            "--requirements",
            str(requirements_path),
            "--include-conda-envs",
            "--show-paths",
            "--log-level",
            "INFO",
            "--register-conda-env",
            f"gamma={manual_python}",
        ]
    )
    assert exit_code == 0
    first_output = capsys.readouterr().out
    assert "Environment compatibility summary" in first_output
    assert "alpha" in first_output and "beta" in first_output

    cached_envs = config.load_cached_conda_envs()
    expected_alpha = ("alpha", str(python_paths[environments[0]].resolve()))
    expected_beta = ("beta", str(python_paths[environments[1]].resolve()))
    assert expected_alpha in cached_envs
    assert expected_beta in cached_envs

    assert any("Scanning conda environment 1/2" in message for message in caplog.messages)

    assert any("gamma" in name for name, _ in cached_envs)

    caplog.clear()
    exit_code = cli.main(
        [
            "--requirements",
            str(requirements_path),
            "--include-conda-envs",
            "--show-paths",
            "--log-level",
            "INFO",
            "--refresh-conda-envs",
        ]
    )
    assert exit_code == 0
    capsys.readouterr()
    assert any("Refreshing cached conda environments before scanning." in message for message in caplog.messages)
    assert all("Reusing" not in message for message in caplog.messages)

    refreshed_cache = config.load_cached_conda_envs()
    assert expected_alpha in refreshed_cache
    assert expected_beta in refreshed_cache
    assert all(name != "gamma" for name, _ in refreshed_cache)


def test_inspect_environment_uses_real_python(discovered_environments) -> None:
    requirements = parse_requirement_text(
        [
            "pip>=9",
            "psypyenv-non-existent-demo-package==0.0.1",
        ]
    )

    for env_name, python_path in discovered_environments:
        report = environment.inspect_environment(env_name, python_path, requirements)

        assert report.total_requirements == 2
        assert "pip" in report.matching
        assert "psypyenv-non-existent-demo-package" in report.missing
        assert report.compatibility == pytest.approx(50.0, abs=0.1)
        assert report.python_version is not None


def test_cli_main_reports_discovered_environments(discovered_environments, capsys) -> None:
    sample_path = Path(__file__).parent / "data" / "requirements_samples" / "scenario09_with_extras.txt"

    exit_code = cli.main([
        "--requirements",
        str(sample_path),
        "--include-conda-envs",
        "--refresh-conda-envs",
    ])
    captured = capsys.readouterr()

    assert exit_code == 0
    output = captured.out
    assert "Environment compatibility summary" in output
    for env_name, _ in discovered_environments:
        assert env_name in output
    assert output.count("Compatibility:") == len(discovered_environments)
    assert output.lower().count("missing: django") == len(discovered_environments)


def test_cli_accepts_positional_requirement_path(discovered_environments, capsys) -> None:
    sample_path = Path(__file__).parent / "data" / "pyproject_samples" / "pep621_basic.toml"

    exit_code = cli.main([
        str(sample_path),
        "--include-conda-envs",
        "--refresh-conda-envs",
    ])

    captured = capsys.readouterr()

    assert exit_code == 0
    output = captured.out
    assert "Environment compatibility summary" in output
    for env_name, _ in discovered_environments:
        assert env_name in output
