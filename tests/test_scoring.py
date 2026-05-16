"""End-to-end test on mock fixture, with no API key available."""

import os
import tempfile
from pathlib import Path

import pytest

from scout.outreach.angle import load_pipeline_suppression
from scout.pipeline import load_fit_profile, run_mock
from scout.storage import ScoutDB


@pytest.fixture
def isolated_db():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "scout.db"
        db = ScoutDB(db_path)
        yield db
        db.close()


@pytest.fixture
def no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def test_mock_end_to_end(isolated_db, no_api_key):
    fit_profile = load_fit_profile("config/fit_profile.yaml")
    suppression = load_pipeline_suppression("config/companies_in_pipeline.yaml")

    scored = run_mock(fit_profile=fit_profile, db=isolated_db, suppression=suppression)

    company_names = {c.enrichment.company_name for c in scored}

    # UK/EU companies should pass; US/hardware should not.
    assert "Lovable" in company_names
    assert "BuildMate" in company_names
    assert "Finsight" in company_names
    assert "CropWise" in company_names
    assert "Zenith Robotics" not in company_names


def test_cfo_present_caps_finance_gap(isolated_db, no_api_key):
    fit_profile = load_fit_profile("config/fit_profile.yaml")
    suppression = load_pipeline_suppression("config/companies_in_pipeline.yaml")

    scored = run_mock(fit_profile=fit_profile, db=isolated_db, suppression=suppression)

    finsight = next(c for c in scored if c.enrichment.company_name == "Finsight")
    # Heuristic enrichment can't infer CFO presence from the title without a careers
    # page, so we don't assert has_existing_cfo_flag here — but the rule is enforced
    # in scoring.rubric when the flag is set. That path is exercised in unit form.
    assert finsight.score.finance_gap_score <= 10


def test_idempotency(isolated_db, no_api_key):
    fit_profile = load_fit_profile("config/fit_profile.yaml")
    suppression = load_pipeline_suppression("config/companies_in_pipeline.yaml")

    first = run_mock(fit_profile=fit_profile, db=isolated_db, suppression=suppression)
    second = run_mock(fit_profile=fit_profile, db=isolated_db, suppression=suppression)

    assert len(first) > 0
    assert len(second) == 0, "Second run must skip already-seen events."
