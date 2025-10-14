from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response
import time

REQUEST_COUNT = Counter("app_requests_total", "Total requests")
REQUEST_LATENCY = Histogram("app_request_latency_seconds", "Request latency")

def setup_metrics(app):
    @app.middleware("http")
    async def metrics_middleware(request, call_next):
        start = time.time()
        response = await call_next(request)
        latency = time.time() - start
        REQUEST_COUNT.inc()
        REQUEST_LATENCY.observe(latency)
        return response

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
