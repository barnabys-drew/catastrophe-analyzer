"""SEC EDGAR 8-K feed via the EFTS full-text search API."""
import json
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Optional, List
import requests
from dataclasses import dataclass

log = logging.getLogger("sec_feed")

# 8-K item → CA event category mapping
ITEM_TO_CATEGORY = {
    "1.01": "ma_corporate_action",          # Entry into Material Definitive Agreement
    "1.02": "ma_corporate_action",          # Termination of Material Agreement
    "1.03": "financial_distress",           # Bankruptcy or Receivership
    "2.01": "ma_corporate_action",          # Completion of Acquisition/Disposition
    "2.02": "positive_earnings_catalyst",   # Results of Operations (earnings)
    "2.03": "financial_distress",           # Creation of Direct Financial Obligation
    "2.04": "financial_distress",           # Triggering Events Creating Obligation
    "2.05": "financial_distress",           # Costs Associated with Exit Activities
    "2.06": "financial_distress",           # Material Impairments
    "3.01": "financial_distress",           # Delisting or Failure of Listing Rule
    "4.01": "going_concern_auditor_change", # Change of Certifying Accountant
    "4.02": "fraud_accounting_enforcement", # Non-Reliance on Prior Financial Statements
    "5.01": "ma_corporate_action",          # Change in Control
    "5.02": "leadership_scandal",           # Departure/Appointment of Directors or Officers
    "7.01": None,                           # Reg FD Disclosure (press release — skip)
    "8.01": None,                           # Other Events (too broad — skip)
    "9.01": None,                           # Financial Statements/Exhibits (attachment — skip)
}

ITEM_DESCRIPTIONS = {
    "1.01": "Entry into Material Definitive Agreement",
    "1.02": "Termination of Material Definitive Agreement",
    "1.03": "Bankruptcy or Receivership",
    "2.01": "Completion of Acquisition or Disposition of Assets",
    "2.02": "Results of Operations (Earnings Report)",
    "2.03": "Creation of Direct Financial Obligation",
    "2.04": "Triggering Events Creating Financial Obligation",
    "2.05": "Exit or Disposal Activity Costs",
    "2.06": "Material Impairment",
    "3.01": "Delisting or Failure to Satisfy Listing Rule",
    "4.01": "Change of Certifying Accountant",
    "4.02": "Non-Reliance on Previously Issued Financial Statements",
    "5.01": "Change in Control of Registrant",
    "5.02": "Departure or Appointment of Director / Principal Officer",
    "7.01": "Regulation FD Disclosure",
    "8.01": "Other Events",
    "9.01": "Financial Statements and Exhibits",
}


@dataclass
class SecEvent:
    """SEC filing event."""
    ticker: str
    company_name: str
    cik: str
    form_type: str
    filing_date: str
    item_type: Optional[str]
    item_description: str
    url: str
    event_category: Optional[str] = None
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
            "event_category": self.event_category,
            "source": self.source,
        }


def _extract_ticker(display_name: str) -> str:
    """Extract ticker from 'COMPANY NAME  (TICKER)  (CIK 0001234567)'."""
    matches = re.findall(r'\(([^)]+)\)', display_name)
    for m in matches:
        m = m.strip()
        if m.startswith("CIK"):
            continue
        if 1 <= len(m) <= 6 and m.isupper() and m.isalpha():
            return m
    return ""


class SecFeed:
    """Fetch 8-K filings from SEC EDGAR via the EFTS full-text search API."""

    EFTS_URL = "https://efts.sec.gov/LATEST/search-index"

    def __init__(self, lookback_days: int = 3, rate_limit_delay: float = 0.5,
                 user_agent: str = "CatastropheAnalyzer/1.0 drewtheguitarguy@gmail.com"):
        self.lookback_days = lookback_days
        self.rate_limit_delay = rate_limit_delay
        self.last_request_time = 0.0
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def _rate_limit(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def fetch_recent_8ks(self, limit: int = 100, use_mock: bool = False) -> List[SecEvent]:
        """Fetch recent 8-K filings via EFTS search API.

        Only returns filings with high-signal item types (1.01-5.02).
        Items 7.01, 8.01, 9.01 (press releases / exhibits) are skipped.
        """
        if use_mock:
            try:
                from sec_feed_mock import generate_mock_8ks
                return generate_mock_8ks()[:limit]
            except ImportError:
                return []

        events: List[SecEvent] = []
        start_date = (datetime.now() - timedelta(days=self.lookback_days)).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")

        params = {
            "q": "",
            "forms": "8-K",
            "dateRange": "custom",
            "startdt": start_date,
            "enddt": end_date,
            "hits.hits.total.value": 1,
        }

        try:
            self._rate_limit()
            resp = self.session.get(self.EFTS_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.error(f"SEC EDGAR fetch failed: {e}")
            return []

        hits = data.get("hits", {}).get("hits", [])
        for hit in hits[:limit]:
            src = hit.get("_source", {})
            items = src.get("items", [])
            display_names = src.get("display_names", [])
            file_date = src.get("file_date", "")
            cik_list = src.get("ciks", [""])
            cik = cik_list[0].lstrip("0") if cik_list else ""
            adsh = src.get("adsh", "").replace("-", "")
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh}/" if cik and adsh else ""

            company_name = display_names[0].split("(")[0].strip() if display_names else "Unknown"
            ticker = ""
            for dn in display_names:
                ticker = _extract_ticker(dn)
                if ticker:
                    break

            if not ticker:
                continue

            # Build one event per actionable item (skip 7.01, 8.01, 9.01)
            actionable_items = [i for i in items if ITEM_TO_CATEGORY.get(i) is not None]
            if not actionable_items:
                continue

            for item in actionable_items[:2]:  # max 2 items per filing
                category = ITEM_TO_CATEGORY.get(item)
                desc = ITEM_DESCRIPTIONS.get(item, f"8-K Item {item}")
                event = SecEvent(
                    ticker=ticker,
                    company_name=company_name,
                    cik=cik,
                    form_type="8-K",
                    filing_date=file_date,
                    item_type=f"Item {item}",
                    item_description=desc,
                    url=url,
                    event_category=category,
                )
                events.append(event)

        log.info(f"SEC EDGAR: fetched {len(hits)} 8-Ks, {len(events)} actionable events ({start_date} to {end_date})")
        return events

    def fetch_form4_insider_trades(self, ticker: str, lookback_days: Optional[int] = None,
                                   use_mock: bool = False) -> List[SecEvent]:
        """Fetch Form 4 insider trades for a specific ticker."""
        if use_mock:
            return []

        lookback = lookback_days or self.lookback_days
        start_date = (datetime.now() - timedelta(days=lookback)).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")

        params = {
            "q": f'"{ticker}"',
            "forms": "4",
            "dateRange": "custom",
            "startdt": start_date,
            "enddt": end_date,
        }

        events: List[SecEvent] = []
        try:
            self._rate_limit()
            resp = self.session.get(self.EFTS_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.error(f"SEC Form 4 fetch failed for {ticker}: {e}")
            return []

        hits = data.get("hits", {}).get("hits", [])
        for hit in hits[:20]:
            src = hit.get("_source", {})
            display_names = src.get("display_names", [])
            t = ""
            for dn in display_names:
                t = _extract_ticker(dn)
                if t:
                    break
            if t.upper() != ticker.upper():
                continue

            cik_list = src.get("ciks", [""])
            cik = cik_list[0].lstrip("0") if cik_list else ""
            adsh = src.get("adsh", "").replace("-", "")
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh}/" if cik and adsh else ""

            events.append(SecEvent(
                ticker=ticker.upper(),
                company_name=display_names[0].split("(")[0].strip() if display_names else "Unknown",
                cik=cik,
                form_type="4",
                filing_date=src.get("file_date", ""),
                item_type=None,
                item_description="Form 4 insider transaction",
                url=url,
                event_category="insider_trading_cluster",
            ))

        return events

    def cache_to_file(self, events: List[SecEvent], path: str = "/app/data/sec_events.jsonl"):
        try:
            import os
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a") as f:
                for event in events:
                    f.write(json.dumps(event.to_dict()) + "\n")
        except Exception as e:
            log.warning(f"Failed to cache SEC events: {e}")
