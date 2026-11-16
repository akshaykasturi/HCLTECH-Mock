---
title: Search endpoints
version: "2.3"
status: current
updated: 2026-09-01
product: NovaPay Commerce API
---
# Search endpoints

## GET /v1/search

Full-text product search over the catalogue.

- Service: `search-api`; dependencies: `search-cluster`
- Required scope: `catalog:read`
- IP allowlist enforced: no
- Typical latency: p50 70 ms, p95 260 ms; gateway timeout 10000 ms
- Possible errors: 401, 403, 429, 500, 503, 504
