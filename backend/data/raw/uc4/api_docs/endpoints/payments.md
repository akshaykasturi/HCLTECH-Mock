---
title: Payments endpoints
version: "2.3"
status: current
updated: 2026-09-01
product: NovaPay Commerce API
---
# Payments endpoints

## POST /v1/payments

Authorise and capture a payment through the external bank gateway.

- Service: `payments-api`; dependencies: `bank-gateway`
- Required scope: `payments:write`
- IP allowlist enforced: yes
- Typical latency: p50 280 ms, p95 850 ms; gateway timeout 10000 ms
- Possible errors: 400, 401, 403, 415, 429, 500, 502, 503, 504

### Required fields

`amount`, `currency`, `payment_method_id`. Body must be `application/json`.
