---
title: Error reference
version: "2.3"
status: current
updated: 2026-09-01
product: NovaPay Commerce API
---
# Error reference

Errors return JSON: `{"error": {"code": "...", "message": "..."}}`.

## Error codes

| Status | Code | Meaning | Usual cause |
|---|---|---|---|
| 400 | ERR_VALIDATION_REQUIRED_FIELD | A required field is missing | Payload does not match the route's schema; since 2.3 `currency` is required on orders |
| 400 | ERR_VALIDATION | Generic validation failure | Check the payload against the endpoint reference |
| 401 | ERR_AUTH_TOKEN_EXPIRED | Bearer token expired | Token older than 3600 s |
| 401 | ERR_AUTH_INVALID_KEY | API key unknown or wrong environment | Test key used on production, revoked key |
| 401 | ERR_UNAUTHORIZED | Generic authentication failure | Check token age and key prefix |
| 403 | ERR_FORBIDDEN_SCOPE | Token lacks the route's scope | See Authorization and scopes |
| 403 | ERR_IP_NOT_ALLOWED | Source IP not allowlisted | Payments and refunds only |
| 403 | ERR_FORBIDDEN | Generic authorization failure | Older gateway nodes |
| 415 | ERR_UNSUPPORTED_MEDIA_TYPE | Body is not JSON | Wrong Content-Type |
| 429 | ERR_RATE_LIMITED | Rate limit exceeded | See Rate limits |
| 499 | (none) | Client closed the request | Client timeout shorter than server latency |
| 500 | ERR_INTERNAL | Unexpected server error | Often a recent deploy; check change history |
| 500 | ERR_DB_POOL_EXHAUSTED | No free database connections | Pool too small for traffic, slow queries |
| 502 | ERR_BAD_GATEWAY | Invalid response from upstream | TLS failure, upstream crash |
| 503 | ERR_DEPENDENCY_UNAVAILABLE | A dependency is down | Dependency outage |
| 504 | ERR_UPSTREAM_TIMEOUT | Gateway timed out after 10 s | Slow dependency |
| 504 | ERR_GATEWAY_TIMEOUT | Generic timeout (older nodes) | Same as above |

## Which errors are the client's to fix

4xx errors (except 429 caused by a NovaPay incident) are fixed by the client. 5xx errors are investigated by NovaPay; a client can only report them with the correlation ID.
