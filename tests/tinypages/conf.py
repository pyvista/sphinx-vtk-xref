from __future__ import annotations
import datetime
from pathlib import Path
import sys


sys.path.append(str(Path(__file__).parent))

# -- General configuration ------------------------------------------------

templates_path = ["_templates"]
source_suffix = ".rst"
root_doc = "index"
project = "tinypages"
year = datetime.datetime.now(tz=datetime.timezone.utc).date().year
copyright = f"2021-{year}, PyVista developers"  # noqa: A001
author = "PyVista developers"
version = "0.1"
release = "0.1"
exclude_patterns = ["_build"]
pygments_style = "sphinx"

extensions = ["sphinx_vtk_xref", "sphinx.ext.autosummary"]

# -- Options for HTML output ----------------------------------------------

html_static_path = ["_static"]
