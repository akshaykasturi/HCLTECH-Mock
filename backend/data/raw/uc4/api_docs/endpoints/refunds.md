---
title: Refunds endpoints
version: "2.3"
status: current
updated: 2026-09-01
product: NovaPay Commerce API
---
# Refunds endpoints

## POST /v1/refunds

Refund all or part of a captured payment.

- Service: `payments-api`; dependencies: `payments-svc`
- Required scope: `refunds:write`
- IP allowlist enforced: yes
- Typical latency: p50 220 ms, p95 700 ms; gateway timeout 10000 ms
- Possible errors: 400, 401, 403, 415, 429, 500, 502, 503, 504

### Required fields

`payment_id`, `amount`, `reason`. Body must be `application/json`.
