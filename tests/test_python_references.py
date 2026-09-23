"""Python references to VTK classes, such as those in type annotations."""

from __future__ import annotations

from docutils import nodes
import pytest
from sphinx import addnodes

from sphinx_vtk_xref import _vtk_class_url
from sphinx_vtk_xref import resolve_python_reference


def _pending_xref(target, domain="py"):
    """Return an unresolved reference to ``target`` in ``domain``."""
    node = addnodes.pending_xref("", refdomain=domain, reftype="class", reftarget=target)
    return node, nodes.literal(target, target)


@pytest.mark.parametrize(
    "target",
    ["vtkPoints", "_vtk.vtkPoints", "vtkmodules.vtkCommonCore.vtkPoints"],
)
def test_vtk_class_links_to_its_documentation(target):
    node, contnode = _pending_xref(target)
    reference = resolve_python_reference(None, None, node, contnode)
    assert reference["refuri"] == _vtk_class_url("vtkPoints")
    assert reference.astext() == target


@pytest.mark.parametrize(
    ("target", "domain"),
    [("numpy.ndarray", "py"), ("vtk", "py"), ("vtk.VTK_DOUBLE_MAX", "py"), ("vtkPoints", "cpp")],
)
def test_other_references_are_left_unresolved(target, domain):
    node, contnode = _pending_xref(target, domain)
    assert resolve_python_reference(None, None, node, contnode) is None
