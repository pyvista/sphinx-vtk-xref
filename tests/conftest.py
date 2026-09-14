"""Enable coverage collection for sphinx-build subprocesses.

``tests/test_vtk_role.py`` drives the ``:vtk:`` role by spawning
``sys.executable -msphinx`` in a subprocess. Without this hook the module's
code paths are measured only via the small direct-call tests, and the repo's
``--cov-fail-under`` gate would fail. Setting ``COVERAGE_PROCESS_START`` makes
coverage.py's ``.pth``-installed startup hook attach in every subprocess.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import NoReturn

import pytest
import requests

os.environ.setdefault(
    "COVERAGE_PROCESS_START",
    str(Path(__file__).resolve().parent.parent / "pyproject.toml"),
)

#: Text the ``:vtk:`` role logs when it cannot reach the VTK documentation.
UNREACHABLE_MESSAGE = "Could not reach the VTK documentation"

#: Reasons tests were skipped because vtk.org was unavailable.
_outages: list[str] = []

_config: pytest.Config | None = None


def pytest_configure(config: pytest.Config) -> None:
    """Keep the config so an outage can reach the coverage plugin."""
    global _config  # noqa: PLW0603
    _config = config


def _lift_coverage_gate() -> None:
    """Drop ``--cov-fail-under``, since skipped tests cover nothing."""
    plugin = _config.pluginmanager.get_plugin("_cov") if _config else None
    if plugin is not None:
        plugin.options.cov_fail_under = 0


def skip_if_unreachable(reason: str) -> NoReturn:
    """Skip the running test because vtk.org could not be reached."""
    _outages.append(reason)
    _lift_coverage_gate()
    pytest.skip(f"vtk.org is unavailable: {reason}")


def get_or_skip(url: str, **kwargs) -> requests.Response:
    """Fetch a URL, skipping the running test if vtk.org does not serve it."""
    try:
        response = requests.get(url, timeout=30, **kwargs)
        response.raise_for_status()
    except requests.RequestException as exc:
        skip_if_unreachable(f"{url} ({type(exc).__name__}: {exc})")
    return response


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    """Announce that vtk.org was unavailable and its tests were skipped."""
    if not _outages:
        return
    terminalreporter.write_sep(
        "=",
        f"vtk.org was unavailable: {len(_outages)} test(s) skipped, coverage gate lifted",
        yellow=True,
    )
    for reason in _outages:
        terminalreporter.write_line(f"  {reason}")
