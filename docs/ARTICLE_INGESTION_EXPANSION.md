# Article Ingestion Expansion — Task List

Goal: increase the volume and quality of articles/signals feeding the algorithm so it has enough data to prove itself.

Status legend: `[ ]` pending · `[~]` in progress · `[x]` done

---

## Phase 0 — Throttle lifts (config-only, zero risk)

- [x] Bump `scraping.hours_back` from 24 → 72 in `config/settings.json`
- [x] Bump `scraping.max_article_age_hours` from 24 → 72
- [x] Bump `scraping.max_results_per_source` from 50 → 100
- [x] Rewrite all 58 Google News RSS URLs using `when:1d` → `when:3d` to match extended window

---

## Phase 1 — Keyword expansion in existing 20 categories

Add high-signal keywords that are currently missing. ~300-500 total additions.
**Done: +~600 keywords added, total now 1,240 across 20 categories.**

- [x] **cybersecurity** — add `leak site`, `double extortion`, `claimed by <group>`, `Item 1.05`, `BEC`, `business email compromise`, `credential stuffing`, `stolen source code`, `CISA KEV`, `DDoS`, `MOVEit-style`, `data extortion`, `incident response firm retained`, `contained the incident`, `bricked systems`, `operational technology`, `OT attack`, `cyber insurance claim`
- [x] **clinical_regulatory_binary** — add `DSMB halt`, `DMC recommendation`, `dose-limiting toxicity`, `approvable letter`, `label expansion`, `boxed warning`, `sBLA`, `sNDA`, `adcom vote`, `ODAC`, `enrollment pause`, `enrollment halt`, `statistical significance`, `hit primary endpoint`, `fast track designation`, `orphan drug`, `EUA revoked`, `withdrawal from market`
- [x] **product_safety_recall** — add `recall expanded`, `expanded recall`, `voluntary recall`, `mandatory recall`, `consumer advisory`, `NHTSA investigation`, `defect investigation`, `infant formula`, `blood clots`, `adverse reactions`, `reports of injuries`, `serious adverse event`, `FAA directive`
- [x] **fraud_accounting_enforcement** — add `whistleblower complaint`, `parallel investigation`, `criminal probe`, `corporate monitor`, `compliance monitor`, `SDNY indictment`, `EDNY indictment`, `FBI investigation`, `grand jury`, `cooperating witness`, `plea agreement`
- [x] **financial_distress** — add `DIP financing`, `debtor-in-possession`, `bridge financing`, `cash runway`, `liquidity squeeze`, `store closures`, `mass layoffs`, `creditor protection`, `RSA signed`, `ad hoc group`, `funding runway`, `tight liquidity`, `CCAA protection`, `prepackaged bankruptcy`
- [x] **dilutive_financing** — add `upsize offering`, `increased offering`, `overallotment option`, `greenshoe`, `unit offering`, `convertible note issuance`, `term loan amendment`, `reverse stock split`
- [x] **ma_corporate_action** — add `reverse termination fee`, `second request`, `HSR pulled and refiled`, `break fee`, `CFIUS review`, `CFIUS blocked`, `merger cleared`, `shareholder vote rejected`, `topping bid`, `revised offer`
- [x] **positive_earnings_catalyst** — add `raised full-year`, `outperformed consensus`, `order book strong`, `book-to-bill above 1`, `positive operating leverage`, `margin beat`
- [x] **negative_earnings_catalyst** — add `lowered FY`, `softer demand`, `push-out`, `order cancellations`, `slipped to next quarter`, `order pushouts`, `demand weakness`, `inventory build`
- [x] **short_seller_report** — add `Citron Research`, `Culper Research`, `GMT Research`, `Sohn short pitch`, `accounting red flags`, `report alleges`, `short thesis published`, `Night Market Research`, `J Capital`
- [x] **credit_rating_action** — add `KBRA downgrade`, `DBRS downgrade`, `Morningstar DBRS`, `rating watch negative`, `creditwatch negative`, `under review for downgrade`, `rating withdrawn`
- [x] **going_concern_auditor_change** — add `non-reliance`, `PCAOB inspection`, `restated prior periods`, `rescinded financial statements`
- [x] **guidance_cut_preannouncement** — add `trajectory slower`, `softer demand`, `order cancellations`, `push out revenue`, `slip to next quarter`, `revising lower`, `tempering expectations`
- [x] **activist_13d_filing** — add `Third Point`, `ValueAct`, `D.E. Shaw activist`, `Blue Harbour`, `withhold vote`, `say-on-pay against`, `proxy advisory firm`, `ISS recommends against`, `Glass Lewis recommends against`, `vote no campaign`
- [x] **labor_action** — add `contract expires`, `cooling off period`, `NLRB charge`, `unionization vote`, `union election`, `successor contract rejected`, `hot cargo`
- [x] **securities_class_action** — add `Kessler Topaz`, `Hagens Berman`, `Bernstein Litowitz`, `Motley Rice`, `class period announced`, `putative class`, `first amended complaint`
- [x] **insider_trading_cluster** — add `accelerated share sales`, `unscheduled sale`, `non-10b5-1 sale`, `outside trading plan`, `large open-market sale`
- [x] **supply_chain_disruption** — add `key supplier fire`, `wafer shortage`, `substrate shortage`, `Red Sea diversion`, `Panama Canal restriction`, `tier 2 supplier`, `sole-source`, `qualification delay`
- [x] **geopolitical_sanctions_exposure** — add `Bureau of Industry and Security`, `Commerce Department list`, `unverified list`, `military end user list`, `Treasury sanctions`, `sanctioned by OFAC`, `delisted from sdn`, `foreign direct product rule`

---

## Phase 2 — Add SEC EDGAR 8-K item-specific RSS feeds

8-K item feeds are the single highest-signal free source. Companies *must* file these.

- [x] Add 8-K Item 1.05 feed (material cybersecurity incident) → `cybersecurity` category
- [x] Add 8-K Item 2.04 feed (triggering events accelerating debt) → `financial_distress`
- [x] Add 8-K Item 2.06 feed (material impairments) → `negative_earnings_catalyst`
- [x] Add 8-K Item 3.01 feed (delisting notice) → `fraud_accounting_enforcement`
- [x] Add 8-K Item 4.01 feed (auditor change) → `going_concern_auditor_change`
- [x] Add 8-K Item 4.02 feed (non-reliance on prior financials) → `going_concern_auditor_change` **highest signal**
- [x] Add 8-K Item 5.02 feed (departure of directors/officers) → `leadership_scandal`
- [x] Add 8-K Item 7.01 feed (Reg FD disclosure) → generic catalyst
- [x] Add Form NT 10-K feed (late annual filing) → `going_concern_auditor_change`
- [x] Add Form NT 10-Q feed (late quarterly filing) → `going_concern_auditor_change`

---

## Phase 3 — Add PR wire services (self-disclosure firehose)

These hit before Google News indexes them. High volume, micro-cap coverage.

- [x] Add PR Newswire all-news RSS
- [x] Add BusinessWire by-category RSS (health, tech, finance)
- [x] Add GlobeNewswire RSS (often where biotechs announce trial results)
- [x] Add ACCESSWIRE RSS (small-cap heavy)

---

## Phase 4 — Other high-value free sources

- [x] Add FDA MAUDE device adverse events feed
- [x] Add FDA Warning Letters weekly RSS
- [x] Add CISA Known Exploited Vulnerabilities (KEV) catalog RSS → `cybersecurity`
- [x] Add CourtListener RSS for securities class actions (SDNY, NDCA, District of Delaware)
- [x] Add FINRA Reg SHO daily threshold securities → `financial_distress` companion signal
- [x] Add FTC press releases RSS (beyond what's in M&A category)
- [x] Add EPA enforcement news RSS → future `environmental_incident` category
- [x] Add NHTSA recalls RSS → `product_safety_recall`
- [x] Add OFAC recent actions RSS → `geopolitical_sanctions_exposure`

---

## Phase 5 — New event categories

Each needs keywords + sources + triage thresholds in settings.

- [x] **key_customer_contract_loss** — "loses Apple as customer"-style catalysts
- [x] **patent_ip_loss** — PTAB IPR decisions, ITC 337, Markman rulings, patent invalidation
- [x] **environmental_incident** — refinery fires, spills, derailments, explosions
- [x] **license_revocation_regulatory_ban** — state AG actions, operating license pulls
- [x] **mass_tort_product_liability** — talc, PFAS, opioid-pattern litigation
- [x] **bank_credit_deterioration** — NPL spikes, loan loss provisions, CRE exposure
- [x] **insurance_cat_loss** — hurricane/wildfire reserve charges

---

## Phase 6 — Alternative signal channels (larger lifts)

- [ ] Reddit sentiment via Pushshift/PullPush (r/wallstreetbets, r/stocks, r/pennystocks)
- [ ] StockTwits trending tickers API
- [ ] Unusual options activity from CBOE end-of-day feeds
- [ ] Glassdoor CEO-rating delta tracker
- [ ] LinkedIn job-posting volume drops (layoff precursor)
- [ ] Earnings call transcript sentiment delta (Seeking Alpha)

---

## Execution notes

- Keyword changes are instantly reversible (just edit settings.json).
- 8-K feeds require verifying SEC RSS URLs work and aren't rate-limited.
- PR wire additions may need per-source `max_results` to avoid noise flood.
- New categories require distress/impact threshold tuning; start conservative.
