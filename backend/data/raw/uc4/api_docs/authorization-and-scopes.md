---
title: Authorization, scopes and IP allowlists
version: "2.3"
status: current
updated: 2026-09-01
product: NovaPay Commerce API
---
# Authorization, scopes and IP allowlists

A valid credential can still be refused with `403`. There are two reasons: a missing scope, or a source IP that is not on the allowlist.

## Scopes

Each route needs one scope. A token without it returns `403 ERR_FORBIDDEN_SCOPE`.

| Route | Required scope |
|---|---|
| POST /v1/orders | orders:write |
| GET /v1/orders/{id} | orders:read |
| POST /v1/payments | payments:write |
| POST /v1/refunds | refunds:write |
| GET /v1/inventory/{sku} | inventory:read |
| GET /v1/customers/{id} | customers:read |
| GET /v1/search | catalog:read |

The gateway logs the token's scopes in `auth.scopes`.

## IP allowlists

Money-moving routes, `POST /v1/payments` and `POST /v1/refunds`, accept calls only from IP addresses on the merchant's allowlist. Other IPs get `403 ERR_IP_NOT_ALLOWED`. The gateway logs `client_ip_allowlisted: true/false`.

Changing an allowlist is a privileged action done by the merchant's account owner in the dashboard; support can only verify it.

## Generic 403 responses

Older gateway nodes return `403 ERR_FORBIDDEN` without saying which check failed. Compare `auth.scopes` with the table above and check `client_ip_allowlisted` in the log.
