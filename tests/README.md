# Tests

The suite is split in two independent halves:

- **Pure Python** (`tests/*.py`) — no Maya required. `tests/conftest.py` stubs
  `maya.cmds` with a dummy module so imports work under any system Python. This
  half runs in CI.
- **mayapy integration** (`tests/mayapy/*.py`) — drives the live Maya kernel
  (real node creation, connections, shading-engine wiring, renderer plugins). Run
  locally with Maya's `mayapy.exe`. **Not** part of CI.

## Layout

```
tests/
  conftest.py                     # stubs maya.cmds for the pure suite
  support.py                      # shared mayapy harness (import-safe)
  test_*.py                       # pure suite (CI)
  mayapy/
    __init__.py                   # puts tests/ on sys.path so `import support` works
    test_config_validator_live.py
    test_node_utils_live.py
    test_conversion_matrix_live.py
    ...
```

`pytest.ini` sets `addopts = --ignore=tests/mayapy`, so a plain `pytest` run only
collects the pure suite.

## Pure suite (no Maya)

```
python -m pytest -v
```

## mayapy suite (Maya required)

```
mayapy -m unittest discover -s tests/mayapy -t tests -v
```

With Maya 2024 on Windows:

```
"C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe" -m unittest discover -s tests/mayapy -t tests -v
```

- `-t tests` puts `tests/` (home of `support.py`) on `sys.path`.
- `tests/support.py` starts `maya.standalone`, loads the renderer plugins found on
  the machine (mtoa / redshift4maya / vrayformaya / lookdevKit) and gives every
  test a fresh scene.
- Renderer plugins that are not installed are filtered out generically, so the
  conversion matrix only runs for what is available and widens automatically once
  a renderer is installed.

## Coverage

| Domain | File |
|---|---|
| Config validation (real nodes, incl. `invert`) | `test_config_validator_live.py` |
| node_utils (identify / create / CC / collect / selection) | `test_node_utils_live.py` |
| Cross-material conversion matrix (all pairs) | `test_conversion_matrix_live.py` |
| Texture-driven, complex architectures, special handlers, converter flow | (added in later phases) |
| Builder / BuilderContext / Batch Builder / Colorspace / Node Tools / scene round-trip | (added in later phases) |
