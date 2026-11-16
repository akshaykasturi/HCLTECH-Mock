"""Collect evidence for one UC4 failure case.

collect_evidence(case) looks where an on-call engineer would look:
  request  - the failing request itself (by focal_correlation_id)
  traffic  - all requests on the route in the window vs the hour before
  metric   - endpoint and dependency metrics in the window vs the hour before
  change   - deploys and config changes shortly before / during the incident
  missing  - what we expected to find but could not

Rules:
  - Never read labels (expected_*, missing_info, generation): a live case must work the same.
  - Never copy secrets. request_headers (Authorization, X-Api-Key) are never read; only
    allow-listed fields are copied, and free text (error messages) is masked.
  - Each item has a stable id, one readable line with numbers, and the raw numbers in `data`.
"""
import re
from collections import Counter
from datetime import datetime, timedelta
from statistics import mean
from typing import Any, Optional

from app.uc4.models import Case, EvidenceItem
from app.uc4.settings import get_settings
from app.uc4 import store

# Only these response headers are copied (they carry no secrets).
_RATE_LIMIT_HEADERS = ("X-RateLimit-Limit", "X-RateLimit-Remaining", "Retry-After")
_METRIC_COLUMNS = ("error_rate", "p95_ms", "rps")
_UPSTREAM_STATUSES = (502, 503, 504)

# Safety net for free text. The full masking step (plan step 2) runs before this;
# this keeps evidence clean even when called on raw data.
_SCRUB_PATTERNS = [
    (re.compile(r"eyJ[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+){0,2}"), "<token>"),
    (re.compile(r"\bnvp_(live|test)_[A-Za-z0-9]+"), r"nvp_\1_<key>"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "<email>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "<ip>"),
]


def scrub(text: Optional[str]) -> Optional[str]:
    """Mask tokens, full API keys, emails and IPs inside a piece of free text."""
    if text is None:
        return None
    for pattern, replacement in _SCRUB_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ---------- small formatting helpers ----------

def _hms(ts: datetime) -> str:
    return ts.strftime("%H:%M:%S")


def _pct(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _num(x: Optional[float]) -> str:
    if x is None:
        return "n/a"
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:,.2f}".rstrip("0").rstrip(".")


def _ratio(window: Optional[float], baseline: Optional[float]) -> Optional[float]:
    """window / baseline, or None when the baseline is missing or zero."""
    if window is None or not baseline:
        return None
    return round(window / baseline, 2)


def _ratio_text(r: Optional[float]) -> str:
    return "baseline 0" if r is None else f"x{r:g}"


def _counts_text(counter: dict[Any, int]) -> str:
    return ", ".join(f"{k}x{v}" for k, v in counter.items()) or "none"


# ---------- dependencies ----------

def _route_info(route: str) -> dict[str, Any]:
    return get_settings()["routes"].get(route, {"service": None, "dependencies": []})


def _dependencies(route: str, rows: list[dict[str, Any]]) -> list[str]:
    """Services named in the rows' upstream fields, then the route's direct dependencies."""
    names: list[str] = []
    for row in rows:
        service = (row.get("upstream") or {}).get("service")
        if service and service not in names:
            names.append(service)
    for service in _route_info(route).get("dependencies", []):
        if service not in names:
            names.append(service)
    return names


# ---------- request ----------

def _request_item(row: dict[str, Any], item_id: str) -> EvidenceItem:
    """The focal request, from allow-listed fields only (never request_headers)."""
    error = row.get("error") or {}
    upstream = row.get("upstream")
    auth = row.get("auth") or {}
    rate_limit = {h: v for h, v in (row.get("response_headers") or {}).items() if h in _RATE_LIMIT_HEADERS}

    data = {
        "correlation_id": row["correlation_id"],
        "ts": row["ts"],
        "method": row.get("method"),
        "route": row.get("route"),
        "status": row.get("status"),
        "latency_ms": row.get("latency_ms"),
        "error_code": error.get("code"),
        "error_message": scrub(error.get("message")),
        "upstream_service": upstream.get("service") if upstream else None,
        "upstream_status": upstream.get("status") if upstream else None,
        "upstream_error": scrub(upstream.get("error")) if upstream else None,
        "upstream_latency_ms": upstream.get("latency_ms") if upstream else None,
        "auth_method": auth.get("method"),
        "key_prefix": auth.get("key_prefix"),
        "token_age_s": auth.get("token_age_s"),
        "scopes": auth.get("scopes"),
        "client_ip_allowlisted": row.get("client_ip_allowlisted"),
        "payload_shape": row.get("payload_shape"),
        "rate_limit_headers": rate_limit,
        "client_id": row.get("client_id"),
    }

    parts = [f"Request {data['correlation_id']} at {_hms(store.parse_ts(row['ts']))}: "
             f"{data['route']} -> {data['status']} in {_num(data['latency_ms'])} ms"]
    if data["error_code"]:
        parts.append(f"error {data['error_code']} \"{data['error_message']}\"")
    if upstream:
        upstream_status = data["upstream_status"] if data["upstream_status"] is not None else "none"
        parts.append(f"upstream {data['upstream_service'] or 'unknown'} status {upstream_status} "
                     f"error {data['upstream_error'] or 'none'} after {_num(data['upstream_latency_ms'])} ms")
    auth_bits = [f"auth {data['auth_method'] or 'unknown'}"]
    if data["key_prefix"]:
        auth_bits.append(f"key prefix {data['key_prefix']}")
    if data["token_age_s"] is not None:
        auth_bits.append(f"token age {_num(data['token_age_s'])} s")
    if data["scopes"] is not None:
        auth_bits.append(f"scopes {', '.join(data['scopes']) or 'none'}")
    if data["client_ip_allowlisted"] is not None:
        auth_bits.append(f"IP allowlisted {data['client_ip_allowlisted']}")
    parts.append(", ".join(auth_bits))
    if data["payload_shape"]:
        parts.append(f"payload {data['payload_shape']}")
    if rate_limit:
        parts.append("rate limit " + ", ".join(f"{h} {v}" for h, v in rate_limit.items()))
    parts.append(f"client {data['client_id']}")
    return EvidenceItem(id=item_id, kind="request", text="; ".join(parts), data=data)


# ---------- traffic ----------

def traffic_stats(rows: list[dict[str, Any]], minutes: float, top_n: int) -> dict[str, Any]:
    """Count, error rate, status counts, top error codes and client spread for some log rows."""
    n = len(rows)
    failures = sum(1 for r in rows if (r.get("status") or 0) >= 400)
    statuses = Counter(r.get("status") for r in rows)
    codes = Counter((r.get("error") or {}).get("code") for r in rows if r.get("error"))
    clients = Counter(r.get("client_id") for r in rows)
    top_client, top_count = clients.most_common(1)[0] if clients else (None, 0)
    return {
        "requests": n,
        "requests_per_min": round(n / minutes, 2) if minutes else None,
        "failures": failures,
        "error_rate": round(failures / n, 4) if n else None,
        "status_counts": {str(k): v for k, v in sorted(statuses.items())},
        "top_error_codes": dict(codes.most_common(top_n)),
        "clients": len(clients),
        "top_client": top_client,
        "top_client_share": round(top_count / n, 4) if n else None,
    }


def _traffic_item(case: Case, window: list, baseline: list, baseline_min: int, top_n: int) -> EvidenceItem:
    window_min = (case.window_end - case.window_start).total_seconds() / 60
    w = traffic_stats(window, window_min, top_n)
    b = traffic_stats(baseline, baseline_min, top_n)
    text = (
        f"Traffic on {case.route} {_hms(case.window_start)}-{_hms(case.window_end)} ({window_min:g} min): "
        f"{w['requests']} requests ({_num(w['requests_per_min'])}/min), error rate {_pct(w['error_rate'])}; "
        f"baseline {baseline_min} min before: {b['requests']} requests ({_num(b['requests_per_min'])}/min), "
        f"error rate {_pct(b['error_rate'])}; "
        f"window statuses {_counts_text(w['status_counts'])}; "
        f"top error codes {_counts_text(w['top_error_codes'])}; "
        f"{w['clients']} clients, top client {w['top_client']} sends {_pct(w['top_client_share'])} of requests "
        f"(baseline top client share {_pct(b['top_client_share'])})"
    )
    return EvidenceItem(id="traffic:window", kind="traffic", text=text,
                        data={"window": w, "baseline": b, "window_minutes": window_min,
                              "baseline_minutes": baseline_min})


# ---------- metrics ----------

def _metric_item(case: Case, kind: str, target: str, baseline_start: datetime, label: str) -> Optional[EvidenceItem]:
    """Mean error_rate, p95_ms and rps in the window vs the baseline. None if no window rows."""
    window = store.metrics_for(kind, target, case.window_start, case.window_end)
    if not window:
        return None
    baseline = store.metrics_for(kind, target, baseline_start, case.window_start, end_inclusive=False)

    def avg(rows, col):
        values = [r[col] for r in rows if r[col] is not None]
        return round(mean(values), 4) if values else None

    data: dict[str, Any] = {"kind": kind, "target": target,
                            "window_points": len(window), "baseline_points": len(baseline)}
    for col in _METRIC_COLUMNS:
        w, b = avg(window, col), avg(baseline, col)
        data[col] = {"window": w, "baseline": b, "ratio": _ratio(w, b)}
    p95_values = [r["p95_ms"] for r in window if r["p95_ms"] is not None]
    data["p95_ms"]["window_max"] = max(p95_values) if p95_values else None

    e, p, r = data["error_rate"], data["p95_ms"], data["rps"]
    text = (
        f"Metrics for {label} {target} (window mean vs {len(baseline)}-min baseline): "
        f"p95 {_num(p['window'])} ms vs {_num(p['baseline'])} ms ({_ratio_text(p['ratio'])}, peak {_num(p['window_max'])} ms); "
        f"error rate {_pct(e['window'])} vs {_pct(e['baseline'])} ({_ratio_text(e['ratio'])}); "
        f"rps {_num(r['window'])} vs {_num(r['baseline'])} ({_ratio_text(r['ratio'])})"
    )
    return EvidenceItem(id=f"metric:{kind}:{target}", kind="metric", text=text, data=data)


# ---------- changes ----------

def _change_item(case: Case, change: dict[str, Any], dependencies: list[str]) -> EvidenceItem:
    service = change.get("service")
    route_service = _route_info(case.route).get("service")
    if service == route_service:
        relation = "route's service"
    elif service in dependencies:
        relation = "dependency"
    else:
        relation = None
    ts = store.parse_ts(change["ts"])
    minutes = round((case.onset_ts - ts).total_seconds() / 60, 1)
    when = f"{minutes:g} min before onset" if minutes >= 0 else f"{-minutes:g} min after onset"
    version = f" {change['version']}" if change.get("version") else ""
    related_text = f"related ({relation})" if relation else f"unrelated (route's service is {route_service})"
    text = (f"{change.get('type', 'change').capitalize()} on {service}{version} at {_hms(ts)} ({when}) "
            f"by {change.get('author')}: \"{scrub(change.get('description'))}\"; {related_text}")
    data = {**{k: change.get(k) for k in ("ts", "service", "type", "version", "author")},
            "description": scrub(change.get("description")),
            "minutes_before_onset": minutes, "related": relation is not None, "relation": relation}
    return EvidenceItem(id=f"change:{change['ts']}:{service}", kind="change", text=text, data=data)


# ---------- missing ----------

def _missing(what: str, text: str, **data: Any) -> EvidenceItem:
    return EvidenceItem(id=f"missing:{what}", kind="missing", text=f"Missing: {text}", data={"what": what, **data})


def _missing_from_request(row: dict[str, Any]) -> list[EvidenceItem]:
    """Things a failing request of this status should carry but does not."""
    items = []
    status = row.get("status")
    auth = row.get("auth") or {}
    headers = row.get("response_headers") or {}
    upstream = row.get("upstream") or {}
    if status == 401 and not any(auth.get(k) is not None for k in ("method", "key_prefix", "token_age_s")):
        items.append(_missing("auth_details", f"request {row['correlation_id']} got 401 but the log has no "
                              "auth method, key prefix or token age", correlation_id=row["correlation_id"]))
    if status == 429 and not any(h in headers for h in _RATE_LIMIT_HEADERS):
        items.append(_missing("rate_limit_headers", f"request {row['correlation_id']} got 429 but has no "
                              "X-RateLimit-* or Retry-After response headers", correlation_id=row["correlation_id"]))
    if status in _UPSTREAM_STATUSES and not upstream.get("service"):
        items.append(_missing("upstream_detail", f"request {row['correlation_id']} got {status} but the log does "
                              "not name the upstream service", correlation_id=row["correlation_id"]))
    return items


# ---------- main entry point ----------

def collect_evidence(case: Case) -> list[EvidenceItem]:
    """All evidence for one case, in a fixed order: request, traffic, metric, change, missing."""
    cfg = get_settings()["evidence"]
    baseline_min = cfg["baseline_minutes"]
    baseline_start = case.window_start - timedelta(minutes=baseline_min)
    items: list[EvidenceItem] = []
    missing: list[EvidenceItem] = []

    # request
    focal = store.logs_by_correlation_id(case.focal_correlation_id)
    if not focal:
        missing.append(_missing("focal_request", f"no request log with correlation_id {case.focal_correlation_id}",
                                correlation_id=case.focal_correlation_id))
    for i, row in enumerate(focal):
        item_id = f"request:{row['correlation_id']}" + (f":{i + 1}" if len(focal) > 1 else "")
        items.append(_request_item(row, item_id))
        missing.extend(_missing_from_request(row))

    # traffic
    window = store.logs_for_route(case.route, case.window_start, case.window_end)
    baseline = store.logs_for_route(case.route, baseline_start, case.window_start, end_inclusive=False)
    traffic = _traffic_item(case, window, baseline, baseline_min, cfg["top_error_codes"])
    items.append(traffic)
    if traffic.data["window"]["requests"] <= cfg["min_requests_in_window"]:
        missing.append(_missing("other_requests", f"only {traffic.data['window']['requests']} request(s) on "
                                f"{case.route} in the window, so there is no traffic pattern to compare"))
    elif traffic.data["window"]["failures"] <= cfg["min_failures_in_window"]:
        missing.append(_missing("other_failures", f"only {traffic.data['window']['failures']} failing request(s) "
                                f"on {case.route} in the window: an isolated failure, no pattern"))

    # metric: endpoint
    endpoint = _metric_item(case, "endpoint", case.route, baseline_start, "endpoint")
    if endpoint:
        items.append(endpoint)
    else:
        missing.append(_missing("endpoint_metrics", f"no endpoint metrics for {case.route} in the window",
                                target=case.route))

    # metric: dependencies
    dependencies = _dependencies(case.route, window + focal)
    for name in dependencies:
        dep = _metric_item(case, "service", name, baseline_start, "dependency")
        if dep:
            items.append(dep)
        else:
            missing.append(_missing(f"dependency_metrics:{name}", f"no metrics for dependency {name} in the window",
                                    target=name))

    # change
    since = case.onset_ts - timedelta(minutes=cfg["change_lookback_minutes"])
    for change in store.changes_between(since, case.window_end):
        items.append(_change_item(case, change, dependencies))

    return items + missing
