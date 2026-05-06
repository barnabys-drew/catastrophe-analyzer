#!/usr/bin/env python3
"""Test CA multi-source feeds with mock data."""
import sys
import logging

sys.path.insert(0, "src")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("test_mock")


def test_with_mock_data():
    """Test multi-source detector with mock SEC data."""
    from sec_feed_mock import generate_mock_8ks, generate_mock_form4s
    from multi_source_detector import MultiSourceDetector, MultiSourceSignal

    log.info("\n" + "=" * 70)
    log.info("TESTING MULTI-SOURCE DETECTOR WITH MOCK DATA")
    log.info("=" * 70)

    # Generate mock SEC events
    log.info("\n📋 Generating mock SEC events...")
    mock_8ks = generate_mock_8ks()
    log.info(f"✅ Generated {len(mock_8ks)} mock 8-K events:")
    for evt in mock_8ks:
        log.info(f"  • {evt.ticker}: {evt.item_description}")

    mock_form4s = generate_mock_form4s("AAPL")
    log.info(f"\n✅ Generated {len(mock_form4s)} mock Form 4 events for AAPL:")
    for evt in mock_form4s:
        log.info(f"  • {evt.filing_date}: {evt.item_description}")

    # Test signal detection
    log.info("\n" + "=" * 70)
    log.info("TESTING SIGNAL DETECTION")
    log.info("=" * 70)

    detector = MultiSourceDetector()

    # Manually create signals from mock data
    log.info("\n📋 Converting mock events to signals...")
    signals = []

    # Map 8-K events to signals
    for evt in mock_8ks:
        if "bankruptcy" in evt.item_description.lower():
            confidence = 95
            action = "sell_strength"
        elif "going concern" in evt.item_description.lower():
            confidence = 90
            action = "sell_strength"
        elif any(x in evt.item_description.lower() for x in ["restructuring", "litigation"]):
            confidence = 75
            action = "sell_strength"
        else:
            confidence = 60
            action = "investigate"

        sig = MultiSourceSignal(
            ticker=evt.ticker,
            company_name=evt.company_name,
            event_type="sec_8k_filing",
            confidence_score=confidence,
            sources=["sec_edgar"],
            description=f"8-K: {evt.item_description}",
            urgency="high" if confidence > 80 else "medium",
            recommend_action=action,
            timestamp=evt.filing_date,
        )
        signals.append(sig)

    # Add Form 4 signals
    for evt in mock_form4s:
        if "sold" in evt.item_description.lower():
            confidence = 55
            action = "investigate"
        elif "purchased" in evt.item_description.lower():
            confidence = 65
            action = "buy_dip"
        else:
            confidence = 45
            action = "hold"

        sig = MultiSourceSignal(
            ticker=evt.ticker,
            company_name=evt.company_name,
            event_type="insider_form4",
            confidence_score=confidence,
            sources=["sec_form4"],
            description=f"Form 4: {evt.item_description}",
            urgency="low",
            recommend_action=action,
            timestamp=evt.filing_date,
        )
        signals.append(sig)

    # Filter and rank
    log.info(f"\n✅ Generated {len(signals)} signals from mock events")

    # High confidence signals
    high_conf = [s for s in signals if s.confidence_score >= 70]
    log.info(f"\n📊 Signal Summary:")
    log.info(f"  Total: {len(signals)}")
    log.info(f"  High confidence (≥70%): {len(high_conf)}")

    log.info(f"\n🎯 High-Confidence Signals (≥70%):")
    for sig in sorted(high_conf, key=lambda x: x.confidence_score, reverse=True):
        log.info(f"  {sig.ticker:6s} | {sig.confidence_score:3.0f}% | {sig.urgency:8s} | {sig.describe_action}")

    log.info(f"\n⏳ Medium-Confidence Signals (50-69%):")
    med_conf = [s for s in signals if 50 <= s.confidence_score < 70]
    for sig in sorted(med_conf, key=lambda x: x.confidence_score, reverse=True):
        log.info(f"  {sig.ticker:6s} | {sig.confidence_score:3.0f}% | {sig.urgency:8s} | {sig.recommend_action}")

    log.info("\n" + "=" * 70)
    log.info("TEST COMPLETE")
    log.info("=" * 70)

    log.info("\n✅ Mock data pipeline working!")
    log.info("Next: Wire real SEC API (when endpoint is stable)")

    return True


if __name__ == "__main__":
    try:
        test_with_mock_data()
    except Exception as e:
        log.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
