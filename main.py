from fastapi import FastAPI, Query
import time, math, random
from prometheus_client import start_http_server, Summary, Counter
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

app = FastAPI()

# Métricas Prometheus
REQUEST_TIME = Summary('app_request_duration_seconds', 'Tempo de processamento da requisição')
REQUEST_COUNT = Counter('app_requests_total', 'Número total de requisições')

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post("/compute")
@REQUEST_TIME.time()
def compute(complexity: int = Query(10000)):
    REQUEST_COUNT.inc()
    # Simulação de carga CPU-bound
    result = sum(math.sqrt(i) for i in range(complexity))
    # Simulação de espera aleatória (rede, IO)
    time.sleep(random.uniform(0.1, 0.5))
    return {"result": result, "complexity": complexity}
