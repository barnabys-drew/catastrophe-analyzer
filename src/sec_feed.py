"""SEC EDGAR 8-K and Form 4 feed parser for real-time regulatory events."""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List
import requests
from dataclasses import dataclass

log = logging.getLogger("sec_feed")


@dataclass
class SecEvent:
    """SEC filing event."""
    ticker: str
    company_name: str
    cik: str
    form_type: str  # "8-K", "4", "8-A", etc.
    filing_date: str
    item_type: Optional[str]  # e.g., "Item 1.01" for "Material Agreement"
    item_description: str  # "Bankruptcy", "Material Cost Associated with Exit or Disposal Activities", etc.
    url: str
    source: str = "sec_edgar"

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "cik": self.cik,
            "form_type": self.form_type,
            "filing_date": self.filing_date,
            "item_type": self.item_type,
            "item_description": self.item_description,
            "url": self.url,
            "source": self.source,
        }


class SecFeed:
    """Fetch 8-K and Form 4 filings from SEC EDGAR."""

    SEC_API_BASE = "https://data.sec.gov/api/xquery"
    EDGAR_BROWSE = "https://www.sec.gov/cgi-bin/browse-edgar"

    # High-impact 8-K items that indicate distress/material events
    MATERIAL_8K_ITEMS = {
        "1.01": "Bankruptcy or going concern",
        "2.02": "Material cost/restructuring",
        "2.06": "Material disposition (asset sale)",
        "8.01": "Material agreement/change in control",
        "9.01": "Litigation/legal proceedings",
    }

    def __init__(self, lookback_days: int = 7):
        """Initialize SEC feed.

        Args:
            lookback_days: how far back to fetch 8-Ks/Form 4s
        """
        self.lookback_days = lookback_days
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Catastrophe-Analyzer (research)"})

    def fetch_recent_8ks(self, limit: int = 100) -> List[SecEvent]:
        """Fetch recent 8-K filings across all companies.

        Note: SEC API has rate limits. Use sparingly (cache results).

        Args:
            limit: max 8-Ks to return

        Returns:
            List of SecEvent objects
        """
        events = []

        try:
            # Query recent 8-K filings
            # This uses the SEC FULL-TEXT search API
            params = {
                "action": "getcompany",
                "type": "8-K",
                "dateb": datetime.now().isoformat()[:10],
                "owner": "exclude",
                "match": "",
                "filenum": "",
                "State": "",
                "SIC": "",
                "myHID": "",
                "output": "json",
                "count": limit,
            }

            resp = self.session.get(self.EDGAR_BROWSE, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            for filing in data.get("filings", [])[:limit]:
                # Parse 8-K
                ticker = filing.get("ticker", "").upper()
                if not ticker:
                    continue

                try:
                    event = SecEvent(
                        ticker=ticker,
                        company_name=filing.get("company_name", "Unknown"),
                        cik=filing.get("cik_str", ""),
                        form_type="8-K",
                        filing_date=filing.get("filing_date", ""),
                        item_type=None,  # Would need to parse full filing for this
                        item_description=f"8-K filing - check for material events",
                        url=f"https://www.sec.gov/cgi-bin/viewer?action=view&cik={filing.get('cik_str')}&accession_number={filing.get('accession_number')}&xbrl_type=v",
                    )
                    events.append(event)
                except Exception as e:
                    log.debug(f"Error parsing 8-K for {ticker}: {e}")
                    continue

        except Exception as e:
            log.error(f"Error fetching 8-Ks from SEC: {e}")

        return events

    def fetch_form4_insider_trades(self, ticker: str, lookback_days: Optional[int] = None) -> List[SecEvent]:
        """Fetch Form 4 insider trading filings for a specific ticker.

        Form 4 = insider transactions (buys/sells by officers, directors, >10% holders)
        Heavy selling or large position accumulation can signal distress or opportunity.

        Args:
            ticker: stock ticker (e.g., "AAPL")
            lookback_days: override self.lookback_days

        Returns:
            List of SecEvent objects
        """
        events = []
        lookback = lookback_days or self.lookback_days

        try:
            params = {
                "action": "getcompany",
                "type": "4",
                "dateb": datetime.now().isoformat()[:10],
                "owner": "include",
                "match": "",
                "filenum": "",
                "State": "",
                "SIC": "",
                "myHID": "",
                "output": "json",
                "CIK": ticker,  # Can be ticker or CIK
                "count": 100,
            }

            resp = self.session.get(self.EDGAR_BROWSE, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            cutoff = datetime.now() - timedelta(days=lookback)

            for filing in data.get("filings", []):
                filing_date = filing.get("filing_date", "")
                if filing_date < cutoff.isoformat()[:10]:
                    continue

                try:
                    event = SecEvent(
                        ticker=ticker.upper(),
                        company_name=filing.get("company_name", "Unknown"),
                        cik=filing.get("cik_str", ""),
                        form_type="4",
                        filing_date=filing_date,
                        item_type=None,
                        item_description=f"Form 4 insider transaction - check for pattern (buys vs sells)",
                        url=f"https://www.sec.gov/cgi-bin/viewer?action=view&cik={filing.get('cik_str')}&accession_number={filing.get('accession_number')}&xbrl_type=v",
                    )
                    events.append(event)
                except Exception as e:
                    log.debug(f"Error parsing Form 4 for {ticker}: {e}")
                    continue

        except Exception as e:
            log.error(f"Error fetching Form 4 for {ticker}: {e}")

        return events

    def cache_to_file(self, events: List[SecEvent], path: str = "/app/data/sec_events.jsonl"):
        """Cache events to file for later processing.

        Args:
            events: list of SecEvent objects
            path: file path to write to
        """
        try:
            with open(path, "a") as f:
                for event in events:
                    f.write(json.dumps(event.to_dict()) + "\n")
            log.info(f"Cached {len(events)} SEC events to {path}")
        except Exception as e:
            log.error(f"Error caching SEC events: {e}")

    def load_cache(self, path: str = "/app/data/sec_events.jsonl", lookback_days: int = 7) -> List[SecEvent]:
        """Load recent cached SEC events.

        Args:
            path: file path to read from
            lookback_days: only return events from last N days

        Returns:
            List of SecEvent objects
        """
        events = []
        cutoff = datetime.now() - timedelta(days=lookback_days)

        try:
            with open(path, "r") as f:
                for line in f:
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if data.get("filing_date", "") >= cutoff.isoformat()[:10]:
                        events.append(SecEvent(**data))
        except FileNotFoundError:
            log.debug(f"No cache file at {path}")
        except Exception as e:
            log.error(f"Error loading SEC cache: {e}")

        return events
