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
- `fraud_accounting_enforcement` (SEC + DOJ RSS, multiple Google News lanes, Reuters/MarketWatch/Yahoo headline feeds; tune keywords to reduce noise)

### Next expansion candidates (keep these)

- `leadership_scandal`
- `supply_chain_disruption`
- `product_safety_recall`
- `financial_distress`
- `dilutive_financing`
- `ma_corporate_action`
- `positive_earnings_catalyst`

### Optional structural notes

- If needed, merge `clinical_regulatory_binary` + `product_safety_recall` into one regulatory/product safety family, then split later when source and keyword sets diverge.
- Keep M&A outcomes as subtypes under `ma_corporate_action` rather than creating many top-level categories.

## Usage guidance

- Keep category ids stable once used in persisted data.
- Add per-category keyword/source bundles in `config/settings.json`.
- Keep category-specific subtype and distress heuristics in `src/main.py`.
