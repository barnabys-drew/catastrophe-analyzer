# Event categories and news impact likelihood

This document is the **reference list** for `event_category` values (see `event_categories` in `config/settings.json` when implemented) and a **qualitative rating** of how often **firm-specific** headlines tend to produce **material short-horizon price moves** (intraday to a few days) for **listed equities**.

It is **not** investment advice, not a forecast, and **not** a guarantee of volatility. Ratings are rules-of-thumb for **prioritizing ingestion and alert design**.

## How to read the ratings

**Question answered:** If a credible news headline **clearly names (or unambiguously implies) one public company**, how **often** do you typically see a **meaningful** price reaction **soon** after the headline?

| Rating | Meaning |
|--------|---------|
| **High** | Very often a sharp move when the story is firm-specific and **new**. |
| **Medium–high** | Often material; sometimes waits for details, confirmation, or sizing. |
| **Medium** | Sometimes large; often smaller, or sector breadth dominates single names. |
| **Low–medium** | Frequently noisy; big moves usually need **specifics** (numbers, duration, guidance). |
| **Low** | Usually second-order, slow-burn, or hard to attribute to one ticker. |
| **Variable** | Depends heavily on **subtype** (split in the table). |

**Caveats:** Reaction size depends on **ticker identifiability**, **novelty** (vs priced-in), **liquidity**, **short interest**, and **macro regime** (risk-on days can dampen idiosyncratic shocks).

---

## Full impact likelihood table (by shock shape)

| Area / shock shape | Impact likelihood | Notes |
|--------------------|-------------------|--------|
| FDA / clinical (failure, hold, approval) | **High** | Binary outcomes; fast repricing. |
| Major recall / grounding / safety order | **High** | Revenue / legal tail risk priced quickly when scope is clear. |
| Antitrust / breakup / huge fine (firm-specific) | **Medium–high** | Large when it is *the* named company; sometimes partly anticipated. |
| Fraud / accounting / restatement / SEC–DOJ (firm-specific) | **High** | Especially when earnings credibility is in question. |
| Distress / covenant / restructuring / Ch.11 chatter | **High** | Capital-structure shocks; stronger in leveraged names. |
| Emergency financing / highly dilutive raise | **High** | Cap table math moves immediately. |
| M&A: deal announced / competing bids | **High** | Targets often gap; acquirer can move a lot too. |
| M&A: blocked deal / walk / break fee | **Medium–high** | Big for targets; acquirer reaction varies. |
| Major plant / refinery / mine / DC disaster (firm-specific) | **Medium–high** | Needs scale, duration, and clear revenue linkage. |
| Force majeure (firm-specific, quantified) | **Medium–high** | Stronger when volumes or timeline are concrete. |
| Large-scale outage (non-cyber ops / IT) | **Medium** | Leaders move; magnitude depends on revenue exposure clarity. |
| Cyber incident (material breach / ransom / outage) | **Medium–high** | High when **new and large**; many headlines are incremental. |
| Leadership scandal / CEO exit / indictment | **Medium–high** | Large when governance or cash flows are at risk; sometimes one-day. |
| Labor: national strike / prolonged stoppage (firm-specific) | **Medium–high** | Strong when cash burn or EPS path is obvious. |
| Consumer boycott / viral scandal | **Medium** | Huge for consumer brands when sales evidence appears; otherwise hype. |
| Geopolitics / war / sanctions (firm-specific transmission) | **Medium–high** | High when facilities, exports, or compliance are directly hit. |
| Trade policy (tariffs) hitting a named supply chain | **Medium** | Often sector ETFs move more unless exposure is obvious. |
| Commodity spike (helps / hurts one operator) | **Medium** | Clear for E&P vs airlines; murkier for diversified industrials. |
| Natural disaster hitting concentrated footprint | **Medium** | Insurance / complexity can dampen immediate single-name clarity. |
| Patent win / loss / cliff | **Medium–high** | High when revenue is concentrated; less for diversified portfolios. |
| Competitive “killer” launch / major share shift | **Medium** | Can be high; markets debate durability → slower or choppier. |
| AI / platform policy shifts affecting dependents | **Medium** | Often reprices groups; single-name attribution can lag. |
| “Good” shocks: beat-and-raise / major contract win | **High** | Often from **earnings / PR**, not general RSS—still very market-moving when **new**. |

---

## Canonical `event_category` ids (config + CSV)

Use these **stable snake_case** ids in configuration and in the `event_category` column on stored events.

### Prioritized for implementation (already on the product roadmap)

| `event_category` | Description |
|------------------|-------------|
| `cybersecurity` | Breaches, ransomware, major security incidents, large-scale cyber-driven outages. |
| `leadership_scandal` | CEO exit, board scandal, indictment, investigations with leadership / governance focus. |
| `supply_chain_disruption` | Ports, strikes, shortages, fires, logistics shocks with clear operational impact. |

### Added from **High** impact likelihood rows above

Each row below maps to the **High** tier in the table (or the “good shock” row rated High).

| `event_category` | Description |
|------------------|-------------|
| `clinical_regulatory_binary` | FDA actions, clinical holds / failures / approvals, binary regulatory outcomes for a named drug/device program. |
| `product_safety_recall` | Recalls, groundings, safety orders with immediate demand or liability implications. |
| `fraud_accounting_enforcement` | Fraud allegations, restatements, material accounting issues, significant SEC / DOJ enforcement against the issuer. |
| `financial_distress` | Covenant breach, restructuring, bankruptcy chatter, solvency stress for a named company. |
| `dilutive_financing` | Emergency equity, highly dilutive raises, sudden capital raises that reshape the cap table. |
| `ma_corporate_action` | M&A announced, competing bids, transformative deals (block / break in **medium–high** but same category id can cover subtypes). |
| `positive_earnings_catalyst` | Beat-and-raise, major contract win, transformative “good news” catalysts (often from earnings / company PR). |

### Optional merge notes

- You can **collapse** `clinical_regulatory_binary` and `product_safety_recall` into a single `regulatory_and_product_safety` category if you want fewer ids; split when keyword / source sets diverge.
- `ma_corporate_action` can hold both “deal on” and “deal off” **subtypes** via `event_subtype` without new top-level ids.

---

## Related project files

- Implementation plan (multi-category pipeline, Phase 1 cyber): see the Cursor plan *Catastrophe categories Phase 1*.
- [README.md](../README.md) — broader shock-event direction and example category table.
- [ARCHITECTURE.md](../ARCHITECTURE.md) — system modules and data flow.
