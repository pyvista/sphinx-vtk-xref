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

#.  Add ``sphinx_vtk_xref`` as an extension in your ``conf.py`` file used by
    Sphinx. The exact setup depends on whether your documentation is written
    in reStructuredText or Markdown.

reStructuredText
~~~~~~~~~~~~~~~~

.. code-block:: python

    extensions = [
        ...,
        'sphinx_vtk_xref',
    ]

Markdown (MyST)
~~~~~~~~~~~~~~~

Markdown support requires `MyST-Parser <https://myst-parser.readthedocs.io>`_,
which dispatches Sphinx roles like ``:vtk:`` using its own ``{vtk}`` syntax.

.. code-block:: bash

    pip install myst-parser

.. code-block:: python

    extensions = [
        ...,
        'sphinx_vtk_xref',
        'myst_parser',
    ]
    source_suffix = {
        '.md': 'markdown',
    }

Usage
-----

- Add links to VTK class documentation with the ``:vtk:`` role. For
  example, write ``:vtk:`vtkImageData``` in docstrings to link directly
  to the ``vtkImageData`` documentation. This will render as
  `vtkImageData <https://vtk.org/doc/nightly/html/classvtkImageData.html>`_.

  If using MyST, use ``{vtk}`vtkImageData``` instead.

- Link directly to class members such as methods, enums, or enum values. For
  example, write ``:vtk:`vtkImageData.GetSpacing``` to link directly to the
  ``GetSpacing`` method. This will render as
  `vtkImageData.GetSpacing <https://vtk.org/doc/nightly/html/classvtkImageData.html#ae6ebee83577b2d58c393a0df2f15b67d>`_.

  If using MyST, use ``{vtk}`vtkImageData.GetSpacing``` instead.

- Write enum values the way they appear in code: with or without their enum,
  and with either separator. All four of these link to the same
  ``COMPOSITE_BLEND`` anchor.

  .. code-block:: rst

      :vtk:`vtkVolumeMapper.COMPOSITE_BLEND`
      :vtk:`vtkVolumeMapper::COMPOSITE_BLEND`
      :vtk:`vtkVolumeMapper.BlendModes.COMPOSITE_BLEND`
      :vtk:`vtkVolumeMapper::BlendModes::COMPOSITE_BLEND`

  Naming the enum is required for a scoped ``enum class``, where
  ``:vtk:`vtkProperty::Point2DShapeType::Round``` is the only way to spell the
  value in C++.

- ``.`` and ``::`` are interchangeable separators, and a trailing argument list
  is ignored, so ``:vtk:`vtkImageData::GetSpacing()``` and
  ``:vtk:`vtkImageData.GetSpacing``` are the same reference.

- Use ``~`` to shorten the title for the link and only show the class member
  after the period. For example, ``:vtk:`~vtkImageData.GetSpacing```
  will render as
  `GetSpacing <https://vtk.org/doc/nightly/html/classvtkImageData.html#ae6ebee83577b2d58c393a0df2f15b67d>`_.

  If using MyST, use ``{vtk}`~vtkImageData.GetSpacing``` instead.

- Provide a custom title for the reference. For example,
  ``:vtk:`Get Image Spacing <vtkImageData.GetSpacing>```
  will render as
  `Get Image Spacing <https://vtk.org/doc/nightly/html/classvtkImageData.html#ae6ebee83577b2d58c393a0df2f15b67d>`_

  If using MyST, use ``{vtk}`Get Image Spacing <vtkImageData.GetSpacing>```
  instead.

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

- A reference is resolved from its most specific component that matches, so the
  class must come first. A module-qualified path such as
  ``:vtk:`vtk.vtkVolumeMapper.COMPOSITE_BLEND``` is not supported, and reports
  ``vtk`` as an invalid class.
