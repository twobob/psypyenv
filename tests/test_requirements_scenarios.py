from __future__ import annotations

from pathlib import Path

import pytest

from psypyenv.models import PackageRequirement
from psypyenv.requirements import parse_requirements


DATA_DIR = Path(__file__).parent / "data" / "requirements_samples"
PYPROJECT_DIR = Path(__file__).parent / "data" / "pyproject_samples"


@pytest.mark.parametrize(
    "filename",
    sorted(path.name for path in DATA_DIR.glob("*.txt")),
)
def test_parse_requirement_samples(filename: str) -> None:
    expectations = {
        "scenario01_basic.txt": {"names": ["numpy", "pandas"], "indexes": []},
        "scenario02_comments_whitespace.txt": {"names": ["scipy"], "indexes": []},
        "scenario03_extra_index.txt": {
            "names": ["rich"],
            "indexes": ["https://example.com/simple"],
        },
        "scenario04_invalid_entry.txt": {"names": ["black"], "indexes": []},
        "scenario05_http_egg.txt": {"names": ["custompkg"], "indexes": []},
        "scenario06_editable_git.txt": {"names": ["gitpkg"], "indexes": []},
        "scenario07_direct_reference.txt": {"names": ["samplepkg"], "indexes": []},
        "scenario08_with_marker.txt": {
            "names": ["uvloop"],
            "indexes": [],
            "marker": 'sys_platform == "linux"',
        },
        "scenario09_with_extras.txt": {"names": ["django"], "indexes": []},
        "scenario10_skip_git_without_egg.txt": {"names": [], "indexes": []},
    }
    assert len(expectations) == 10, "Expected metadata for ten requirement scenarios"

    sample_path = DATA_DIR / filename
    requirements, indexes = parse_requirements(sample_path)

    expected = expectations[filename]
    assert [requirement.name for requirement in requirements] == expected["names"]
    assert indexes == expected["indexes"]

    if "marker" in expected and expected["names"]:
        assert requirements[0].marker == expected["marker"]

    for requirement in requirements:
        assert isinstance(requirement, PackageRequirement)
        assert requirement.original is not None
        assert requirement.original.strip() != ""


def test_sample_directory_contains_ten_files() -> None:
    sample_files = list(DATA_DIR.glob("*.txt"))
    assert len(sample_files) == 10
    assert all(file.is_file() for file in sample_files)


def test_parse_pyproject_dependencies() -> None:
    sample_path = PYPROJECT_DIR / "pep621_basic.toml"

    requirements, indexes = parse_requirements(sample_path)

    assert [requirement.name for requirement in requirements] == [
        "numpy",
        "pandas",
        "requests",
    ]
    assert indexes == []

    markers = [requirement.marker for requirement in requirements]
    assert markers == [None, 'python_version >= "3.10"', None]
