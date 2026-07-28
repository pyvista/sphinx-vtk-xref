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

Notes
-----

- The URLs linking to the VTK documentation are checked to ensure they are valid
  references. A warning is emitted if the reference is invalid, but the role
  will still try to point to a valid URL where possible. It is recommended to
  set ``nitpicky=True`` in ``conf.py`` when using this extension to ensure all
  links are valid and correct.

- The role does not currently support linking to nested members. For example,
  linking to an enum member with ``:vtk:`vtkCommand.EventIds``` works,
  but linking to a specific enum value with ``:vtk:`vtkCommand.EventIds.PickEvent```
  does not.
