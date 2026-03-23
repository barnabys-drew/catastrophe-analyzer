# Category Expansion + Signal Quality TODO

Execution checklist to expand beyond current categories while keeping signals high quality and alerts fast/actionable.

## Priority order for remaining categories

- [ ] `fraud_accounting_enforcement`
- [ ] `financial_distress`
- [ ] `dilutive_financing`
- [ ] `ma_corporate_action`
- [ ] `leadership_scandal`
- [ ] `supply_chain_disruption`
- [ ] `positive_earnings_catalyst`

## Per-category implementation checklist

For each category above:

- [ ] Add category block in `config/settings.json` with `enabled`, keywords, and distress gate threshold.
- [ ] Add at least 3-6 high-quality sources (trade press + broad feed + Google News query with recency filter).
- [ ] Add category-specific subtype/severity mapping in `src/main.py` (`_classify_event_subtype_and_severity`).
- [ ] Add category-specific distress heuristics in `src/main.py` (`_financial_distress_assessment`).
- [ ] Add category-specific impact weights in `src/impact_triage.py` deterministic scorer.
- [ ] Confirm watch creation + dedupe keys are stable in `src/database_manager.py`.
- [ ] Verify monitor path sends high-value alerts and marks triage `SENT` once delivered.

## Signal quality hardening tasks

- [ ] Add category-specific signal thresholds (RSI/drop/volume) so one rule set is not forced on all shock types.
- [ ] Add rejection reasons to analysis output (`why no signal`) for better tuning feedback loops.
- [ ] Add minimum liquidity/price filters (for example, min avg volume and min price).
- [ ] Add stale-news guardrail (drop articles older than configured max hours unless explicitly allowed).
- [ ] Add confidence calibration pass against historical outcomes (win rate by confidence bucket).
- [ ] Add false-positive audit: weekly review of top alerted events that did not move price.

## Testing plan (must pass before enabling a new category)

- [ ] Unit-style checks for parser/classification/distress scoring on curated headline fixtures.
- [ ] Integration run: `python src/monitor.py --once --quiet` with mounted `config/` and `data/`.
- [ ] Docker parity run: build image, run one cycle, confirm no runtime import/config errors.
- [ ] Data integrity checks: no duplicate watches/signals for same `(ticker, event_date, event_category)`.
- [ ] Triage state checks: `NEW -> SENT -> ACKED/SUPPRESSED` transitions behave correctly.
- [ ] Alert regression: ntfy message format, priority, and payload content are correct.

## Quick outreach reliability checklist

- [ ] Define alert SLA target (example: deliver high-value event alert within 2 minutes of detection).
- [ ] Ensure ntfy is primary and tested (`alert_channels.ntfy.enabled = true`) with production topic.
- [ ] Add short alert format for urgent mobile outreach (ticker + category + impact/distress + action link).
- [ ] Add retry/backoff for outbound alert failures and persist failure reason.
- [ ] Add duplicate suppression window per event key to avoid noisy repeat outreach.
- [ ] Add daily summary alert (top 5 high-value events + top 5 signals) for fast situational awareness.

## Operational dashboards and review cadence

- [ ] Add CLI/report view for weekly precision metrics by category:
  - alerts sent
  - alerts acked
  - signal hit rate
  - false-positive rate
- [ ] Run weekly threshold tuning using the above metrics.
- [ ] Keep one changelog line per tuning change (what moved, why, expected effect).

## Definition of done for each new category

- [ ] Category is enabled in Docker runtime config.
- [ ] At least one live `--once` cycle processes category articles end to end.
- [ ] At least one high-value event is triaged and alert flow is verified.
- [ ] No linter/syntax errors and no new duplicate-alert regressions.
- [ ] Category added to docs list of active depth categories once stable.
