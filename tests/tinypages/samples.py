def example() -> int:
    """
    Example function.

    Demonstrate the usage of ``sphinx-vtk-xref``:

    - :vtk:`vtkImageData.GetSpacing` should render to ``vtkImageData.GetSpacing``.
    - :vtk:`~vtkPolyData.SetVerts` should render to ``SetVerts``.
    - :vtk:`Get Triangle Strips <vtkPolyData.GetStrips>` should render to ``Get Triangle Strips``.

    Returns
    -------
    int
        An important number.

    """
    return 42
