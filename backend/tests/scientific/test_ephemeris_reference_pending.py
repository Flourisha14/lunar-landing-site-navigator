"""Explicitly pending independent NASA ephemeris golden values."""

import json
from pathlib import Path

import pytest


@pytest.mark.scientific
@pytest.mark.requires_spice
def test_independent_spice_reference_pending() -> None:
    fixture = json.loads(
        Path(__file__).with_name("ephemeris_reference_pending.json").read_text(encoding="utf-8")
    )
    assert fixture["status"] == "pending_independent_reference"
    pytest.skip("Independent external SPICE reference values not yet available (QA-003 open item)")
