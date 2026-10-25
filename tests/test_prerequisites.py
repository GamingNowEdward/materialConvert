"""Tests for builder prerequisite application (per-channel switches from config).

A builder prerequisite is one ``{"attribute": ..., "value": ...}`` entry; it must
never be a silent no-op when it cannot be applied.
"""

from core import prerequisites as prerequisites_module
from core.logger import Logger
from core.prerequisites import apply_prerequisite_dict


def _patch(monkeypatch, setattr_error=None):
    calls = []

    def fake_set_attr(plug, *values, **kwargs):
        if setattr_error is not None:
            raise setattr_error
        calls.append((plug, values))

    monkeypatch.setattr(prerequisites_module.cmds, "setAttr", fake_set_attr)
    return calls


def test_prerequisite_is_applied(monkeypatch):
    log = Logger()
    calls = _patch(monkeypatch)

    outcome = apply_prerequisite_dict(
        "M1", {"attribute": "translucencyMode", "value": 6}, logger=log)

    assert outcome.ok
    assert calls == [("M1.translucencyMode", (6,))]


def test_missing_prerequisite_is_a_noop(monkeypatch):
    log = Logger()
    calls = _patch(monkeypatch)

    outcome = apply_prerequisite_dict("M1", {}, logger=log)

    assert outcome.ok
    assert calls == []


def test_prerequisite_failure_is_reported(monkeypatch):
    log = Logger()
    _patch(monkeypatch, setattr_error=RuntimeError("No object matches name"))

    outcome = apply_prerequisite_dict(
        "M1", {"attribute": "translucencyMode", "value": 6}, logger=log)

    assert not outcome.ok
    assert outcome.failures and "translucencyMode" in outcome.failures[0]


def test_invalid_prerequisite_definition_is_reported(monkeypatch):
    log = Logger()
    calls = _patch(monkeypatch)

    outcome = apply_prerequisite_dict("M1", ["not", "a", "dict"], logger=log)

    assert not outcome.ok
    assert calls == []
