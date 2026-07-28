"""Sphinx role for linking to VTK documentation."""

from __future__ import annotations
from subprocess import run, PIPE
from pathlib import Path
from http import HTTPStatus
import re
import subprocess
import sys
import textwrap
import filecmp

from bs4 import BeautifulSoup
import pytest
import requests

from sphinx_vtk_xref import _find_member_anchor
from sphinx_vtk_xref import _vtk_class_url

GET_SPACING_ANCHOR = "ae6ebee83577b2d58c393a0df2f15b67d"
GET_SPACING_URL = f"{_vtk_class_url('vtkImageData')}#{GET_SPACING_ANCHOR}"
SET_ORIGIN_ANCHOR = "ad18d146c5e2471876e5d9c6242ac1544"
SET_ORIGIN_URL = f"{_vtk_class_url('vtkImageData')}#{SET_ORIGIN_ANCHOR}"

EVENT_IDS_ANCHOR = "a59a8690330ebcb1af6b66b0f3121f8fe"
EVENT_IDS_URL = f"{_vtk_class_url('vtkCommand')}#{EVENT_IDS_ANCHOR}"

ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[.*?m")


@pytest.fixture(scope="module")
def vtk_polydata_html():
    """Fixture that fetches HTML for vtkPolyData once per test module."""
    response = requests.get(_vtk_class_url("vtkPolyData"), timeout=30)
    response.raise_for_status()
    return response.text


def test_find_member_anchor(vtk_polydata_html):
    anchor = _find_member_anchor(vtk_polydata_html, "Foo")
    assert anchor is None

    anchor = _find_member_anchor(vtk_polydata_html, "GetVerts")
    assert isinstance(anchor, str)

    # Confirm that the anchor appears in the HTML
    assert f'id="{anchor}"' in vtk_polydata_html

    # Confirm that the final URL with anchor resolves
    full_url = f"{_vtk_class_url('vtkPolyData')}#{anchor}"
    response = requests.get(full_url, timeout=30, allow_redirects=True)
    assert response.status_code == HTTPStatus.OK


def make_temp_doc_project(tmp_path, sample_text: str, conf_extras: str = ""):
    """Set up a minimal Sphinx project that uses the :vtk: role directly in index.rst."""
    src = tmp_path / "src"
    src.mkdir()

    # conf.py with the extension enabled
    conf = "extensions = ['sphinx_vtk_xref']\n" + conf_extras
    (src / "conf.py").write_text(conf)

    # Write index.rst with sample text
    lines = [
        "Test Page",
        "=========",
        "",
        sample_text.strip(),
        "",
    ]
    (src / "index.rst").write_text("\n".join(lines))

    return src


@pytest.mark.parametrize(
    ("code_block", "expected_links", "expected_warning"),
    [
        (  # Valid cases (get/set methods and enum)
            textwrap.dedent("""
            :vtk:`vtkImageData.GetSpacing`.
            :vtk:`vtkImageData.SetOrigin`
            :vtk:`vtkCommand.EventIds`
            """),
            {
                GET_SPACING_URL: "vtkImageData.GetSpacing",
                SET_ORIGIN_URL: "vtkImageData.SetOrigin",
                EVENT_IDS_URL: "vtkCommand.EventIds",
            },
            None,
        ),
        (  # Use an explicit title
            ":vtk:`Get Image Spacing<vtkImageData.GetSpacing>`",
            {GET_SPACING_URL: "Get Image Spacing"},
            None,
        ),
        (  # Use a tilde
            ":vtk:`~vtkImageData.GetSpacing`",
            {GET_SPACING_URL: "GetSpacing"},
            None,
        ),
        (  # Valid class but too many member parts
            ":vtk:`vtkImageData.GetSpacing.SomethingElse`",
            {
                GET_SPACING_URL: "vtkImageData.GetSpacing.SomethingElse",
            },
            "Too many nested members in VTK reference: 'vtkImageData.GetSpacing.SomethingElse'. Interpreting as 'vtkImageData.GetSpacing', ignoring: 'SomethingElse' [sphinx-vtk-xref]",
        ),
        (  # Valid class, invalid method
            ":vtk:`vtkImageData.FakeMethod`",
            {_vtk_class_url("vtkImageData"): "vtkImageData.FakeMethod"},
            "VTK method anchor not found for: 'vtkImageData.FakeMethod' → https://vtk.org/doc/nightly/html/classvtkImageData.html#<anchor>, the class URL is used instead. [sphinx-vtk-xref]",
        ),
        (  # Invalid class
            ":vtk:`NonExistentClass`",
            {_vtk_class_url("NonExistentClass"): "NonExistentClass"},
            "Invalid VTK class reference: 'NonExistentClass' → https://vtk.org/doc/nightly/html/classNonExistentClass.html (HTTP 404 Not Found) [sphinx-vtk-xref]",
        ),
        (  # Test caching with valid class and invalid member
            textwrap.dedent("""
            :vtk:`vtkImageData`
            :vtk:`vtkImageData`
            :vtk:`vtkImageData.FakeEnum`
            :vtk:`vtkImageData.FakeEnum`
            """),
            {
                # Only one URL expected: the url for a bad member falls back to the class URL
                _vtk_class_url("vtkImageData"): "vtkImageData",
            },
            "VTK method anchor not found for: 'vtkImageData.FakeEnum' → https://vtk.org/doc/nightly/html/classvtkImageData.html#<anchor>, the class URL is used instead. [sphinx-vtk-xref]",
        ),
        (  # Test caching with invalid class and invalid member
            textwrap.dedent("""
           :vtk:`vtkFooBar`
           :vtk:`vtkFooBar`
           :vtk:`vtkFooBar.Baz`
           :vtk:`vtkFooBar.Baz`
           """),
            {
                _vtk_class_url("vtkFooBar"): "vtkFooBar",
            },
            "Invalid VTK class reference: 'vtkFooBar' → https://vtk.org/doc/nightly/html/classvtkFooBar.html (HTTP 404 Not Found) [sphinx-vtk-xref]",
        ),
    ],
)
def test_vtk_role(tmp_path, code_block, expected_links, expected_warning):
    doc_project = make_temp_doc_project(tmp_path, code_block)
    build_dir = tmp_path / "_build"
    build_html_dir = build_dir / "html"

    result = subprocess.run(  # noqa: UP022
        [
            sys.executable,
            "-msphinx",
            "-b",
            "html",
            str(doc_project),
            str(build_html_dir),
            "-W",
            "--keep-going",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # need to explicitly decode the output with UTF-8 to avoid UnicodeDecodeError
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    print("STDOUT:\n", stdout)
    print("STDERR:\n", stderr)

    if expected_warning:
        assert result.returncode != 0, "Expected warning but build succeeded"

        # Verify warning message. Skip check on Windows due to Unicode/color output differences
        if not sys.platform.startswith("win"):
            assert expected_warning in stderr, (
                f"Expected warning:\n{expected_warning!r}\n\nBut got:\n{stderr}"
            )
    else:
        assert result.returncode == 0, "Unexpected failure in Sphinx build"

    index_html = build_html_dir / "index.html"
    assert index_html.exists()
    html = index_html.read_text(encoding="utf-8")

    # Parse HTML and validate all expected links
    soup = BeautifulSoup(html, "html.parser")
    for href, expected_text in expected_links.items():
        link = soup.find("a", href=href)
        assert link is not None, f'Expected link with href="{href}" not found'
        assert link.text == expected_text, (
            f'Expected link text "{expected_text}", got "{link.text}"'
        )


def test_ignored_status_codes(tmp_path):
    """A status code in ``sphinx_vtk_xref_ignored_status_codes`` must not fail ``-W`` builds.

    Asking vtk.org for a non-existent class returns a 404. Adding 404 to the
    ignored set should turn that into a non-fatal info log so ``-W`` still passes.
    """
    code_block = ":vtk:`NonExistentClass`"
    conf_extras = "sphinx_vtk_xref_ignored_status_codes = {404}\n"
    doc_project = make_temp_doc_project(tmp_path, code_block, conf_extras=conf_extras)
    build_html_dir = tmp_path / "_build" / "html"

    result = subprocess.run(  # noqa: UP022
        [
            sys.executable,
            "-msphinx",
            "-b",
            "html",
            str(doc_project),
            str(build_html_dir),
            "-W",
            "--keep-going",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    print("STDOUT:\n", stdout)
    print("STDERR:\n", stderr)

    assert result.returncode == 0, "Build should not fail when 404 is ignored"

    if not sys.platform.startswith("win"):
        # The old "Invalid VTK class reference" warning must not appear.
        assert "Invalid VTK class reference" not in stderr

    # The class URL (unvalidated) should still land in the HTML as a fallback link.
    html = (build_html_dir / "index.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    link = soup.find("a", href=_vtk_class_url("NonExistentClass"))
    assert link is not None


def _build_docs(src, build_dir, jobs):
    cmd = [
        sys.executable,
        "-msphinx",
        "-b",
        "html",
        str(src),
        str(build_dir / "html"),
        "-d",
        str(build_dir / "doctrees"),
        f"-j{jobs}",
        "-W",
        "--keep-going",
    ]
    return run(cmd, stdout=PIPE, stderr=PIPE, text=True)


def _check_html_content(html_path, expected_links):
    """Check if the expected links are in the generated HTML."""
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    for expected_link in expected_links:
        link = soup.find("a", href=expected_link["href"])
        assert link is not None, f"Expected link not found: {expected_link['href']}"
        assert link.text.strip() == expected_link["text"], (
            f'Expected link text "{expected_link["text"]}", but got "{link.text.strip()}"'
        )


def test_build(tmp_path):
    tinypages_dir = Path(__file__).parent / "tinypages"

    build_parallel = tmp_path / "build_parallel"
    build_serial = tmp_path / "build_serial"

    res_parallel = _build_docs(tinypages_dir, build_parallel, "auto")
    assert res_parallel.returncode == 0, f"Parallel build failed:\n{res_parallel.stderr}"

    res_serial = _build_docs(tinypages_dir, build_serial, 1)
    assert res_serial.returncode == 0, f"Serial build failed:\n{res_serial.stderr}"

    html_parallel = build_parallel / "html" / "index.html"
    html_serial = build_serial / "html" / "index.html"

    assert filecmp.cmp(html_parallel, html_serial, shallow=False), (
        "Parallel and serial outputs differ"
    )

    # Verify that both parallel and serial outputs are the same
    html_parallel = build_parallel / "html" / "index.html"
    html_serial = build_serial / "html" / "index.html"

    # Check for expected content in the output HTML
    expected_links = [
        {
            "href": "https://vtk.org/doc/nightly/html/classvtkUnstructuredGrid.html#a390dfe6352f0bba3bb17be5d7a5e83e7",
            "text": "vtkUnstructuredGrid.GetCells",
        },
        {
            "href": "https://vtk.org/doc/nightly/html/classvtkPolyData.html#a34a0f2c07e4464a32cfb30e946a78be2",
            "text": "SetVerts",
        },
        {
            "href": "https://vtk.org/doc/nightly/html/classvtkPolyData.html#a00a291f8dc80f58fb451d3227ab3fb65",
            "text": "Get Triangle Strips",
        },
    ]

    _check_html_content(html_parallel, expected_links)
    _check_html_content(html_serial, expected_links)

    assert filecmp.cmp(html_parallel, html_serial, shallow=False), (
        "Parallel and serial outputs differ"
    )
