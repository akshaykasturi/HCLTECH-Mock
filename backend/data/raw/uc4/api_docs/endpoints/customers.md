---
title: Customers endpoints
version: "2.3"
status: current
updated: 2026-09-01
product: NovaPay Commerce API
---
# Customers endpoints

## GET /v1/customers/{id}

Read a customer profile.

- Service: `customers-api`; dependencies: `customer-db`
- Required scope: `customers:read`
- IP allowlist enforced: no
- Typical latency: p50 45 ms, p95 160 ms; gateway timeout 10000 ms
- Possible errors: 401, 403, 429, 500, 503, 504
