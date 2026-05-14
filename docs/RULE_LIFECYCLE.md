# Rule Lifecycle

Rules move through explicit review states.

## Draft

Suggestion promotion creates inactive draft rules:

```text
status=draft
active=false
```

Draft rules do not affect evaluator behavior.

## Activation

Activate only after review, backtest, and paper-trade validation:

```bash
curl -X PATCH "http://localhost:8000/rules/DRAFT-RETRACEMENT-LRHR/activation" \
  -H "Content-Type: application/json" \
  -d '{"active":true,"validation_note":"Backtest and paper-trade review passed."}'
```

Activation sets:

```text
status=active_reviewed
active=true
```

Deactivation uses the same endpoint with `active=false`.

All activation changes are written to the audit log.
