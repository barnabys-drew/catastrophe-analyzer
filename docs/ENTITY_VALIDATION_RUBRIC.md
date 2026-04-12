## Entity-to-Ticker Validation Rubric

Use this rubric when deciding whether an article should map to a public ticker.

### Approve only when ALL are true

- The article is clearly about the candidate company (not just a word overlap).
- The company is directly affected by the event (victim/operator/manufacturer/distributor/retailer, depending on category).
- The event is material enough to plausibly drive a legitimate buy-signal workflow after technical gates.

### Reject when ANY are true

- The match is a homonym, adjective, or food/common noun (for example: urgent, black beans, metal).
- The company is only a comparator, quote source, or unrelated mention.
- The article is too ambiguous to confirm the company is affected.

### Category reminders

- `cybersecurity`: target must be the breached/impacted entity.
- `clinical_regulatory_binary`: target must own the program tied to trial/FDA outcome.
- `product_safety_recall`: target must be tied to the recalled product chain.
  - Multi-issuer headlines can approve multiple public tickers from one article when each ticker has a direct role (for example retailer + manufacturer/distributor).
  - Do not collapse a retailer mention just because a different manufacturer is named; approve both when role context is explicit.

### Response format

Return:

- `approved`: boolean
- `confidence`: 0.0 to 1.0
- `reason`: short rationale
- `normalized_company_name`: optional cleaned canonical name
