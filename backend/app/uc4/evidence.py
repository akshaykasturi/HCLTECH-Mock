"""Collect evidence for one UC4 failure case.

collect_evidence(case) looks where an on-call engineer would look:
  request  - the failing request itself (by focal_correlation_id)
  traffic  - all requests on the route in the window vs the hour before
  metric   - endpoint and dependency metrics in the window vs the hour before
  change   - deploys and config changes shortly before / during the incident
  doc      - what the API documentation says about this error (doc_search.py)
  missing  - what we expected to find but could not

Rules:
  - Never read labels (expected_*, missing_info, generation): a live case must work the same.
  - Never copy secrets. request_headers (Authorization, X-Api-Key) are never read; only
    allow-listed fields are copied, and free text (error messages) is masked.
  - Each item has a stable id, one readable line with numbers, and the raw numbers in `data`.
"""
from collections import Counter
from http import HTTPStatus
from datetime import datetime, timedelta
from statistics import mean
from typing import Any, Optional

from app.uc4.models import Case, EvidenceItem
from app.uc4.settings import get_settings
from app.uc4 import doc_search, store
from app.uc4.redact import mask_text

# Only these response headers are copied (they carry no secrets).
_RATE_LIMIT_HEADERS = ("X-RateLimit-Limit", "X-RateLimit-Remaining", "Retry-After")
_METRIC_COLUMNS = ("error_rate", "p95_ms", "rps")
_UPSTREAM_STATUSES = (502, 503, 504)

def _masked(text: Optional[str]) -> Optional[str]:
    """Mask secrets in free text (error messages, change descriptions) with redact.mask_text."""
    return None if text is None else mask_text(text)[0]


def mask_ip(ip: Optional[str]) -> Optional[str]:
    """Keep the network, hide the host: '203.0.113.42' -> '203.0.113.x'. Anything else -> '<ip>'."""
    if not ip:
        return None
    parts = ip.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        return ".".join(parts[:3] + ["x"])
    return "<ip>"


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
        "error_message": _masked(error.get("message")),
        "upstream_service": upstream.get("service") if upstream else None,
        "upstream_status": upstream.get("status") if upstream else None,
        "upstream_error": _masked(upstream.get("error")) if upstream else None,
        "upstream_latency_ms": upstream.get("latency_ms") if upstream else None,
        "auth_method": auth.get("method"),
        "key_prefix": auth.get("key_prefix"),
        "token_age_s": auth.get("token_age_s"),
        "scopes": auth.get("scopes"),
        "client_ip_masked": mask_ip(row.get("client_ip")),
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
        allowlisted = "allowlisted" if data["client_ip_allowlisted"] else "NOT allowlisted"
        auth_bits.append(f"client IP {data['client_ip_masked']} {allowlisted}")
    parts.append(", ".join(auth_bits))
    if data["payload_shape"]:
        parts.append(f"payload {data['payload_shape']}")
    if rate_limit:
        parts.append("rate limit " + ", ".join(f"{h} {v}" for h, v in rate_limit.items()))
    parts.append(f"client {data['client_id']}")
    return EvidenceItem(id=item_id, kind="request", text="; ".join(parts), data=data)


# ---------- traffic ----------

def sample_stats(rows: list[dict[str, Any]], top_n: int) -> dict[str, Any]:
    """What a SAMPLE of log rows can tell us: mix and shares, never volume.

    Logs are a sample of traffic, so counts and per-minute rates from them say nothing
    about traffic volume. Volume and error rate come from metrics (rps, error_rate).
    """
    n = len(rows)
    failures = sum(1 for r in rows if (r.get("status") or 0) >= 400)
    statuses = Counter(r.get("status") for r in rows)
    codes = Counter((r.get("error") or {}).get("code") for r in rows if r.get("error"))
    clients = Counter(r.get("client_id") for r in rows)
    top_client, top_count = clients.most_common(1)[0] if clients else (None, 0)
    return {
        "logged_requests": n,  # size of the sample, not traffic volume
        "logged_failures": failures,
        "failed_share": round(failures / n, 4) if n else None,
        "status_counts": {str(k): v for k, v in sorted(statuses.items())},
        "top_error_codes": dict(codes.most_common(top_n)),
        "clients": len(clients),
        "top_client": top_client,
        "top_client_share": round(top_count / n, 4) if n else None,
    }


def _traffic_item(case: Case, window: list, baseline: list, baseline_min: int, top_n: int) -> EvidenceItem:
    w = sample_stats(window, top_n)
    b = sample_stats(baseline, top_n)
    # From the baseline sample we keep shares only (comparable across samples), never counts.
    b_shares = {"failed_share": b["failed_share"], "top_client_share": b["top_client_share"],
                "top_client": b["top_client"]}
    text = (
        f"Logged requests (sample, not volume) on {case.route} {_hms(case.window_start)}-{_hms(case.window_end)}: "
        f"{_pct(w['failed_share'])} of logged requests failed ({w['logged_failures']} of {w['logged_requests']}); "
        f"statuses {_counts_text(w['status_counts'])}; "
        f"top error codes {_counts_text(w['top_error_codes'])}; "
        f"{w['clients']} clients, top client {w['top_client']} in {_pct(w['top_client_share'])} of logged requests "
        f"(previous {baseline_min} min: {_pct(b['top_client_share'])}, failed share {_pct(b['failed_share'])}). "
        f"Traffic volume and error rate: see endpoint metrics"
    )
    return EvidenceItem(id="traffic:window", kind="traffic", text=text,
                        data={"sample": True, "window": w, "baseline": b_shares,
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
        f"Metrics for {label} {target} (all traffic, window mean vs previous {len(baseline)} min): "
        f"traffic volume {_num(r['window'])} rps vs {_num(r['baseline'])} rps ({_ratio_text(r['ratio'])}); "
        f"error rate {_pct(e['window'])} vs {_pct(e['baseline'])} ({_ratio_text(e['ratio'])}); "
        f"p95 {_num(p['window'])} ms vs {_num(p['baseline'])} ms ({_ratio_text(p['ratio'])}, peak {_num(p['window_max'])} ms)"
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
            f"by {change.get('author')}: \"{_masked(change.get('description'))}\"; {related_text}")
    data = {**{k: change.get(k) for k in ("ts", "service", "type", "version", "author")},
            "description": _masked(change.get("description")),
            "minutes_before_onset": minutes, "related": relation is not None, "relation": relation}
    return EvidenceItem(id=f"change:{change['ts']}:{service}", kind="change", text=text, data=data)


# ---------- documentation ----------

def doc_queries(row: dict[str, Any], route: str) -> tuple[str, str]:
    """(error query, full query) for doc search, from the focal request.

    error query: status + its standard HTTP name ("429 Too Many Requests", the way the troubleshooting
                 headings are written) + error code + upstream service: what the error MEANS.
    full query:  the same plus the route: finds the route's own endpoint doc.
    Route words alone would otherwise crowd out the error's docs (inventory, sku...).
    """
    status = row.get("status")
    phrase = HTTPStatus(status).phrase if status in HTTPStatus._value2member_map_ else ""
    code = (row.get("error") or {}).get("code") or ""
    upstream = (row.get("upstream") or {}).get("service") or ""
    error_query = " ".join(str(x) for x in (status, phrase, code, upstream) if x)
    return error_query, " ".join(x for x in (error_query, route) if x)


def _doc_item(hit: Any, role: str, query: str, sentences: int) -> EvidenceItem:
    section = doc_search.get_section(hit.section_id)
    quote = _masked(doc_search.first_sentences(section.text, sentences))
    version = f" v{hit.version}" if hit.version else ""
    text = f'Doc "{hit.title or hit.doc_id}"{version}, section "{hit.heading}": {quote}'
    data = {"section_id": hit.section_id, "doc_id": hit.doc_id, "title": hit.title, "heading": hit.heading,
            "version": hit.version, "status": hit.status, "score": hit.score, "rank": hit.rank,
            "mode": hit.mode, "role": role, "query": query}
    return EvidenceItem(id=hit.section_id, kind="doc", text=text, data=data)


def _doc_items(row: dict[str, Any], route: str) -> list[EvidenceItem]:
    """Up to evidence_k doc sections: the top hits for what the error means, plus the best troubleshooting
    section (the report's steps cite it); if that is already in, the best hit for the route instead.
    Never deprecated. Doc items are for the report only: signals and ranking never read them."""
    cfg = get_settings()["doc_search"]
    k, n = cfg["evidence_k"], cfg["quote_sentences"]
    error_query, full_query = doc_queries(row, route)
    chosen: list[tuple[Any, str, str]] = []

    def add(hit: Any, role: str, query: str) -> None:
        if hit is not None and all(hit.section_id != h.section_id for h, _, _ in chosen) and len(chosen) < k:
            chosen.append((hit, role, query))

    for hit in doc_search.search(error_query, k=max(k - 1, 1)):
        add(hit, "error", error_query)
    trouble = doc_search.search(error_query, k=1, doc_id="troubleshooting")
    if trouble and all(trouble[0].section_id != h.section_id for h, _, _ in chosen):
        add(trouble[0], "troubleshooting", error_query)
    else:
        for hit in doc_search.search(full_query, k=k):
            add(hit, "route", full_query)
    return [_doc_item(hit, role, query, n) for hit, role, query in chosen]


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
    """All evidence for one case, in a fixed order: request, traffic, metric, change, doc, missing."""
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
    sample = traffic.data["window"]
    if sample["logged_requests"] <= cfg["min_requests_in_window"]:
        missing.append(_missing("other_requests", f"only {sample['logged_requests']} logged request(s) on "
                                f"{case.route} in the window, so there is no pattern to compare"))
    elif sample["logged_failures"] <= cfg["min_failures_in_window"]:
        missing.append(_missing("other_failures", f"only {sample['logged_failures']} logged failing request(s) "
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

    # doc: what the documentation says about this error (for the report; never read by signals or ranking)
    if focal:
        items.extend(_doc_items(focal[0], case.route))

    return items + missing
