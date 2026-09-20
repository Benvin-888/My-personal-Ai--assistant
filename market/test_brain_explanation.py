from market.brain_explanation import explain_market_snapshot


def test_explanation_preserves_market_evidence_only():
    result = explain_market_snapshot(
        {
            "symbol": "EURUSD",
            "timeframe": "5m",
            "regime": "trend",
            "session": "london",
            "opportunity_state": "candidate",
            "evidence_fingerprint": "abc123",
            "supporting_factors": ["ema alignment"],
            "caution_factors": ["news risk"],
        }
    )

    assert result.symbol == "EURUSD"
    assert result.evidence_fingerprint == "abc123"
    assert "ema alignment" in result.supporting_factors


def test_explanation_has_no_execution_authority():
    result = explain_market_snapshot({"symbol": "EURUSD"})
    assert not hasattr(result, "execute")
    assert not hasattr(result, "buy")
