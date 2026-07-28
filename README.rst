Sphinx VTK XRef
===============

``sphinx-vtk-xref`` is a Sphinx extension for linking directly to
`VTK's documentation <https://vtk.org/doc/nightly/html/index.html>`_
using the ``:vtk:`` reference role.

Installation
------------

#.  Add ``sphinx-vtk-xref`` as a project dependency or install it with:

    .. code-block:: bash

        pip install sphinx-vtk-xref


#.  Add ``sphinx_vtk_xref`` as an extension in your ``conf.py`` file
    used by Sphinx:

.. code-block:: python

    extensions = [
        ...,
        'sphinx_vtk_xref',
    ]

Usage
-----

- Add links to VTK class documentation with the ``:vtk:`` role. For
  example, write ``:vtk:`vtkImageData``` in docstrings to link directly
  to the ``vtkImageData`` documentation. This will render as
  `vtkImageData <https://vtk.org/doc/nightly/html/classvtkImageData.html>`_.

- Link directly to class members such as methods or enums. For example,
  write ``:vtk:`vtkImageData.GetSpacing``` to link directly to the
  ``GetSpacing`` method. This will render as
  `vtkImageData.GetSpacing <https://vtk.org/doc/nightly/html/classvtkImageData.html#ae6ebee83577b2d58c393a0df2f15b67d>`_.

- Use ``~`` to shorten the title for the link and only show the class member
  after the period. For example, ``:vtk:`~vtkImageData.GetSpacing```
  will render as
  `GetSpacing <https://vtk.org/doc/nightly/html/classvtkImageData.html#ae6ebee83577b2d58c393a0df2f15b67d>`_.

- Provide a custom title for the reference. For example,
  ``:vtk:`Get Image Spacing <vtkImageData.GetSpacing>```
  will render as
  `Get Image Spacing <https://vtk.org/doc/nightly/html/classvtkImageData.html#ae6ebee83577b2d58c393a0df2f15b67d>`_

Configuration
-------------

The following options can be set in ``conf.py``:

``sphinx_vtk_xref_nitpicky``
  Bool, default ``True``. Set to ``False`` to disable ``:vtk:`` link
  checking. This is independent of Sphinx's own ``nitpicky`` option, so
  you can turn off ``:vtk:`` link validation without affecting how the rest
  of your project handles missing references. When disabled, the ``:vtk:``
  role skips the HTTP request used to validate class and member references
  (and to resolve member anchors) and instead links directly to the
  (unvalidated) class documentation page.

  .. code-block:: python

      sphinx_vtk_xref_nitpicky = False

``sphinx_vtk_xref_ignored_status_codes``
  Collection of HTTP status codes, default ``{429, 500, 502, 503, 504}``.
  These codes typically indicate a transient server-side issue (rate
  limiting or upstream unavailability) rather than a genuinely-invalid
  class reference, so they are logged as info messages and do not fail the
  build, even with Sphinx's ``-W`` flag. The role falls back to the
  (unvalidated) class URL in this case.

  .. code-block:: python

      sphinx_vtk_xref_ignored_status_codes = {404}

Notes
-----

- The URLs linking to the VTK documentation are checked to ensure they are valid
  references. A warning is emitted if the reference is invalid, but the role
  will still try to point to a valid URL where possible. Combine this with
  Sphinx's own ``-W`` flag to fail the build on invalid links.

- The role does not currently support linking to nested members. For example,
  linking to an enum member with ``:vtk:`vtkCommand.EventIds``` works,
  but linking to a specific enum value with ``:vtk:`vtkCommand.EventIds.PickEvent```
  does not.
