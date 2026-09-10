"""Unit tests for the structured conversion outcome model (no Maya).

These tests encode the review findings: a created-but-unwired conversion must
never be summarized as a plain success, and per-SG wiring is tracked so a
multi-SG material is not silently reported as fully converted.
"""

from core.results import (
    BuildResult,
    ConversionResult,
    summarize_build_results,
    summarize_results,
)


def _ok(material="mat"):
    return ConversionResult(material=material, created=True, converted=True)


def test_full_success_counts_as_converted():
    result = _ok()
    result.total_sgs = 2
    result.wired = 2
    assert not result.unwired
    assert not result.partially_wired
    assert summarize_results([result]) == {
        "converted": 1, "skipped": 0, "failed": 0,
        "unwired": 0, "partial_wired": 0,
    }


def test_created_but_unwired_is_not_a_plain_success():
    # Report finding #2: SG connection failed for every SG, yet the material
    # node exists. This must surface as failed + unwired, never as converted.
    result = _ok()
    result.total_sgs = 2
    result.wired = 0
    assert result.unwired
    assert summarize_results([result]) == {
        "converted": 0, "skipped": 0, "failed": 1,
        "unwired": 1, "partial_wired": 0,
    }


def test_material_with_no_shading_engine_counts_as_converted():
    # A floating material has nothing to replace; conversion of the network
    # itself succeeded and must not be treated as a wiring failure.
    result = _ok()
    result.total_sgs = 0
    assert not result.unwired
    assert summarize_results([result]) == {
        "converted": 1, "skipped": 0, "failed": 0,
        "unwired": 0, "partial_wired": 0,
    }


def test_partially_wired_counts_converted_but_is_flagged():
    # Report finding #3: multi-SG material where only some SGs were wired.
    result = _ok()
    result.total_sgs = 3
    result.wired = 1
    assert not result.unwired
    assert result.partially_wired
    assert summarize_results([result]) == {
        "converted": 1, "skipped": 0, "failed": 0,
        "unwired": 0, "partial_wired": 1,
    }


def test_creation_failure_counts_as_failed():
    result = ConversionResult(material="mat", reason="failed to create target material")
    assert summarize_results([result])["failed"] == 1


def test_transfer_failure_counts_as_failed_even_if_node_created():
    result = ConversionResult(material="mat", created=True, reason="conversion failed")
    assert summarize_results([result])["failed"] == 1


def test_skips_are_not_failures():
    result = ConversionResult(material="mat", skipped=True, reason="already target type")
    assert summarize_results([result]) == {
        "converted": 0, "skipped": 1, "failed": 0,
        "unwired": 0, "partial_wired": 0,
    }


def test_mixed_batch_totals():
    results = [
        ConversionResult(material="a", skipped=True, reason="already target type"),
        ConversionResult(material="b", created=True, converted=True, total_sgs=1, wired=1),
        ConversionResult(material="c", created=True, converted=True, total_sgs=1, wired=0),
        ConversionResult(material="d", created=True, reason="conversion failed"),
    ]
    assert summarize_results(results) == {
        "converted": 1, "skipped": 1, "failed": 2,
        "unwired": 1, "partial_wired": 0,
    }


def test_build_result_success():
    result = BuildResult(material="hero", new_material="M_hero", built=True)
    assert result.built
    assert summarize_build_results([result]) == {"built": 1, "failed": 0}


def test_build_result_failure():
    result = BuildResult(material="hero", reason="boom")
    assert not result.built
    assert result.new_material is None
    assert summarize_build_results([result]) == {"built": 0, "failed": 1}


def test_summarize_build_results_mixed_batch():
    results = [
        BuildResult(material="a", new_material="M_a", built=True),
        BuildResult(material="b", reason="boom"),
    ]
    assert summarize_build_results(results) == {"built": 1, "failed": 1}
    assert summarize_build_results([]) == {"built": 0, "failed": 0}
