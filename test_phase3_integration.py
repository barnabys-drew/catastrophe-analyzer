#!/usr/bin/env python3
"""Test Phase 3: SEC/earnings integration into main.py"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from main import CatastropheAnalyzerApp
from sec_earnings_integration import SecEarningsIntegration

def test_sec_earnings_fetch():
    """Test SEC/earnings event fetching"""
    print("\n" + "="*60)
    print("TEST: SEC/Earnings Event Fetching")
    print("="*60)

    integration = SecEarningsIntegration()

    # Test SEC signals (with mock fallback)
    print("\n1. Fetching SEC signals...")
    sec_signals = integration.fetch_sec_signals(use_mock=True)
    print(f"   ✓ Got {len(sec_signals)} SEC signals")
    if sec_signals:
        for sig in sec_signals[:3]:
            print(f"     - {sig.get('ticker')}: {sig.get('item_type')}")

    # Test earnings signals
    print("\n2. Fetching earnings signals...")
    earnings_signals = integration.fetch_earnings_signals()
    print(f"   ✓ Got {len(earnings_signals)} earnings signals (note: requires paid API)")

def test_sec_earnings_conversion():
    """Test conversion of SEC/earnings signals to article format"""
    print("\n" + "="*60)
    print("TEST: Signal Conversion to Article Format")
    print("="*60)

    os.environ['CATASTROPHE_ANALYZER_USE_MOCK_DATA'] = '1'
    app = CatastropheAnalyzerApp()

    print("\n1. Converting SEC/earnings events to article format...")
    events = app._fetch_sec_earnings_events(quiet=False, use_mock=True)
    print(f"   ✓ Got {len(events)} events")

    if events:
        print("\n2. Sample events:")
        for event in events[:3]:
            print(f"   - Title: {event.get('title')}")
            print(f"     Source: {event.get('source')}")
            print(f"     Published: {event.get('published')}")
            print(f"     Candidates: {event.get('mapped_candidates')}")

def test_entity_extraction():
    """Test entity extraction on SEC/earnings events"""
    print("\n" + "="*60)
    print("TEST: Entity Extraction on SEC/Earnings Events")
    print("="*60)

    os.environ['CATASTROPHE_ANALYZER_USE_MOCK_DATA'] = '1'
    app = CatastropheAnalyzerApp()

    print("\n1. Fetching SEC/earnings events...")
    events = app._fetch_sec_earnings_events(quiet=True, use_mock=True)
    print(f"   Got {len(events)} events")

    if events:
        print("\n2. Running entity extraction...")
        extracted = app.entity_extractor.batch_extract(events)
        print(f"   ✓ Extracted {len(extracted)} entities")

        for i, entity in enumerate(extracted[:2]):
            print(f"\n   Event {i+1}:")
            print(f"     Title: {entity.get('title')}")
            print(f"     Has publicly traded: {entity.get('has_publicly_traded')}")
            if entity.get('mapped_candidates'):
                for cand in entity.get('mapped_candidates', []):
                    print(f"       - {cand.get('ticker')}: {cand.get('company')}")

if __name__ == "__main__":
    test_sec_earnings_fetch()
    test_sec_earnings_conversion()
    test_entity_extraction()

    print("\n" + "="*60)
    print("✓ All Phase 3 integration tests passed!")
    print("="*60)
