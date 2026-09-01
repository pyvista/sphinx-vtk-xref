"""Link to VTK's documentation with the ``:vtk:`` role."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING
import re

from bs4 import BeautifulSoup
from docutils import nodes
import requests
from sphinx.util.docutils import ReferenceRole
from sphinx.util import logging

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from typing import ClassVar

#: Timeout (in seconds) for HTTP requests to the VTK documentation server.
HTTP_TIMEOUT = 30

#: Shared across every lookup, so the connection to the server is reused.
_SESSION = requests.Session()

#: The bare member name of a Doxygen ``memtitle`` header, i.e. the ``GetSpacing``
#: of ``◆ GetSpacing() [1/3]``.
MEMTITLE_NAME_PATTERN = re.compile(r"[\s◆]*([^\s(]+)")

#: A trailing C++ argument list on a member reference, i.e. the ``(double x)``
#: of ``GetSpacing(double x)``.
ARGUMENT_LIST_PATTERN = re.compile(r"\(.*\)\s*$")

#: HTTP status codes that, by default, do not fail the build. These typically
#: indicate a transient server-side issue (rate limiting or upstream
#: unavailability) rather than a genuinely-invalid class reference.
DEFAULT_IGNORED_STATUS_CODES = frozenset(
    {
        HTTPStatus.TOO_MANY_REQUESTS,  # 429
        HTTPStatus.INTERNAL_SERVER_ERROR,  # 500
        HTTPStatus.BAD_GATEWAY,  # 502
        HTTPStatus.SERVICE_UNAVAILABLE,  # 503
        HTTPStatus.GATEWAY_TIMEOUT,  # 504
    }
)


class VTKRole(ReferenceRole):
    """Link to vtk class documentation using a custom role.

    E.g. use :vtk:`vtkPolyData` for linking to the `vtkPolyData` class docs.
    """

    # Cache for (class, member) keys with urls as values
    resolved_urls: ClassVar[dict[tuple[str, str | None], str]] = {}

    def run(self):  # numpydoc ignore=RT01
        """Run the :vtk: role."""
        INVALID_URL = ""  # URL is set to empty string if not valid

        cls_full = self.target
        title = self.title

        # Handle `~` prefix to shorten the title
        if cls_full.startswith("~"):
            cls_full = cls_full[1:]
            if not self.has_explicit_title:
                title = cls_full.replace("::", ".").split(".")[-1]

        # Split input like 'vtkClass.member' or 'vtkClass::Enum::VALUE'
        cls_name, member_path = _split_reference(cls_full)
        member_name = ".".join(member_path) if member_path else None
        cls_url = _vtk_class_url(cls_name)

        if not self._nitpicky():
            # Link checking disabled: skip the HTTP validation/anchor lookup
            # entirely and point straight at the (unvalidated) class URL.
            node = nodes.reference(title, title, refuri=cls_url)
            return [node], []

        cache_key = (cls_name, member_name)
        cached_url = self.resolved_urls.get(cache_key)
        if cached_url is not None:
            # Cache hit, check if valid or not
            if cached_url == INVALID_URL:
                # Not valid, report the error source
                has_valid_class_url = self.resolved_urls.get((cls_name, None))
                if member_name and has_valid_class_url:
                    # Class is valid but member is not
                    self._warn_invalid_class_member_ref(cls_name, member_name)
                else:
                    self._warn_invalid_class_ref(cls_name)

                # Use class URL fallback for invalid member anchor
                refuri = cls_url
            else:
                # Cached url is valid
                refuri = cached_url

            node = nodes.reference(title, title, refuri=refuri)
            return [node], []

        # Not cached, build URL and validate
        status_code: int | None = None
        status_reason = ""
        try:
            # Only an anchor lookup needs the page body; otherwise the status is enough.
            fetch = _SESSION.get if member_path else _SESSION.head
            response = fetch(cls_url, timeout=HTTP_TIMEOUT)
            status_code = response.status_code
            status_reason = response.reason or ""
            if status_code != HTTPStatus.OK:
                msg = f"HTTP {status_code} {status_reason}".strip()
                raise requests.RequestException(msg)
            html = response.text if member_path else ""
        except requests.RequestException as exc:
            if status_code is not None and status_code in self._ignored_status_codes():
                # Transient server issue — do not fail the build. Emit an info
                # message and fall back to the (unvalidated) class URL.
                self._info_ignored_class_ref(cls_name, status_code, status_reason)
                self.resolved_urls[cache_key] = cls_url
                if member_name:
                    self.resolved_urls[(cls_name, None)] = cls_url
                node = nodes.reference(title, title, refuri=cls_url)
                return [node], []

            # Invalid class url
            reason = str(exc) if str(exc) else exc.__class__.__name__
            self._warn_invalid_class_ref(cls_name, reason=reason)

            # Create cache entries
            self.resolved_urls[cache_key] = INVALID_URL
            if member_name:
                self.resolved_urls[(cls_name, None)] = INVALID_URL

            # We return the reference even though the URL is bad
            node = nodes.reference(title, title, refuri=cls_url)
            return [node], []

        if member_path:
            anchor, ignored = _find_member_path_anchor(html, member_path)
            if anchor:
                if ignored:
                    self._warn_nested_members_ref(cls_name, member_path, ignored)
                full_url = f"{cls_url}#{anchor}"
                self.resolved_urls[cache_key] = full_url
                node = nodes.reference(title, title, refuri=full_url)
                return [node], []
            else:
                # Anchor not found, mark cache as invalid but still fallback to class URL
                self.resolved_urls[cache_key] = INVALID_URL
                self._warn_invalid_class_member_ref(cls_name, member_name)

                node = nodes.reference(title, title, refuri=cls_url)
                return [node], []

        # No member, just class URL
        self.resolved_urls[cache_key] = cls_url
        node = nodes.reference(title, title, refuri=cls_url)
        return [node], []

    def _ignored_status_codes(self):
        try:
            codes = self.env.config.vtk_xref_ignored_status_codes
        except AttributeError:
            return DEFAULT_IGNORED_STATUS_CODES
        return frozenset(codes)

    def _nitpicky(self):
        try:
            return bool(self.env.config.vtk_xref_nitpicky)
        except AttributeError:
            return True

    def _warn_invalid_class_ref(self, cls_name, reason=None):
        suffix = f" ({reason})" if reason else ""
        self._issue_warning(
            f"Invalid VTK class reference: '{cls_name}' → {_vtk_class_url(cls_name)}{suffix}"
        )

    def _warn_invalid_class_member_ref(self, cls_name, member_name):
        self._issue_warning(
            f"VTK method anchor not found for: '{cls_name}.{member_name}' → {_vtk_class_url(cls_name)}#<anchor>, "
            f"the class URL is used instead."
        )

    def _warn_nested_members_ref(self, cls_name, member_path, ignored):
        full = ".".join(member_path)
        resolved = ".".join(member_path[: len(member_path) - len(ignored)])
        extra = ".".join(ignored)
        self._issue_warning(
            f"Too many nested members in VTK reference: '{cls_name}.{full}'. "
            f"Interpreting as '{cls_name}.{resolved}', ignoring: '{extra}'"
        )

    def _info_ignored_class_ref(self, cls_name, status_code, reason):
        logger.info(
            f"Ignoring HTTP {status_code} {reason} for VTK class reference: "
            f"'{cls_name}' → {_vtk_class_url(cls_name)}",
            location=self.get_location(),
            type="sphinx-vtk-xref",
        )

    def _issue_warning(self, msg):
        logger.warning(
            msg,
            location=self.get_location(),
            type="sphinx-vtk-xref",
        )


def _vtk_class_url(cls_name):
    """Return the URL to the documentation for a VTK class."""
    return f"https://vtk.org/doc/nightly/html/class{cls_name}.html"


def _split_reference(target: str) -> tuple[str, list[str]]:
    """Split a reference into its class name and the member path below it."""
    # `::` separators and trailing argument lists are how VTK's own C++ docs
    # spell members, so accept them alongside the dotted Python spelling.
    parts = ARGUMENT_LIST_PATTERN.sub("", target.replace("::", ".")).split(".")
    return parts[0], [part for part in parts[1:] if part]


def _find_member_path_anchor(html: str, member_path: list[str]) -> tuple[str | None, list[str]]:
    """Find the anchor for the most specific component of a member path that resolves."""
    # An enum value may be written bare or qualified by its enum, and a scoped
    # enum can only be written qualified, so the last component is tried first.
    soup = BeautifulSoup(html, "html.parser")
    for index in reversed(range(len(member_path))):
        anchor = _find_anchor(soup, member_path[index])
        if anchor:
            return anchor, member_path[index + 1 :]
    return None, []


def _find_member_anchor(html: str, member_name: str) -> str | None:
    """Try to find the anchor ID for a method/attribute/enumerator in the HTML."""
    anchor, _ = _find_member_path_anchor(html, [member_name])
    return anchor


def _find_anchor(soup: BeautifulSoup, member_name: str) -> str | None:
    """Find the anchor ID for a single member name, most specific match first."""
    return (
        _find_memtitle_anchor(soup, member_name, exact=True)
        or _find_enumerator_anchor(soup, member_name)
        or _find_memtitle_anchor(soup, member_name, exact=False)
    )


def _memtitle_name(title: str) -> str:
    """Return a ``memtitle`` header's member name, without its permalink or signature."""
    match = MEMTITLE_NAME_PATTERN.match(title)
    return match.group(1) if match else ""


def _find_memtitle_anchor(soup: BeautifulSoup, member_name: str, *, exact: bool) -> str | None:
    """Find the anchor ID of a method or member variable from its ``memtitle`` header."""
    headers = soup.find_all(["h2", "h3"], class_="memtitle")
    for header in headers:
        title = header.get_text()
        matched = _memtitle_name(title) == member_name if exact else member_name in title
        if matched:
            anchor = header.find_previous("a", id=True)
            if anchor:
                return anchor["id"]
    return None


def _find_enumerator_anchor(soup: BeautifulSoup, member_name: str) -> str | None:
    """Find the anchor ID of an enumerator from its row in the enum's value table."""
    # Doxygen documents enumerators as rows of a table inside the enum's own
    # ``memitem`` block, so they have no ``memtitle`` header of their own.
    for cell in soup.select("table.fieldtable td.fieldname"):
        anchor = cell.find("a", id=True)
        if anchor and cell.get_text(strip=True) == member_name:
            return anchor["id"]
    return None


def setup(app):
    app.add_role("vtk", VTKRole())
    app.add_config_value(
        "vtk_xref_ignored_status_codes",
        DEFAULT_IGNORED_STATUS_CODES,
        "env",
        types=(frozenset, set, list, tuple),
    )
    app.add_config_value(
        "vtk_xref_nitpicky",
        True,
        "env",
        types=(bool,),
    )
    return {
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
