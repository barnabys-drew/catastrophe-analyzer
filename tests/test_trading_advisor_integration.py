"""
Integration test: CA signals → TradingAdvisor → Discord
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from trading_advisor import TradingAdvisor
from alert_manager import AlertManager


def test_trading_advisor_coverage():
    """Verify all 5 event categories map to trades"""
    advisor = TradingAdvisor()
    categories = list(advisor.EVENT_TRADE_PATTERNS.keys())
    assert len(categories) == 5
    assert "GEO_CRISIS" in categories
    assert "SUPPLY_SHOCK" in categories
    assert "FINANCIAL_CRISIS" in categories
    assert "PANDEMIC" in categories
    assert "POLITICAL_SHOCK" in categories
    print("✓ All 5 event categories covered")


def test_recommendation_generation():
    """Verify trade recommendations are generated with conviction scoring"""
    advisor = TradingAdvisor()
    signal = {
        "ticker": "SPY",
        "event_category": "GEO_CRISIS",
        "confidence": 85,
        "issue_summary": "Test crisis"
    }
    recs = advisor.get_recommendations(signal)
    assert len(recs) > 0
    assert all(0 <= r.conviction <= 100 for r in recs)
    assert recs[0].conviction >= recs[-1].conviction  # Sorted by conviction
    print(f"✓ Generated {len(recs)} recommendations with conviction scoring")


def test_alert_manager_integration():
    """Verify AlertManager calls TradingAdvisor for each signal"""
    manager = AlertManager()
    signals = [
        {"ticker": "USO", "event_category": "SUPPLY_SHOCK", "confidence": 80, "issue_summary": "Supply shock"},
        {"ticker": "TLT", "event_category": "FINANCIAL_CRISIS", "confidence": 90, "issue_summary": "Crisis"},
    ]
    result = manager.send_trading_advice(signals, emit_console=False)
    assert result["kind"] == "trading_advice"
    assert result["trades_generated"] == 2
    print(f"✓ AlertManager generated {result['trades_generated']} trade messages")


if __name__ == "__main__":
    test_trading_advisor_coverage()
    test_recommendation_generation()
    test_alert_manager_integration()
    print("\n✓ All integration tests passed")
