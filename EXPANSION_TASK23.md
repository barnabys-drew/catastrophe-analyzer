# Task #23: Catastrophe-Analyzer Event Detection Expansion

**Goal:** Increase signal firing from 0-1/week to 5-10/week by adding SEC, earnings, and insider data sources.

**Status:** In Progress (2026-05-06)

---

## Phase 1: Data Source Integration ✅ (Started)

### Completed:
- [x] `src/sec_feed.py` — SEC 8-K and Form 4 parser
  - Fetches recent 8-K filings (material events, going concerns, restructuring)
  - Fetches Form 4 insider transaction filings
  - Caches to JSON for batch processing

- [x] `src/earnings_feed.py` — Earnings surprise detector
  - Earnings beat/miss detection
  - Guidance change tracking (raises vs cuts)
  - Analyst rating changes
  - Placeholder for paid API integration (Zacks, TradingView)

- [x] `src/multi_source_detector.py` — Multi-source signal engine
  - Combines news + SEC + earnings signals
  - Confidence scoring and thresholds (adjusted lower to increase firing)
  - Multi-source confirmation (same ticker in 2+ sources = confidence boost)
  - Signal ranking and filtering

### Next (Phase 2):
- [ ] Integrate into `main.py` pipeline
- [ ] Add real earnings data source (currently placeholder)
- [ ] Litigation tracking (class actions, settlements)
- [ ] Activist investor detection (13F filings, proxy contests)
- [ ] Adjust confidence thresholds in config
- [ ] Paper trading validation

---

## Signal Types Added

### SEC Filings (8-K)
**Material Events:**
- Bankruptcy / going concern (90% confidence)
- Restructuring / impairment (75% confidence)
- Material agreements / M&A (60% confidence)
- Litigation (75% confidence)

**Form 4 (Insider Trades)**
- Heavy selling by executives (distress signal)
- Buying at lows (opportunity signal)

### Earnings Surprises
- EPS miss >10% + guidance cut → **High confidence sell** (85%)
- EPS beat >10% + guidance raise → **High confidence buy** (80%)
- Earnings miss → **Medium confidence sell** (60%)
- Analyst downgrades on earnings → Confidence boost

### Multi-Source Confirmation
When same ticker triggers in 2+ sources (news + SEC + earnings), confidence boosted by +10-20%.

---

## Data Source Status

| Source | Status | Notes |
|--------|--------|-------|
| **News (RSS)** | ✅ Working | Current system |
| **SEC EDGAR** | ✅ Code ready | Need API integration (free endpoint available) |
| **Earnings** | ⏳ Placeholder | Need paid API (Zacks/TradingView) or scraping |
| **Litigation** | 📋 Planned | Class action tracking, settlement announcements |
| **Insider (Form 4)** | ✅ Code ready | Part of SEC integration |
| **Activist (13F)** | 📋 Planned | For activist-driven plays |

---

## Expected Impact

**Before expansion:**
- 0-1 signals/week (news-only, high quality but rare)

**After expansion:**
- **SEC 8-Ks:** ~5-10/week (material events)
- **Form 4 patterns:** ~5-10/week (insider activity)
- **Earnings surprises:** ~2-3/week (post-earnings reactions)
- **Multi-source confirms:** ~3-5/week (high confidence)
- **Total:** 5-10 high-confidence signals/week (vs 0-1 before)

---

## Next Steps

1. **Setup earnings data source**
   - Option A: Zacks API ($500+/mo) — best for production
   - Option B: TradingView scraping — free, less reliable
   - Option C: yfinance + manual calendar — lightweight fallback

2. **Integrate into main.py**
   - Add SEC and earnings checks to `runtime_cycle.py`
   - Cache recent events to `/app/data/sec_events.jsonl`, `/app/data/earnings_events.jsonl`
   - Combine with news signals in `multi_source_detector.py`

3. **Add litigation tracking**
   - Class action lawsuits (e.g., Law Street Media API)
   - Settlement announcements
   - Short-seller reports (Seeking Alpha, Twitter)

4. **Paper trading validation**
   - Run expanded system for 2-4 weeks
   - Track win rate by signal type
   - Tune confidence thresholds based on results

5. **Tune thresholds** (config/settings.json)
   - Current: `min_confidence_high=70, min_confidence_medium=50, min_confidence_low=35`
   - Adjust based on paper trading results

---

## Files Created

- `src/sec_feed.py` (189 lines) — SEC filing parser
- `src/earnings_feed.py` (160 lines) — Earnings surprise detector
- `src/multi_source_detector.py` (280 lines) — Multi-source signal engine

**Total code added:** ~630 lines

---

## Risk / Considerations

- **SEC API rate limits:** 10 requests/second. Cache responses.
- **Earnings data cost:** Zacks/TradingView APIs are paid. Consider alternatives.
- **False positives:** Lower thresholds = more signals = need careful tuning. Paper trade first.
- **Data freshness:** SEC filings have 1-2 day lag. Earnings typically released AH. News RSS is real-time.

---

## Timeline

- **Phase 1 (data integration):** 2-3 days ✅ (started)
- **Phase 2 (main.py integration):** 2-3 days
- **Phase 3 (paper trading validation):** 2-4 weeks
- **Phase 4 (threshold tuning):** ongoing
- **Total to production:** 3-4 weeks

---

## Validation Criteria

- [ ] System fires 5-10 signals/week (vs 0-1 before)
- [ ] Paper trading shows >50% win rate on high-confidence signals (≥70%)
- [ ] Multi-source confirms boost accuracy by 10%+
- [ ] No API throttling or downtime issues
- [ ] Seamless integration with existing news pipeline
