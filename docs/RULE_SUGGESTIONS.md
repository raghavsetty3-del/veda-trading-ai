# Rule Suggestions

Rule suggestions are generated from extracted insights. They are review-only and do not modify live rules automatically.

Current suggestion templates look for:

- Wait for retracement
- Avoid chasing
- Use 200 EMA context
- Avoid choppy or low ADX markets
- Require risk controls

API:

```bash
curl "http://localhost:8000/suggestions/rules?limit=200"
```

Each suggestion includes:

- Candidate rule code and name
- Candidate principle title
- Expected behavior
- Number of supporting insights
- Average confidence
- Source insight IDs

Promoting a suggestion into a live rule should remain a manual reviewed step until paper trading and backtesting are stronger.

## Promotion

Promoting a suggestion creates:

- A review-derived `AuthorPrinciple`
- A `RuleMapping` with `status=draft`
- `active=false`, so the rule does not affect live evaluation until explicitly reviewed and activated later

API:

```bash
curl -X POST "http://localhost:8000/suggestions/rules/SUGGEST-RETRACEMENT-LRHR/promote" \
  -H "Content-Type: application/json" \
  -d '{"review_note":"Approved for draft review."}'
```
