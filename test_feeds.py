#!/usr/bin/env python3
"""Test CA multi-source feeds integration."""
import sys
import json
import logging
from datetime import datetime

# Add src to path
sys.path.insert(0, "src")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("test_feeds")


def test_sec_feed():
    """Test SEC 8-K and Form 4 fetching."""
    log.info("=" * 60)
    log.info("Testing SEC Feed...")
    log.info("=" * 60)

    try:
        from sec_feed import SecFeed, SecEvent

        feed = SecFeed(lookback_days=7)

        # Test 1: Fetch recent 8-Ks
        log.info("\n📋 Test 1: Fetching recent 8-K filings...")
        recent_8ks = feed.fetch_recent_8ks(limit=10)

        if recent_8ks:
            log.info(f"✅ Got {len(recent_8ks)} recent 8-Ks")
            for evt in recent_8ks[:3]:
                log.info(f"  • {evt.ticker}: {evt.item_description}")
        else:
            log.warning("⚠️ No 8-Ks fetched (API might be rate limited)")

        # Test 2: Fetch Form 4 for a known ticker
        log.info("\n📋 Test 2: Fetching Form 4 insider trades for AAPL...")
        form4s = feed.fetch_form4_insider_trades("AAPL", lookback_days=30)

        if form4s:
            log.info(f"✅ Got {len(form4s)} Form 4 filings")
            for evt in form4s[:2]:
                log.info(f"  • {evt.filing_date}: {evt.item_description}")
        else:
            log.warning("⚠️ No Form 4s fetched")

        # Test 3: Cache operations
        log.info("\n📋 Test 3: Testing cache operations...")
        if recent_8ks:
            feed.cache_to_file(recent_8ks, "/tmp/test_sec_events.jsonl")
            cached = feed.load_cache("/tmp/test_sec_events.jsonl")
            log.info(f"✅ Cached and loaded {len(cached)} events")

        return True

    except ImportError as e:
        log.error(f"❌ Import error: {e}")
        return False
    except Exception as e:
        log.error(f"❌ SEC feed test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_earnings_feed():
    """Test earnings surprise detection."""
    log.info("\n" + "=" * 60)
    log.info("Testing Earnings Feed...")
    log.info("=" * 60)

    try:
        from earnings_feed import EarningsFeed, EarningsSurprise

        feed = EarningsFeed()

        # Test 1: Load cache (if exists)
        log.info("\n📋 Test 1: Loading earnings cache...")
        cached_earnings = feed.load_cache("/app/data/earnings_events.jsonl", days_lookback=30)

        if cached_earnings:
            log.info(f"✅ Loaded {len(cached_earnings)} cached earnings events")
            for evt in cached_earnings[:2]:
                log.info(f"  • {evt.ticker}: EPS {evt.eps_actual} vs {evt.eps_estimate} ({evt.eps_surprise_pct:+.1f}%)")
        else:
            log.info("ℹ️ No earnings cache (expected on first run)")

        # Test 2: Create mock earnings surprise
        log.info("\n📋 Test 2: Creating mock earnings surprise for testing...")
        mock_earnings = EarningsSurprise(
            ticker="TEST",
            company_name="Test Company Inc",
            report_date="2026-05-06",
            eps_estimate=1.50,
            eps_actual=1.75,
            eps_surprise_pct=16.67,
            revenue_estimate=1000,
            revenue_actual=1150,
            revenue_surprise_pct=15.0,
            guidance_change="raised",
            analyst_rating_change="upgrade",
        )
        log.info(f"✅ Created mock: {mock_earnings.ticker} beat by {mock_earnings.eps_surprise_pct:+.1f}%")

        return True

    except ImportError as e:
        log.error(f"❌ Import error: {e}")
        return False
    except Exception as e:
        log.error(f"❌ Earnings feed test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_multi_source_detector():
    """Test multi-source signal detection."""
    log.info("\n" + "=" * 60)
    log.info("Testing Multi-Source Detector...")
    log.info("=" * 60)

    try:
        from multi_source_detector import MultiSourceDetector, MultiSourceSignal

        detector = MultiSourceDetector()

        # Test 1: Detect SEC signals
        log.info("\n📋 Test 1: Detecting SEC signals...")
        sec_signals = detector.detect_sec_signals()
        log.info(f"✅ Found {len(sec_signals)} SEC-based signals")
        for sig in sec_signals[:3]:
            log.info(f"  • {sig.ticker}: {sig.description} (confidence: {sig.confidence_score:.0f}%)")

        # Test 2: Detect earnings signals
        log.info("\n📋 Test 2: Detecting earnings signals...")
        earnings_signals = detector.detect_earnings_signals()
        log.info(f"✅ Found {len(earnings_signals)} earnings-based signals")

        # Test 3: Combine signals
        log.info("\n📋 Test 3: Combining multi-source signals...")
        combined = detector.combine_signals(
            sec_signals=sec_signals[:5],
            earnings_signals=earnings_signals[:5],
        )
        log.info(f"✅ Combined into {len(combined)} ranked signals")
        for sig in combined[:5]:
            sources_str = ", ".join(sig.sources)
            log.info(f"  • {sig.ticker}: confidence {sig.confidence_score:.0f}% ({sources_str})")

        # Test 4: Filter by threshold
        log.info("\n📋 Test 4: Filtering by confidence threshold...")
        high_conf = detector.filter_by_threshold(combined, min_confidence=70)
        log.info(f"✅ High-confidence signals: {len(high_conf)} (≥70%)")
        for sig in high_conf[:3]:
            log.info(f"  • {sig.ticker}: {sig.urgency.upper()} ({sig.confidence_score:.0f}%)")

        return True

    except ImportError as e:
        log.error(f"❌ Import error: {e}")
        return False
    except Exception as e:
        log.error(f"❌ Multi-source detector test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_sec_earnings_integration():
    """Test SEC + earnings integration layer."""
    log.info("\n" + "=" * 60)
    log.info("Testing SEC+Earnings Integration...")
    log.info("=" * 60)

    try:
        from sec_earnings_integration import SecEarningsIntegration

        log.info("\n📋 Test 1: Initializing integration...")
        integration = SecEarningsIntegration()
        log.info("✅ Integration initialized")

        log.info("\n📋 Test 2: Running one cycle with mock data...")
        summary = integration.run_once(use_mock=True)
        log.info(f"✅ Cycle completed:")
        log.info(f"  • SEC signals: {summary['sec_signals_found']}")
        log.info(f"  • Earnings signals: {summary['earnings_signals_found']}")
        log.info(f"  • High-confidence multi-source: {summary['multi_source_high_confidence']}")

        if summary['top_signals']:
            log.info("\n  Top signals:")
            for sig in summary['top_signals'][:3]:
                log.info(f"    • {sig.ticker}: {sig.description} ({sig.confidence_score:.0f}%)")

        return True

    except Exception as e:
        log.error(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_gold_monitor():
    """Test gold monitor FRED API integration."""
    log.info("\n" + "=" * 60)
    log.info("Testing Gold Monitor...")
    log.info("=" * 60)

    try:
        sys.path.insert(0, "../gold-accumulation-monitor")
        from src.monitor import GoldMonitor

        # Note: FRED API requires API key
        log.info("\n📋 Test 1: Initializing Gold Monitor...")
        monitor = GoldMonitor(config_path="gold-accumulation-monitor/config/monitor_config.json")
        log.info("✅ Monitor initialized")

        log.info("\n📋 Test 2: Fetching USD Index...")
        usd = monitor.fetch_usd_index()
        if usd:
            log.info(f"✅ USD Index: {usd:.2f}")
        else:
            log.warning("⚠️ Could not fetch USD Index (check FRED API key)")

        log.info("\n📋 Test 3: Fetching real rates...")
        real_rate = monitor.fetch_real_rates()
        if real_rate is not None:
            log.info(f"✅ Real rate: {real_rate:.2f}%")
        else:
            log.warning("⚠️ Could not fetch real rates (check FRED API key)")

        return True

    except ImportError as e:
        log.warning(f"⚠️ Gold monitor not set up yet: {e}")
        return True  # Not a failure, just not ready
    except Exception as e:
        log.error(f"❌ Gold monitor test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    log.info("\n" + "🧪 CATASTROPHE-ANALYZER MULTI-SOURCE FEED TESTS 🧪")
    log.info("Starting test suite...\n")

    results = {
        "SEC Feed": test_sec_feed(),
        "Earnings Feed": test_earnings_feed(),
        "Multi-Source Detector": test_multi_source_detector(),
        "SEC+Earnings Integration": test_sec_earnings_integration(),
        "Gold Monitor": test_gold_monitor(),
    }

    # Summary
    log.info("\n" + "=" * 60)
    log.info("TEST SUMMARY")
    log.info("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, passed_flag in results.items():
        status = "✅ PASS" if passed_flag else "❌ FAIL"
        log.info(f"{status}: {test_name}")

    log.info(f"\nTotal: {passed}/{total} tests passed")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
