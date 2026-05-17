"""Verify Pydantic models don't have JSON-schema constraints that the
Anthropic structured-outputs API will reject (minimum, maximum, etc.) and
that client-side clamping still enforces the ranges."""

import pytest

from scout.models import CompanyEnrichment, CompanyScore


def test_enrichment_schema_has_no_min_max():
    schema = CompanyEnrichment.model_json_schema()
    _assert_no_constraints(schema)


def test_score_schema_has_no_min_max():
    schema = CompanyScore.model_json_schema()
    _assert_no_constraints(schema)


def test_enrichment_clamps_maturity_high():
    e = CompanyEnrichment(company_name="X", finance_maturity_score=99)
    assert e.finance_maturity_score == 5


def test_enrichment_clamps_maturity_low():
    e = CompanyEnrichment(company_name="X", finance_maturity_score=-3)
    assert e.finance_maturity_score == 1


def test_score_clamps_finance_gap():
    s = CompanyScore(
        finance_gap_score=42,
        personal_fit_score=-5,
        reachability_score=99,
        rationale="r",
        suggested_outreach_angle="o",
    )
    assert s.finance_gap_score == 10
    assert s.personal_fit_score == 0
    assert s.reachability_score == 5


def _assert_no_constraints(schema: dict) -> None:
    """Walk the schema; fail if any node has minimum/maximum/exclusiveMin/Max."""
    bad_keys = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"}

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in bad_keys:
                    raise AssertionError(
                        f"Schema contains {k!r} = {v!r} — Anthropic structured "
                        f"outputs will reject this with a 400. Strip the "
                        f"Pydantic ge/le constraint."
                    )
                walk(v)
        elif isinstance(node, list):
            for x in node:
                walk(x)

    walk(schema)
