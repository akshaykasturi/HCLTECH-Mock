---
title: Inventory endpoints
version: "2.3"
status: current
updated: 2026-09-01
product: NovaPay Commerce API
---
# Inventory endpoints

## GET /v1/inventory/{sku}

Read stock level for a SKU.

- Service: `inventory-api`; dependencies: `inventory-db`
- Required scope: `inventory:read`
- IP allowlist enforced: no
- Typical latency: p50 25 ms, p95 90 ms; gateway timeout 10000 ms
- Possible errors: 401, 403, 429, 500, 503, 504
