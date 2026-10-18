
import json
import logging
import os
import time
import uuid
from collections import deque
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Query
from fastapi.responses import Response
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

app = FastAPI(title="Production Observability")

START_TIME = time.monotonic()

# Prometheus automatically exposes this counter as http_requests_total.
REQUEST_COUNTER = Counter(
    "http_requests",
    "Total number of HTTP requests",
    ["method", "path"],
)

# Keep recent log entries available for the tail endpoint.
recent_logs = deque(maxlen=1000)

logger = logging.getLogger("observability")
logger.setLevel(logging.INFO)
logger.handlers.clear()
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(handler)
logger.propagate = False


@app.middleware("http")
async def observe_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())
    path = request.url.path
    method = request.method
    start = time.monotonic()
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        REQUEST_COUNTER.labels(method=method, path=path).inc()

        entry = {
            "level": "INFO",
            "ts": datetime.now(timezone.utc).isoformat(),
            "path": path,
            "request_id": request_id,
            "method": method,
            "status_code": status_code,
            "duration_ms": round(
                (time.monotonic() - start) * 1000, 3
            ),
        }

        recent_logs.append(entry)
        logger.info(json.dumps(entry))


@app.get("/work")
async def work(n: int = Query(default=1, ge=0, le=100000)):
    # Simulate K units of work.
    result = 0
    for i in range(n):
        result += i

    return {
        "email": os.getenv("SUBMISSION_EMAIL", "23f3003865@ds.study.iitm.ac.in"),
        "done": n,
    }


@app.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "uptime_s": float(time.monotonic() - START_TIME),
    }


@app.get("/logs/tail")
async def logs_tail(limit: int = Query(default=100, ge=1, le=1000)):
    return list(recent_logs)[-limit:]
