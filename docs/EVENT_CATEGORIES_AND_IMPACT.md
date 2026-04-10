# Event Categories and Impact Likelihood

This is the taxonomy reference for `event_category` values and category expansion planning.

It helps prioritize ingestion depth and signal design by category.

## Reading the impact levels

These ratings describe how often firm-specific headlines create meaningful short-horizon price moves.

- **High**: often sharp, immediate repricing
- **Medium-high**: frequently material, depends on detail quality
- **Medium**: mixed, often needs context to move single names
- **Low-medium / Low**: usually noisy or second-order

## Impact table (condensed)

| Shock shape | Likelihood | Why it matters |
|---|---|---|
| FDA/clinical binary outcomes | High | Binary value resets are common |
| Product recall / grounding / major safety action | High | Direct revenue and liability pressure |
| Fraud/accounting/enforcement | High | Credibility and capital access risk |
| Financial distress / covenant / restructuring | High | Solvency risk reprices quickly |
| Dilutive emergency financing | High | Immediate cap table impact |
| M&A announce / competing bid | High | Event-driven repricing |
| Cyber incident (material) | Medium-high | Often material when scope is clear |
| Leadership scandal / forced exits | Medium-high | Governance and execution uncertainty |
| Supply chain disruption (firm-specific) | Medium-high | Throughput and margin risk |
| Commodity/policy/geopolitical transmission | Medium | Exposure clarity varies |
| Natural disaster concentrated footprint | Medium | Depends on concentration and duration |

## Canonical `event_category` ids

### Active depth today

- `cybersecurity`
- `clinical_regulatory_binary`
- `product_safety_recall` (baseline wired; continue expanding source and subtype depth)
- `fraud_accounting_enforcement` (SEC + DOJ RSS, multiple Google News lanes, Reuters/MarketWatch/Yahoo; **set a real `scraping.http_user_agent` or `CATASTROPHE_HTTP_USER_AGENT`** for SEC and other bot-filtering feeds — see `config/settings.json`)
- `supply_chain_disruption` (trade RSS + Google News lanes; operational/logistics shocks — distinct from cyber “supply chain attack”)
- `financial_distress` (bankruptcy/covenant/liquidity lane with restructuring-focused feeds + Google News recency lanes)
- `dilutive_financing` (equity/convertible/warrant issuance lane with financing-specific source queries)
- `ma_corporate_action` (deal announce/competing bid/regulatory block lane; keep outcomes as subtypes)
- `leadership_scandal` (governance/executive-turnover scandal lane with board/ethics probe detection)
- `positive_earnings_catalyst` (raised-guidance/beat lane; currently buy-oriented and paired with lower distress gate)

### Next expansion candidates (keep these)

- `product_safety_recall`

### Optional structural notes

- If needed, merge `clinical_regulatory_binary` + `product_safety_recall` into one regulatory/product safety family, then split later when source and keyword sets diverge.
- Keep M&A outcomes as subtypes under `ma_corporate_action` rather than creating many top-level categories.

## Usage guidance

- Keep category ids stable once used in persisted data.
- Add per-category keyword/source bundles in `config/settings.json`.
- Keep category-specific subtype and distress heuristics in `src/main.py`.
