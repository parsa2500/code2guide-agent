# Abstain / confidence API (اهرم ۲)

## Endpoints
`POST /api/v1/ask` and `POST /api/v1/ask-enduser` now return:

| field | type | meaning |
|-------|------|---------|
| `confidence` | float 0..1 | min signal strength |
| `abstain` | bool | if true, guide is non-step «نمی‌دانم» |
| `reason_codes` | string[] | e.g. `unknown_intent`, `weak_fe_be_link`, `no_evidence`, `no_route` |

## Threshold
Default `τ = 0.75`. Abstain when confidence < τ (and for `unknown_intent` / `no_evidence` always).

## Trade-off
latency≈0 · cost≈0 · trust↑ · coverage↓
