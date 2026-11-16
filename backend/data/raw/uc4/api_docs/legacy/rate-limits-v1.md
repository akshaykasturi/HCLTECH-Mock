---
title: Rate limits (API v1, deprecated)
version: "1.9"
status: deprecated
updated: 2025-11-15
product: NovaPay Commerce API
superseded_by: rate-limits.md
---
# Rate limits (API v1, deprecated)

This page describes the old limits and is kept for accounts on API versions before 2.3.

## Limit

Each API key may send **60 requests per minute**. Exceeding it returns `429 ERR_RATE_LIMITED`. Wait 60 seconds before retrying.
