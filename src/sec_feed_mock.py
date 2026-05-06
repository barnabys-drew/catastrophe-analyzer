"""Mock SEC data generator for testing multi-source detection logic.

In production, replace with real SEC EDGAR API or third-party service (e.g., Alpha Vantage).
"""
from datetime import datetime, timedelta
from typing import List
from sec_feed import SecEvent


def generate_mock_8ks() -> List[SecEvent]:
    """Generate realistic mock 8-K events for testing."""
    events = []

    # Mock events that would trigger signals
    mock_data = [
        {
            "ticker": "SMED",
            "company": "Stereotaxis Inc",
            "item": "Item 1.01",
            "description": "Material agreement - FDA warning letter",
            "date": (datetime.now() - timedelta(days=2)).isoformat()[:10],
        },
        {
            "ticker": "VCTR",
            "company": "Vector Group",
            "item": "Item 2.02",
            "description": "Material cost associated with exit - debt restructuring",
            "date": (datetime.now() - timedelta(days=1)).isoformat()[:10],
        },
        {
            "ticker": "RVTY",
            "company": "Revivity Inc",
            "item": "Item 8.01",
            "description": "Bankruptcy filing - chapter 11",
            "date": (datetime.now() - timedelta(days=3)).isoformat()[:10],
        },
        {
            "ticker": "TLRY",
            "company": "Tilray Inc",
            "item": "Item 2.06",
            "description": "Disposition - sale of subsidiary",
            "date": (datetime.now() - timedelta(days=1)).isoformat()[:10],
        },
        {
            "ticker": "ARKX",
            "company": "ARK Space Technology ETF",
            "item": "Item 9.01",
            "description": "Litigation - class action settlement",
            "date": datetime.now().isoformat()[:10],
        },
    ]

    for data in mock_data:
        event = SecEvent(
            ticker=data["ticker"],
            company_name=data["company"],
            cik="0000" + str(hash(data["ticker"]) % 100000),
            form_type="8-K",
            filing_date=data["date"],
            item_type=data["item"],
            item_description=data["description"],
            url=f"https://www.sec.gov/cgi-bin/viewer?action=view&cik={data['ticker']}",
        )
        events.append(event)

    return events


def generate_mock_form4s(ticker: str = "AAPL") -> List[SecEvent]:
    """Generate realistic mock Form 4 insider trading events."""
    events = []

    mock_data = [
        {
            "date": (datetime.now() - timedelta(days=5)).isoformat()[:10],
            "description": "Executive officer sold 10,000 shares at $150/share",
        },
        {
            "date": (datetime.now() - timedelta(days=2)).isoformat()[:10],
            "description": "Director purchased 5,000 shares at $145/share (large buy)",
        },
        {
            "date": datetime.now().isoformat()[:10],
            "description": "CFO exercised options for 25,000 shares",
        },
    ]

    for data in mock_data:
        event = SecEvent(
            ticker=ticker.upper(),
            company_name=f"{ticker} Inc",
            cik="0000" + str(hash(ticker) % 100000),
            form_type="4",
            filing_date=data["date"],
            item_type="Insider Transaction",
            item_description=data["description"],
            url=f"https://www.sec.gov/cgi-bin/viewer?action=view&cik={ticker}",
        )
        events.append(event)

    return events
