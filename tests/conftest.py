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

os.environ.setdefault(
    "COVERAGE_PROCESS_START",
    str(Path(__file__).resolve().parent.parent / "pyproject.toml"),
)
