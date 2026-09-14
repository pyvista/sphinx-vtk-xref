"""Sphinx role for linking to VTK documentation."""

from __future__ import annotations
from subprocess import run
from pathlib import Path
from http import HTTPStatus
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch
import json
import os
import re
import sys
import textwrap
import filecmp

from bs4 import BeautifulSoup
from docutils import frontend
from docutils import nodes
from docutils import utils
from docutils.parsers import rst
from sphinx.application import Sphinx
import pytest
import requests

import conftest
from conftest import UNREACHABLE_MESSAGE
from conftest import get_or_skip
from conftest import skip_if_unreachable
from sphinx_vtk_xref import URLS_ENV_VAR
from sphinx_vtk_xref import DEFAULT_IGNORED_STATUS_CODES
from sphinx_vtk_xref import VTKRole
from sphinx_vtk_xref import _append_url
from sphinx_vtk_xref import _find_member_anchor
from sphinx_vtk_xref import _read_urls
from sphinx_vtk_xref import _split_reference
from sphinx_vtk_xref import _vtk_class_url

GET_SPACING_ANCHOR = "ae6ebee83577b2d58c393a0df2f15b67d"
GET_SPACING_URL = f"{_vtk_class_url('vtkImageData')}#{GET_SPACING_ANCHOR}"
SET_ORIGIN_ANCHOR = "ad18d146c5e2471876e5d9c6242ac1544"
SET_ORIGIN_URL = f"{_vtk_class_url('vtkImageData')}#{SET_ORIGIN_ANCHOR}"

EVENT_IDS_ANCHOR = "a59a8690330ebcb1af6b66b0f3121f8fe"
EVENT_IDS_URL = f"{_vtk_class_url('vtkCommand')}#{EVENT_IDS_ANCHOR}"

BLEND_MODES_ANCHOR = "aac00c48c3211f5dba0ca98c7a028e409"
COMPOSITE_BLEND_ANCHOR = f"{BLEND_MODES_ANCHOR}a92f6946039dfe09ac64649a5f661d7bf"
COMPOSITE_BLEND_URL = f"{_vtk_class_url('vtkVolumeMapper')}#{COMPOSITE_BLEND_ANCHOR}"
GET_BLEND_MODE_ANCHOR = "ab0d85bd1de808a39ac802f84de3ed1b1"

# ``Round`` is a value of the scoped ``enum class vtkProperty::Point2DShapeType``.
ROUND_ANCHOR = "a523ae84669eb187a1a24c08b7ec0e74fab7f41fc1412ad2ee75e9b2635d3b9d5c"
ROUND_URL = f"{_vtk_class_url('vtkProperty')}#{ROUND_ANCHOR}"

#: Spellings that a reasonable user may write, and the anchor each resolves to.
#: Each renders with its target as the link text.
REFERENCE_SPELLINGS = {
    "vtkVolumeMapper::COMPOSITE_BLEND": COMPOSITE_BLEND_URL,
    "vtkVolumeMapper.BlendModes.COMPOSITE_BLEND": COMPOSITE_BLEND_URL,
    "vtkVolumeMapper::BlendModes::COMPOSITE_BLEND": COMPOSITE_BLEND_URL,
    "vtkProperty.Point2DShapeType.Round": ROUND_URL,
    "vtkProperty::Point2DShapeType::Round": ROUND_URL,
    "vtkImageData.GetSpacing()": GET_SPACING_URL,
    "vtkImageData::GetSpacing": GET_SPACING_URL,
    "vtkImageData::GetSpacing()": GET_SPACING_URL,
}

ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[.*?m")


@pytest.fixture(scope="module")
def vtk_polydata_html():
    """Fixture that fetches HTML for vtkPolyData once per test module."""
    return get_or_skip(_vtk_class_url("vtkPolyData")).text


def test_find_member_anchor(vtk_polydata_html):
    anchor = _find_member_anchor(vtk_polydata_html, "Foo")
    assert anchor is None

    anchor = _find_member_anchor(vtk_polydata_html, "GetVerts")
    assert isinstance(anchor, str)

    # Confirm that the anchor appears in the HTML
    assert f'id="{anchor}"' in vtk_polydata_html

    # Confirm that the final URL with anchor resolves
    full_url = f"{_vtk_class_url('vtkPolyData')}#{anchor}"
    assert get_or_skip(full_url, allow_redirects=True).status_code == HTTPStatus.OK


@pytest.fixture(scope="module")
def vtk_volume_mapper_html():
    """Fixture that fetches HTML for vtkVolumeMapper once per test module."""
    return get_or_skip(_vtk_class_url("vtkVolumeMapper")).text


def test_find_enumerator_anchor(vtk_volume_mapper_html):
    """Enumerators resolve to their own anchor, without disturbing method lookups."""
    # Enumerators live in a table inside the enum's memitem block, not in a memtitle.
    anchor = _find_member_anchor(vtk_volume_mapper_html, "COMPOSITE_BLEND")
    assert anchor == COMPOSITE_BLEND_ANCHOR
    assert f'id="{anchor}"' in vtk_volume_mapper_html

    # Confirm that the final URL with anchor resolves
    full_url = f"{_vtk_class_url('vtkVolumeMapper')}#{anchor}"
    assert get_or_skip(full_url, allow_redirects=True).status_code == HTTPStatus.OK

    # The enclosing enum is still reachable through its memtitle header
    assert _find_member_anchor(vtk_volume_mapper_html, "BlendModes") == BLEND_MODES_ANCHOR

    # Methods are unaffected
    assert _find_member_anchor(vtk_volume_mapper_html, "GetBlendMode") == GET_BLEND_MODE_ANCHOR

    # An unknown enumerator-looking name is still unresolved
    assert _find_member_anchor(vtk_volume_mapper_html, "FAKE_BLEND") is None


@pytest.fixture(scope="module")
def vtk_selection_node_html():
    """Fixture that fetches HTML for vtkSelectionNode once per test module."""
    return get_or_skip(_vtk_class_url("vtkSelectionNode")).text


def test_exact_member_name_is_preferred(vtk_volume_mapper_html, vtk_selection_node_html):
    """An exact member name wins over the substring fallback, which still applies."""
    # ``BlendMode`` is a protected attribute whose name is a substring of the
    # ``BlendModes`` enum's memtitle.
    blend_mode = _find_member_anchor(vtk_volume_mapper_html, "BlendMode")
    assert blend_mode is not None
    assert blend_mode != BLEND_MODES_ANCHOR

    # An enum value also wins over a method that merely contains its name.
    cell = _find_member_anchor(vtk_selection_node_html, "CELL")
    cellgrid = _find_member_anchor(vtk_selection_node_html, "CELLGRID_CELL_TYPE_INDEX")
    assert cell is not None
    assert cellgrid is not None
    assert cell != cellgrid

    # Names with no exact match still resolve by substring, as before.
    assert _find_member_anchor(vtk_volume_mapper_html, "GetBlendMode()") == GET_BLEND_MODE_ANCHOR


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("vtkImageData", ("vtkImageData", [])),
        ("vtkImageData.", ("vtkImageData", [])),
        ("vtkImageData.GetSpacing", ("vtkImageData", ["GetSpacing"])),
        ("vtkImageData::GetSpacing", ("vtkImageData", ["GetSpacing"])),
        ("vtkImageData::GetSpacing()", ("vtkImageData", ["GetSpacing"])),
        ("vtkImageData.GetSpacing(double x)", ("vtkImageData", ["GetSpacing"])),
        (
            "vtkVolumeMapper::BlendModes::COMPOSITE_BLEND",
            ("vtkVolumeMapper", ["BlendModes", "COMPOSITE_BLEND"]),
        ),
    ],
)
def test_split_reference(target, expected):
    """References split on both ``.`` and ``::``, ignoring any argument list."""
    assert _split_reference(target) == expected


def test_reference_spellings(tmp_path):
    """Every spelling of a member a reasonable user may write resolves the same way."""
    targets = [*REFERENCE_SPELLINGS, "~vtkVolumeMapper::BlendModes::COMPOSITE_BLEND"]
    code_block = "\n".join(f":vtk:`{target}`\n" for target in targets)
    doc_project = make_temp_doc_project(tmp_path, code_block)
    build_dir = tmp_path / "_build"

    result = _build_docs(doc_project, build_dir)
    print("STDERR:\n", result.stderr)
    assert result.returncode == 0, f"Unexpected failure in Sphinx build:\n{result.stderr}"

    html = (build_dir / "html" / "index.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    for target, expected_url in REFERENCE_SPELLINGS.items():
        link = soup.find("a", string=target)
        assert link is not None, f"Expected a link labelled {target!r}"
        assert link["href"] == expected_url, f"Wrong anchor for {target!r}"

    # ``~`` shortens the title to the last component of a ``::`` reference too
    link = soup.find("a", string="COMPOSITE_BLEND")
    assert link is not None
    assert link["href"] == COMPOSITE_BLEND_URL


def _run_sphinx(src, build_dir, env):
    """Run ``sphinx-build`` in a subprocess with the given environment."""
    return run(
        [
            sys.executable,
            "-msphinx",
            "-b",
            "html",
            str(src),
            str(build_dir / "html"),
            "-W",
            "--keep-going",
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env=env,
    )


def _build_offline(src, build_dir, urls):
    """Run ``sphinx-build`` with the server unreachable and the given recorded URLs."""
    env = {**os.environ, URLS_ENV_VAR: str(urls), "HTTPS_PROXY": "http://127.0.0.1:9"}
    return _run_sphinx(src, build_dir, env)


def test_recorded_urls_are_reused_by_a_later_build(tmp_path):
    """A build takes its anchors from the recorded URLs instead of asking the server."""
    urls = tmp_path / "urls.jsonl"
    urls.write_text(
        json.dumps(["vtkImageData", "SetOrigin", SET_ORIGIN_URL, True]) + "\n", encoding="utf-8"
    )

    src = make_temp_doc_project(tmp_path, ":vtk:`vtkImageData.SetOrigin`")
    build_dir = tmp_path / "_build"
    result = _build_offline(src, build_dir, urls)
    assert result.returncode == 0, f"Unexpected failure in Sphinx build:\n{result.stderr}"

    html = (build_dir / "html" / "index.html").read_text(encoding="utf-8")
    link = BeautifulSoup(html, "html.parser").find("a", href=SET_ORIGIN_URL)
    assert link is not None, "The anchor was not taken from the recorded URLs"


def test_unchecked_references_are_recorded_too(tmp_path):
    """With link checking off, every reference still lands in the recorded URLs."""
    urls = tmp_path / "urls.jsonl"
    code_block = textwrap.dedent("""
    :vtk:`vtkImageData.SetOrigin`
    :vtk:`vtkPolyData`
    """)
    src = make_temp_doc_project(tmp_path, code_block, conf_extras="vtk_xref_nitpicky = False\n")

    result = _build_offline(src, tmp_path / "_build", urls)
    assert result.returncode == 0, f"Unexpected failure in Sphinx build:\n{result.stderr}"

    recorded = [json.loads(line) for line in urls.read_text(encoding="utf-8").splitlines()]
    assert ["vtkImageData", "SetOrigin", _vtk_class_url("vtkImageData"), False] in recorded
    assert ["vtkPolyData", None, _vtk_class_url("vtkPolyData"), False] in recorded

    # Nothing unvalidated is ever reused as an anchor
    assert _read_urls(urls) == {}


def test_recorded_urls_go_where_the_config_says(tmp_path):
    """``vtk_xref_urls`` names a file relative to the build output."""
    conf_extras = "vtk_xref_nitpicky = False\nvtk_xref_urls = 'vtk_xref_urls.jsonl'\n"
    src = make_temp_doc_project(tmp_path, ":vtk:`vtkPolyData`", conf_extras=conf_extras)
    build_dir = tmp_path / "_build"

    env = {key: value for key, value in os.environ.items() if key != URLS_ENV_VAR}
    result = _run_sphinx(src, build_dir, env)
    assert result.returncode == 0, f"Unexpected failure in Sphinx build:\n{result.stderr}"

    urls = build_dir / "html" / "vtk_xref_urls.jsonl"
    recorded = [json.loads(line) for line in urls.read_text(encoding="utf-8").splitlines()]
    assert recorded == [["vtkPolyData", None, _vtk_class_url("vtkPolyData"), False]]


def test_recorded_urls_survive_a_damaged_file(tmp_path):
    """A line which is not a reference is ignored rather than failing the build."""
    urls = tmp_path / "urls.jsonl"
    urls.write_text(
        "not json\n{}\n" + json.dumps(["vtkImageData", None, GET_SPACING_URL, True]) + "\n",
        encoding="utf-8",
    )
    assert _read_urls(urls) == {("vtkImageData", None): GET_SPACING_URL}


def test_recorded_urls_survive_an_unusable_path(tmp_path):
    """A file which cannot be read or written is no reason to fail the build."""
    assert _read_urls(tmp_path / "never-written.jsonl") == {}

    blocked = tmp_path / "a-file"
    blocked.write_text("", encoding="utf-8")
    _append_url(blocked / "urls.jsonl", ("vtkImageData", None), GET_SPACING_URL, validated=True)


def _rst_to_myst_role(code_block: str) -> str:
    """Translate ``:vtk:`content``` occurrences to MyST's ``{vtk}`content``` syntax.

    The role content between the backticks (targets, titles, ``~`` prefixes) is
    identical between the two syntaxes, so this is a purely mechanical swap of
    the role's delimiters.
    """
    return re.sub(r":vtk:`([^`]*)`", r"{vtk}`\1`", code_block)


def _build_docs(src, build_dir, jobs=None):
    """Run ``sphinx-build`` on ``src`` in a subprocess and return the completed process.

    Always builds with ``-W --keep-going`` so warnings from the ``:vtk:`` role
    surface as build failures. Pass ``jobs`` to build in parallel with an
    explicit doctree directory (used to compare parallel vs. serial output).

    ``stdout``/``stderr`` on the returned process are already decoded text
    (with invalid bytes replaced), so callers don't need to decode manually.

    Skips the running test when the build reports it could not reach vtk.org.
    """
    cmd = [
        sys.executable,
        "-msphinx",
        "-b",
        "html",
        str(src),
        str(build_dir / "html"),
    ]
    if jobs is not None:
        cmd += ["-d", str(build_dir / "doctrees"), f"-j{jobs}"]
    cmd += ["-W", "--keep-going"]
    env = dict(os.environ)
    if conftest.recorded_urls is not None:
        env[URLS_ENV_VAR] = str(conftest.recorded_urls)
    result = run(cmd, capture_output=True, encoding="utf-8", errors="replace", check=False, env=env)
    if UNREACHABLE_MESSAGE in result.stdout:
        skip_if_unreachable("the build could not check its references")
    return result


def make_temp_doc_project(tmp_path, sample_text: str, conf_extras: str = "", filetype: str = "rst"):
    """Set up a minimal Sphinx project that uses the :vtk: role directly in index.rst/md."""
    src = tmp_path / "src"
    src.mkdir()

    extensions = (
        "['sphinx_vtk_xref']" if filetype == "rst" else "['sphinx_vtk_xref', 'myst_parser']"
    )
    conf = f"extensions = {extensions}\n"
    if filetype == "md":
        conf += "source_suffix = {'.md': 'markdown'}\n"
    conf += conf_extras
    (src / "conf.py").write_text(conf)

    if filetype == "rst":
        lines = [
            "Test Page",
            "=========",
            "",
            sample_text.strip(),
            "",
        ]
        (src / "index.rst").write_text("\n".join(lines))
    else:
        lines = [
            "# Test Page",
            "",
            _rst_to_myst_role(sample_text.strip()),
            "",
        ]
        (src / "index.md").write_text("\n".join(lines))

    return src


@pytest.mark.parametrize(
    ("code_block", "expected_links", "expected_warning"),
    [
        (  # Valid cases (get/set methods and enum)
            textwrap.dedent("""
            :vtk:`vtkImageData.GetSpacing`.
            :vtk:`vtkImageData.SetOrigin`
            :vtk:`vtkCommand.EventIds`
            :vtk:`vtkVolumeMapper.COMPOSITE_BLEND`
            """),
            {
                GET_SPACING_URL: "vtkImageData.GetSpacing",
                SET_ORIGIN_URL: "vtkImageData.SetOrigin",
                EVENT_IDS_URL: "vtkCommand.EventIds",
                COMPOSITE_BLEND_URL: "vtkVolumeMapper.COMPOSITE_BLEND",
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
        (  # Valid class with enums, invalid enumerator
            ":vtk:`vtkVolumeMapper.FAKE_BLEND`",
            {_vtk_class_url("vtkVolumeMapper"): "vtkVolumeMapper.FAKE_BLEND"},
            "VTK method anchor not found for: 'vtkVolumeMapper.FAKE_BLEND' → https://vtk.org/doc/nightly/html/classvtkVolumeMapper.html#<anchor>, the class URL is used instead. [sphinx-vtk-xref]",
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
@pytest.mark.parametrize("filetype", ["rst", "md"])
def test_vtk_role(tmp_path, code_block, expected_links, expected_warning, filetype):
    doc_project = make_temp_doc_project(tmp_path, code_block, filetype=filetype)
    build_dir = tmp_path / "_build"
    build_html_dir = build_dir / "html"

    result = _build_docs(doc_project, build_dir)
    stdout = result.stdout
    stderr = result.stderr
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


@pytest.mark.parametrize(("filetype", "source_name"), [("rst", "index.rst"), ("md", "index.md")])
def test_warning_location_has_single_suffix(tmp_path, filetype, source_name):
    """Warnings must report ``index.rst:N``/``index.md:N``, not a doubled suffix.

    Regression test: the role used to build its warning location from
    ``document.current_source`` (already a full path) wrapped in a
    ``(docname, lineno)`` tuple, which Sphinx then re-suffixes via
    ``env.doc2path``, doubling the extension (e.g. ``index.rst.rst``).
    """
    code_block = ":vtk:`NonExistentClass`"
    doc_project = make_temp_doc_project(tmp_path, code_block, filetype=filetype)
    build_dir = tmp_path / "_build"

    result = _build_docs(doc_project, build_dir)
    stderr = result.stderr
    print("STDERR:\n", stderr)

    if not sys.platform.startswith("win"):
        assert re.search(rf"{re.escape(source_name)}:\d+:", stderr), (
            f"Expected '{source_name}:<N>:' in:\n{stderr}"
        )
        doubled_suffix = source_name + Path(source_name).suffix
        assert doubled_suffix not in stderr, (
            f"Found doubled suffix '{doubled_suffix}' in:\n{stderr}"
        )


def test_ignored_status_codes(tmp_path):
    """A status code in ``vtk_xref_ignored_status_codes`` must not fail ``-W`` builds.

    Asking vtk.org for a non-existent class returns a 404. Adding 404 to the
    ignored set should turn that into a non-fatal info log so ``-W`` still passes.
    """
    code_block = ":vtk:`NonExistentClass`"
    conf_extras = "vtk_xref_ignored_status_codes = {404}\n"
    doc_project = make_temp_doc_project(tmp_path, code_block, conf_extras=conf_extras)
    build_dir = tmp_path / "_build"
    build_html_dir = build_dir / "html"

    result = _build_docs(doc_project, build_dir)
    stdout = result.stdout
    stderr = result.stderr
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


def test_nitpicky_disabled(tmp_path):
    """``vtk_xref_nitpicky = False`` must skip link checking entirely.

    An otherwise-invalid class reference and an unresolved member reference
    should build cleanly, with no warning and no anchor resolution, since no
    HTTP request is made.
    """
    code_block = textwrap.dedent("""
    :vtk:`NonExistentClass`
    :vtk:`vtkImageData.GetSpacing`
    """)
    conf_extras = "vtk_xref_nitpicky = False\n"
    doc_project = make_temp_doc_project(tmp_path, code_block, conf_extras=conf_extras)
    build_dir = tmp_path / "_build"
    build_html_dir = build_dir / "html"

    result = _build_docs(doc_project, build_dir)
    stdout = result.stdout
    stderr = result.stderr
    print("STDOUT:\n", stdout)
    print("STDERR:\n", stderr)

    assert result.returncode == 0, "Build should not fail when nitpicky is disabled"

    if not sys.platform.startswith("win"):
        assert "[sphinx-vtk-xref]" not in stderr

    html = (build_html_dir / "index.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    # Unvalidated class link, no HTTP check performed.
    link = soup.find("a", href=_vtk_class_url("NonExistentClass"))
    assert link is not None

    # Member reference falls back to the plain class URL since resolving the
    # anchor would require the HTTP request that is now skipped.
    link = soup.find("a", href=_vtk_class_url("vtkImageData"))
    assert link is not None
    assert soup.find("a", href=GET_SPACING_URL) is None


def _build_in_process(doc_project, build_dir, **sphinx_kwargs):
    """Build ``doc_project`` in-process (no subprocess) so mocks in this test apply."""
    app = Sphinx(
        srcdir=str(doc_project),
        confdir=str(doc_project),
        outdir=str(build_dir / "html"),
        doctreedir=str(build_dir / "doctrees"),
        buildername="html",
        **sphinx_kwargs,
    )
    app.build()


def test_nitpicky_disabled_makes_no_http_requests(tmp_path):
    """No requests should happen when link checking is disabled.

    Uses an in-process Sphinx build (rather than the subprocess-based builds
    used elsewhere in this file) so that mocking the session here actually
    takes effect for the role's code.
    """
    # The class-level cache persists across in-process builds; start clean so
    # a previous test can't hide a real network call behind a cache hit.
    VTKRole.resolved_urls.clear()

    code_block = textwrap.dedent("""
    :vtk:`NonExistentClass`
    :vtk:`vtkImageData.GetSpacing`
    """)
    conf_extras = "vtk_xref_nitpicky = False\n"
    doc_project = make_temp_doc_project(tmp_path, code_block, conf_extras=conf_extras)
    build_dir = tmp_path / "_build"

    with (
        patch("sphinx_vtk_xref._SESSION.get") as mock_get,
        patch("sphinx_vtk_xref._SESSION.head") as mock_head,
    ):
        _build_in_process(doc_project, build_dir, warningiserror=True)

    mock_get.assert_not_called()
    mock_head.assert_not_called()


def test_nitpicky_enabled_makes_http_requests(tmp_path):
    """Sanity check: with link checking enabled (the default), requests are made.

    Guards against the previous test passing for the wrong reason (e.g. the
    mock never being wired up, or the role never running at all).
    """
    VTKRole.resolved_urls.clear()

    code_block = ":vtk:`vtkImageData.GetSpacing`"
    doc_project = make_temp_doc_project(tmp_path, code_block)
    build_dir = tmp_path / "_build"

    with patch("sphinx_vtk_xref._SESSION.get", wraps=requests.get) as mock_get:
        _build_in_process(doc_project, build_dir, warningiserror=True)

    mock_get.assert_called_once()


def test_a_class_reference_is_validated_without_downloading_the_page(tmp_path):
    """A reference with no member needs the status only, so it must not use GET."""
    VTKRole.resolved_urls.clear()

    doc_project = make_temp_doc_project(tmp_path, ":vtk:`vtkImageData`")
    build_dir = tmp_path / "_build"

    with (
        patch("sphinx_vtk_xref._SESSION.head", wraps=requests.head) as mock_head,
        patch("sphinx_vtk_xref._SESSION.get", wraps=requests.get) as mock_get,
    ):
        _build_in_process(doc_project, build_dir, warningiserror=True)

    mock_head.assert_called_once()
    mock_get.assert_not_called()
    assert VTKRole.resolved_urls[("vtkImageData", None)] == _vtk_class_url("vtkImageData")


def test_ignored_status_code_with_member(tmp_path):
    """An ignored status code for a ``class.member`` reference must cache both keys.

    Regression coverage for the branch that also marks the bare class name as
    resolved (to the class URL) when the ignored-status fallback fires for a
    class+member lookup, so a later plain-class reference reuses the cache
    instead of issuing a second request.
    """
    VTKRole.resolved_urls.clear()

    code_block = ":vtk:`vtkImageData.GetSpacing`"
    conf_extras = "vtk_xref_ignored_status_codes = {503}\n"
    doc_project = make_temp_doc_project(tmp_path, code_block, conf_extras=conf_extras)
    build_dir = tmp_path / "_build"

    mock_response = Mock(status_code=503, reason="Service Unavailable", text="")
    with patch("sphinx_vtk_xref._SESSION.get", return_value=mock_response):
        _build_in_process(doc_project, build_dir, warningiserror=True)

    class_url = _vtk_class_url("vtkImageData")
    assert VTKRole.resolved_urls[("vtkImageData", "GetSpacing")] == class_url
    assert VTKRole.resolved_urls[("vtkImageData", None)] == class_url


def test_unreachable_server_is_not_an_invalid_reference(tmp_path):
    """A server which is never reached says nothing about the reference.

    The failure carries no status code, so it used to fall through to the
    invalid-reference branch and cache the class as invalid for the whole build.
    """
    VTKRole.resolved_urls.clear()

    code_block = ":vtk:`vtkImageData`\n\n:vtk:`vtkImageData`\n"
    doc_project = make_temp_doc_project(tmp_path, code_block)
    build_dir = tmp_path / "_build"

    refused = requests.ConnectionError("Connection refused")
    warnings = StringIO()
    with patch("sphinx_vtk_xref._SESSION.head", side_effect=refused) as mock_head:
        _build_in_process(doc_project, build_dir, warning=warnings)

    assert "Invalid VTK class reference" not in warnings.getvalue()
    assert mock_head.call_count == 1
    assert VTKRole.resolved_urls[("vtkImageData", None)] == _vtk_class_url("vtkImageData")


def test_ignored_status_codes_defaults_without_config_value():
    """Falls back to the built-in ignored-codes set if the config value is missing.

    The config value is always registered by ``setup()`` in real builds; this
    guards the defensive fallback for callers that access the role directly.
    """
    role = VTKRole.__new__(VTKRole)
    fake_env = SimpleNamespace(config=SimpleNamespace())
    with patch.object(VTKRole, "env", fake_env):
        assert role._ignored_status_codes() == DEFAULT_IGNORED_STATUS_CODES


def test_nitpicky_defaults_false_without_config_value():
    """Falls back to ``nitpicky=False`` if the config value is missing."""
    role = VTKRole.__new__(VTKRole)
    fake_env = SimpleNamespace(config=SimpleNamespace())
    with patch.object(VTKRole, "env", fake_env):
        assert role._nitpicky() is False


def test_nitpicky_is_off_without_an_environment():
    """A document with no Sphinx environment must not be link checked.

    ``sphinx.ext.autosummary`` parses the summary line of a docstring in a bare
    docutils document, so ``self.env`` raises and the config cannot be read.
    """
    settings = frontend.get_default_settings(rst.Parser)
    settings.report_level = 5
    document = utils.new_document("", settings)
    assert not hasattr(settings, "env")

    role = VTKRole()
    rst.roles.register_local_role("vtk", role)
    with (
        patch("sphinx_vtk_xref._SESSION.get") as mock_get,
        patch("sphinx_vtk_xref._SESSION.head") as mock_head,
    ):
        rst.Parser().parse("Apply a :vtk:`vtkThreshold` filter.", document)

    mock_get.assert_not_called()
    mock_head.assert_not_called()
    assert role._nitpicky() is False
    reference = next(iter(document.findall(nodes.reference)))
    assert reference["refuri"] == _vtk_class_url("vtkThreshold")


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
