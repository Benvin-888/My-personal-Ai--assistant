from brain import analyze_intent


def test_explicit_market_query_routes_deterministically():
    intent = analyze_intent("analyze market EUR/USD 5m")
    assert intent == {
        "type": "market_read",
        "parameters": {
            "pair": "EURUSD",
            "interval": "5m",
            "data_range": "1d",
        },
    }


def test_market_query_never_becomes_an_execution_action():
    intent = analyze_intent("check market EURUSD 15m")
    assert intent["type"] == "market_read"
    assert "action" not in intent
    assert intent["parameters"]["pair"] == "EURUSD"
