"""Python references to VTK classes, such as those in type annotations."""

from __future__ import annotations

from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

from docutils import nodes
import pytest
import requests
from sphinx import addnodes

from sphinx_vtk_xref import DEFAULT_IGNORED_STATUS_CODES
from sphinx_vtk_xref import VTKRole
from sphinx_vtk_xref import _vtk_class_url
from sphinx_vtk_xref import resolve_python_reference


def _env(*, nitpicky=True):
    """Return a build environment stub with the extension's config."""
    config = SimpleNamespace(
        vtk_xref_nitpicky=nitpicky, vtk_xref_ignored_status_codes=DEFAULT_IGNORED_STATUS_CODES
    )
    return SimpleNamespace(config=config)


def _pending_xref(target, domain="py"):
    """Return an unresolved reference to ``target`` in ``domain``."""
    node = addnodes.pending_xref("", refdomain=domain, reftype="class", reftarget=target)
    return node, nodes.literal(target, target)


def _response(status):
    """Return a mocked HTTP response with ``status``."""
    return Mock(status_code=status, reason=HTTPStatus(status).phrase)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Start each test with no cached lookups."""
    VTKRole.resolved_urls.clear()


@pytest.mark.parametrize(
    "target",
    ["vtkPoints", "_vtk.vtkPoints", "vtkmodules.vtkCommonCore.vtkPoints"],
)
def test_vtk_class_links_to_its_documentation(target):
    node, contnode = _pending_xref(target)
    with patch("sphinx_vtk_xref._SESSION.head", return_value=_response(200)):
        reference = resolve_python_reference(None, _env(), node, contnode)
    assert reference["refuri"] == _vtk_class_url("vtkPoints")
    assert reference.astext() == target


@pytest.mark.parametrize(
    ("target", "domain"),
    [("numpy.ndarray", "py"), ("vtk", "py"), ("vtk.VTK_DOUBLE_MAX", "py"), ("vtkPoints", "cpp")],
)
def test_other_references_are_left_unresolved(target, domain):
    node, contnode = _pending_xref(target, domain)
    assert resolve_python_reference(None, _env(), node, contnode) is None


def test_invalid_class_warns_once_per_reference():
    node, contnode = _pending_xref("vtkPointz")
    with (
        patch("sphinx_vtk_xref._SESSION.head", return_value=_response(404)) as head,
        patch("sphinx_vtk_xref.logger") as logger,
    ):
        for _ in range(2):
            reference = resolve_python_reference(None, _env(), node, contnode)
    assert reference["refuri"] == _vtk_class_url("vtkPointz")
    head.assert_called_once()
    assert logger.warning.call_count == 2
    assert "Invalid VTK class reference: 'vtkPointz'" in logger.warning.call_args.args[0]


@pytest.mark.parametrize(
    "head",
    [{"return_value": _response(503)}, {"side_effect": requests.ConnectionError("down")}],
    ids=["ignored-status", "unreachable"],
)
def test_unavailable_server_reports_info(head):
    node, contnode = _pending_xref("vtkPoints")
    with (
        patch("sphinx_vtk_xref._SESSION.head", **head),
        patch("sphinx_vtk_xref.logger") as logger,
    ):
        resolve_python_reference(None, _env(), node, contnode)
    logger.warning.assert_not_called()
    logger.info.assert_called_once()


def test_unchecked_when_not_nitpicky():
    node, contnode = _pending_xref("vtkPointz")
    with patch("sphinx_vtk_xref._SESSION.head") as head:
        reference = resolve_python_reference(None, _env(nitpicky=False), node, contnode)
    head.assert_not_called()
    assert reference["refuri"] == _vtk_class_url("vtkPointz")
