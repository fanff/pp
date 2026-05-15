import re
import time

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

REQUEST_COUNT = Counter(
    "pp_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_DURATION = Histogram(
    "pp_http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"],
)
IN_FLIGHT = Gauge(
    "pp_http_in_flight_requests",
    "In-flight requests",
)

# Patterns to normalize dynamic path segments
_PATH_NORMALIZE_PATTERNS = [
    (re.compile(r"/\d+"), "/{id}"),
    (re.compile(
        r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    ), "/{uuid}"),
]


def normalize_path(path: str) -> str:
    for pattern, replacement in _PATH_NORMALIZE_PATTERNS:
        path = pattern.sub(replacement, path)
    return path


class MetricsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "/")
        if path == "/metrics":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "UNKNOWN")
        endpoint = normalize_path(path)

        IN_FLIGHT.inc()
        start_time = time.monotonic()

        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.monotonic() - start_time
            IN_FLIGHT.dec()
            REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(
                duration
            )
            REQUEST_COUNT.labels(
                method=method, endpoint=endpoint, status=str(status_code)
            ).inc()


metrics_router = APIRouter(tags=["metrics"])


@metrics_router.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
