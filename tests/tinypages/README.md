# Test project for sphinx-vtk-xref sphinx extension

Build locally with:

**Normal build**
```
sphinx-build -b html . _build/html -v
```

**Parallel build**
```
sphinx-build -b html -j auto . _build/html -v
```

**Strict parallel build (warnings fail)**
```
sphinx-build -b html -j 4 . _build/html -W --keep-going
```
