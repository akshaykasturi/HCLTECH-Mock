---
title: Orders endpoints
version: "2.3"
status: current
updated: 2026-09-01
product: NovaPay Commerce API
---
# Orders endpoints

## POST /v1/orders

Create an order. Reserves stock with inventory-svc and authorises payment with payments-svc.

- Service: `orders-api`; dependencies: `payments-svc`, `inventory-svc`
- Required scope: `orders:write`
- IP allowlist enforced: no
- Typical latency: p50 120 ms, p95 380 ms; gateway timeout 10000 ms
- Possible errors: 400, 401, 403, 415, 429, 500, 502, 503, 504

### Required fields for POST /v1/orders

`items`, `customer_id`, `currency`. Body must be `application/json`.

`currency` (ISO 4217, e.g. `INR`) is required since release 2.3 (2026-09-01).

## GET /v1/orders/{id}

Fetch one order by id.

- Service: `orders-api`; dependencies: `orders-db`
- Required scope: `orders:read`
- IP allowlist enforced: no
- Typical latency: p50 35 ms, p95 110 ms; gateway timeout 10000 ms
- Possible errors: 401, 403, 429, 500, 503, 504
