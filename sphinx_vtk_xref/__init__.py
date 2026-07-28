"""Link to VTK's documentation with the ``:vtk:`` role."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

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
                title = cls_full.split(".")[-1]

        # Validate and split input like 'vtkClass.member'
        parts = cls_full.split(".")
        if len(parts) > 2:
            cls_name = parts[0]
            member_name = parts[1]
            extra = ".".join(parts[2:])
            self._warn_nested_members_ref(cls_name, member_name, extra)
        else:
            cls_name, member_name = parts[0], parts[1] if len(parts) == 2 else None
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
            response = requests.get(cls_url, timeout=HTTP_TIMEOUT)
            status_code = response.status_code
            status_reason = response.reason or ""
            if status_code != HTTPStatus.OK:
                msg = f"HTTP {status_code} {status_reason}".strip()
                raise requests.RequestException(msg)
            html = response.text
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

        if member_name:
            anchor = _find_member_anchor(html, member_name)
            if anchor:
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
            codes = self.env.config.sphinx_vtk_xref_ignored_status_codes
        except AttributeError:
            return DEFAULT_IGNORED_STATUS_CODES
        return frozenset(codes)

    def _nitpicky(self):
        try:
            return bool(self.env.config.sphinx_vtk_xref_nitpicky)
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

    def _warn_nested_members_ref(self, cls_name, member_name, extra):
        self._issue_warning(
            f"Too many nested members in VTK reference: '{cls_name}.{member_name}.{extra}'. "
            f"Interpreting as '{cls_name}.{member_name}', ignoring: '{extra}'"
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


def _find_member_anchor(html: str, member_name: str) -> str | None:
    """Try to find the anchor ID for a method/attribute in the HTML."""
    soup = BeautifulSoup(html, "html.parser")
    headers = soup.find_all(["h2", "h3"], class_="memtitle")
    for header in headers:
        if member_name in header.get_text():
            anchor = header.find_previous("a", id=True)
            if anchor:
                return anchor["id"]
    return None


def setup(app):
    app.add_role("vtk", VTKRole())
    app.add_config_value(
        "sphinx_vtk_xref_ignored_status_codes",
        DEFAULT_IGNORED_STATUS_CODES,
        "env",
        types=(frozenset, set, list, tuple),
    )
    app.add_config_value(
        "sphinx_vtk_xref_nitpicky",
        True,
        "env",
        types=(bool,),
    )
    return {
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
