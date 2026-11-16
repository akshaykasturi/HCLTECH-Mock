---
title: Changelog
version: "2.3"
status: current
updated: 2026-09-01
product: NovaPay Commerce API
---
# Changelog

## 2.3 (2026-09-01)

- **Breaking:** `currency` is now required on `POST /v1/orders`. Requests without it return `400 ERR_VALIDATION_REQUIRED_FIELD`. Accounts pinned to 2026-06-01 keep the old behaviour until 2026-12-01.
- Gateway now logs `auth.token_age_s` and `client_ip_allowlisted` for faster diagnosis.
- Rate limit raised from 60 to 100 requests per minute per key.

## 2.2 (2026-06-01)

- Added `X-Client-Timeout-Ms` request header (optional, diagnostic only).
- `ERR_GATEWAY_TIMEOUT` renamed to `ERR_UPSTREAM_TIMEOUT`; older gateway nodes still send the old code.

## 2.1 (2026-03-01)

- Added IP allowlists for payments and refunds.
