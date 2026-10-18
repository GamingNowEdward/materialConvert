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
    __init__.py                   # puts tests/ on sys.path, prints the environment
    test_config_validator_live.py
    test_node_utils_live.py
    test_conversion_matrix_live.py
    test_perf_baseline.py
    ...
```

`pytest.ini` sets `addopts = --ignore=tests/mayapy`, so a plain `pytest` run only
collects the pure suite. CI runs on **ubuntu-latest** (Python 3.11 + PySide6) with
the dependencies from `requirements-dev.txt`, then runs
`scripts/check_no_silent_pass.py`. PySide2 / Maya 2024 and Windows path behaviour
are covered by the local mayapy suite only.

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
- The run prints one `[mayapy] maya=... python=... ocio=... plugins[...]` line:
  **read it before trusting a green run** — a suite that passed with many skips
  did not exercise the renderers that were not installed.
- Renderer plugins that are not installed are filtered out generically, so the
  conversion matrix only runs for what is available and widens automatically once
  a renderer is installed.
- `test_perf_baseline.py` prints `[perf]` lines (cmds call counts and elapsed
  time) for one fixed scenario; it is a comparison baseline, not a benchmark with
  hard thresholds. PySide2 (Maya 2024) behaviour is only covered here.

## Coverage

| Domain | File |
|---|---|
| Config validation (real nodes, incl. `invert`) | `test_config_validator_live.py` |
| node_utils (identify / create / CC / collect / selection) | `test_node_utils_live.py` |
| Cross-material conversion matrix (all pairs) | `test_conversion_matrix_live.py` |
| Texture-driven connections | `test_conversion_texture_live.py` |
| Complex Builder-built architectures | `test_conversion_complex_live.py` |
| Bump / normal conversion (incl. normal-space preservation) | `test_conversion_bump_normal_live.py` |
| Special handlers (glossiness invert, black-zero, emission, same-renderer reuse) | `test_conversion_special_live.py` |
| alphaIsLuminance (enable / exempt / cross-network) | `test_conversion_alpha_luminance_live.py` |
| Displacement (sentinel / real node / failure propagation) | `test_conversion_displacement_live.py` |
| Converter flow (SG rewiring / batch / progress / transactional rollback) | `test_converter_flow_live.py` |
| CC chain conversion / reuse / restore / copied intermediate node | `test_cc_conversion_live.py` |
| Prerequisites (material / attribute level, failure reporting) | `test_prerequisites_live.py` |
| BuilderContext (naming / connections / layered) | `test_builder_context_live.py` |
| MaterialBuilder (all channels, full/simple, QSS) | `test_material_builder_live.py` |
| BatchBuilder (build / batch / progress) | `test_batch_builder_live.py` |
| Colorspace matcher (filename / channel / apply / ignore) | `test_colorspace_live.py` |
| Node Tools logic (node-type groups / SG rename / P2D→file) | `test_node_tools_live.py` |
| Scene round-trip (build → save → reopen → convert → save → reopen) | `test_scene_roundtrip_live.py` |
| Failure reporting (critical abort / non-critical issues) | `test_failure_reporting_live.py` |
| Performance baseline (`cmds` counts / timings) | `test_perf_baseline.py` |

Pure-suite files added by the reliability work:
`test_displacement_converter.py`, `test_bump_legacy.py`, `test_bump_converter.py`,
`test_cc_topology.py`, `test_busy_guard.py`, `test_config_schema.py`,
`test_main_entry.py`.

## Manual UI checklist (not automatable in CI)

Run these in Maya after a change that touches UI or scene wiring:

1. Two-SG material; inject a surface and a displacement connection failure →
   connections are restored, the result says so, and one undo reverts the batch.
2. Shared non-default layeredTexture + CC → source topology/parameters unchanged;
   the target reads a copy.
3. Redshift ↔ V-Ray object-space normal → target switch is 2; Arnold target
   reports the unsupported space.
4. Legacy RedshiftNormalMap: no P2D, P2D creation failure, partial UV failure,
   retry after failure, manually created same-name file.
5. Batch Builder directory with `rock_Roughness.png` + `rock_Glossiness.png` →
   CONFLICT rows visible, skip toggle works.
6. During a batch: click again, switch tabs and submit, close the window,
   interrupt with an exception → no re-entry, buttons and progress bar recover.
7. Four startup scenarios (no `__file__`, foreign `__file__`, leftover `main`
   module, another tool already imported `core`/`ui`) → the correct root loads.
