"""Structured conversion outcomes shared by core and UI.

This module intentionally imports nothing but the stdlib so the outcome model
and its classification can be unit-tested in plain Python, and so the UI can
summarize a batch without pulling Maya into the reporting path.

The model separates three concerns that used to be collapsed into a single
"material node exists or not" boolean:

* ``created``    -- the target material node was created.
* ``converted``  -- the whole network transfer (attrs / bump / cc / disp) ran
                    without a fatal error.
* ``wired``      -- the created material was actually connected to shading
                    engines (``total_sgs`` = how many fed the source material).

A material that is created and converted but could not be wired to *any* of
its shading engines is ``unwired``: the scene still renders the old material,
so callers must not present it as a plain success.
"""

from dataclasses import dataclass


@dataclass
class ConversionResult:
    material: str
    new_material: str = None
    created: bool = False
    converted: bool = False
    skipped: bool = False
    reason: str = ""
    wired: int = 0
    total_sgs: int = 0

    @property
    def unwired(self):
        """Created/converted but none of the source's shading engines took it."""
        return self.total_sgs > 0 and self.wired == 0

    @property
    def partially_wired(self):
        """Wired to only some of the source's shading engines."""
        return self.total_sgs > 0 and 0 < self.wired < self.total_sgs


def summarize_results(results):
    """Classify a list of ConversionResult into headline counts.

    Returns a dict with keys: converted / skipped / failed / unwired /
    partial_wired.  ``unwired`` and ``partial_wired`` are sub-counters of
    ``failed`` / ``converted`` respectively (a conversion that could not be
    wired anywhere is counted as failed; a partially wired one still counts
    as converted but is flagged so callers can warn).
    """
    summary = {"converted": 0, "skipped": 0, "failed": 0,
               "unwired": 0, "partial_wired": 0}
    for result in results:
        if result.skipped:
            summary["skipped"] += 1
        elif not (result.created and result.converted):
            summary["failed"] += 1
        elif result.unwired:
            summary["failed"] += 1
            summary["unwired"] += 1
        else:
            summary["converted"] += 1
            if result.partially_wired:
                summary["partial_wired"] += 1
    return summary
