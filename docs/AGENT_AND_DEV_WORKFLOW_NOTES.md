# Agent and Dev Workflow Notes

This file is a practical handoff note for contributors using both manual development and AI-assisted workflows.

## Runtime-first rule

- Treat `src/monitor.py` + `service_runtime.py` as the production path.
- Use `src/main.py` interactive menu for debugging, not as runtime truth.
- Any behavior change that affects runtime should be visible through `monitor.py --once`.

## Fast validation loop

1. Edit code/config.
2. Run a service-path smoke test from `src/`:
   - `python3 monitor.py --once --quiet`
3. Validate heartbeat:
   - `data/runtime_heartbeat.json` should show `status: ok` unless intentionally testing failures.
4. Run targeted tests for changed modules.

## Signal-quality guardrails

- Keep naming canonical in new work:
  - `event_category`
  - `event_subtype`
  - `event_date`
- Distress scoring in `main.py` is the category-aware source of truth.
- Impact triage should layer on top of distress context rather than duplicating full category logic.

## Output and operator UX

- `--quiet` should avoid banner/noise output while still allowing durable artifacts (CSV + heartbeat).
- Prefer compact one-line operational logs in service mode.
- Use staged signal counters for tuning:
  - `signals_generated_raw`
  - `signals_after_confidence_gate`
  - `signals_after_triage_gate`
  - `signals_saved`

## Scope control (avoid complexity creep)

- Prefer extending existing modules over adding parallel paths.
- Remove unused config keys only when replacement behavior exists.
- Keep docs synced when adding/removing categories or runtime toggles:
  - `README.md`
  - `ARCHITECTURE.md`
  - `docs/EVENT_CATEGORIES_AND_IMPACT.md`
