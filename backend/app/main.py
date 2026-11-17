"""FastAPI entry point for the UC4 backend.

Run from the backend folder:
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Swagger UI: http://127.0.0.1:8000/docs   OpenAPI: http://127.0.0.1:8000/openapi.json

Environment variables (all optional):
    UC4_AUDIT_DB             SQLite audit file (default backend/data/audit/uc4_audit.db; *.db is git-ignored)
    UC4_CORS_ORIGINS         comma-separated origins (default http://127.0.0.1:5173,http://localhost:5173)
    UC4_DIAGNOSE_TIMEOUT_S   seconds before a diagnosis is abandoned (default 60)

The app starts even when the diagnosis pipeline does not exist yet: /api/diagnose then answers
503 DIAGNOSIS_NOT_READY and everything else keeps working.
"""
from __future__ import annotations

import contextvars
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.uc4 import audit
from app.uc4.api import (
    ApiError, ApiSettings, _is_valid_request_id, error_response, load_api_settings, ok, readiness, router,
)

logger = logging.getLogger("app.main")
REQUEST_ID_HEADER = "X-Request-ID"
_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
_HTTP_CODES = {400: "BAD_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND",
               405: "METHOD_NOT_ALLOWED", 413: "PAYLOAD_TOO_LARGE", 415: "UNSUPPORTED_MEDIA_TYPE",
               429: "TOO_MANY_REQUESTS"}


def configure_logging() -> None:
    """Add the current request id to every log record; set a simple format if nothing is configured."""
    if not getattr(logging, "_uc4_request_id_factory", False):
        base_factory = logging.getLogRecordFactory()

        def factory(*args, **kwargs):
            record = base_factory(*args, **kwargs)
            record.request_id = _request_id.get()
            return record

        logging.setLogRecordFactory(factory)
        logging._uc4_request_id_factory = True  # type: ignore[attr-defined]
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO,
                            format="%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")


def _validation_message(exc: RequestValidationError) -> str:
    """Field locations and reasons only; the submitted values are never echoed back."""
    parts = []
    for err in exc.errors()[:5]:
        loc = ".".join(str(p) for p in err.get("loc", ()) if p != "body") or "request"
        parts.append(f"{loc}: {err.get('msg', 'invalid value')}")
    return "; ".join(parts) or "The request is not valid."


def create_app(settings: Optional[ApiSettings] = None) -> FastAPI:
    """Build the FastAPI app. Pass settings in tests; otherwise they come from the environment."""
    configure_logging()
    settings = settings or load_api_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            settings.audit_db_path.parent.mkdir(parents=True, exist_ok=True)
            audit.init_db(settings.audit_db_path)
            logger.info("audit database ready")
        except (OSError, audit.AuditError) as exc:  # keep serving; /health reports database down
            logger.error("audit database not available at startup (%s)", exc.__class__.__name__)
        yield

    app = FastAPI(
        title="UC4 API failure diagnosis",
        version="0.1.0",
        description="Cases, diagnoses (from the team's pipeline), the audit log and reviewer feedback. "
                    "Every response is {ok, data, error}; errors carry {code, message}. "
                    "Each response has an X-Request-ID header.",
        lifespan=lifespan,
    )
    app.state.settings = settings

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _is_valid_request_id(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id
        token = _request_id.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:  # last line of defence: no stack trace leaves the server
            logger.error("unhandled error on %s %s (%s)", request.method, request.url.path,
                         exc.__class__.__name__)
            request.state.error_code = "INTERNAL_ERROR"
            response = error_response(500, "INTERNAL_ERROR", "An unexpected error occurred.")
        try:
            response.headers[REQUEST_ID_HEADER] = request_id
            error_code = getattr(request.state, "error_code", None)
            logger.info("request_id=%s %s %s -> %d in %.1f ms%s", request_id, request.method, request.url.path,
                        response.status_code, (time.perf_counter() - started) * 1000,
                        f" error={error_code}" if error_code else "")
        finally:
            _request_id.reset(token)
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError):
        request.state.error_code = exc.code
        return error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError):
        request.state.error_code = "VALIDATION_ERROR"
        return error_response(422, "VALIDATION_ERROR", _validation_message(exc))

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(request: Request, exc: StarletteHTTPException):
        code = _HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
        request.state.error_code = code
        message = exc.detail if isinstance(exc.detail, str) and exc.status_code < 500 else "Request failed."
        return error_response(exc.status_code, code, message)

    @app.get("/health", tags=["health"], summary="Liveness and dependency status",
             description="200 whenever the API is running. data.database is up/down and data.pipeline is "
                         "ready/not_ready; a missing pipeline does not make the API unhealthy.")
    def health():
        return ok(readiness(app.state.settings))

    @app.get("/health/ready", tags=["health"], summary="Readiness",
             description="200 when the API can serve requests (audit database up); 503 DATABASE_UNAVAILABLE "
                         "otherwise. The diagnosis pipeline is reported but not required.")
    def ready(request: Request):
        status = readiness(app.state.settings)
        if status["database"] != "up":
            request.state.error_code = "DATABASE_UNAVAILABLE"
            return error_response(503, "DATABASE_UNAVAILABLE", "The audit database is not available.")
        return ok(status)

    app.include_router(router)
    return app


app = create_app()
