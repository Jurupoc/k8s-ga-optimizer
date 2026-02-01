# app/main.py
"""
API de teste para simulação de microserviço real.
"""

import time
import math
from fastapi import FastAPI

from app.metrics import setup_metrics

app = FastAPI(
    title="Compute Service", description="Test workload API for GA optimization"
)


@app.get("/mixed")
async def mixed_workload():
    """
    Calcula fatorial e aloca memória.
    """
    # CPU: Calcula fatorial
    n = 100
    factorial_result = math.factorial(n)

    # Memória: Cria uma lista grande
    memory_block = [i * 0.5 for i in range(1000000)]  # ~8MB

    return {
        "factorial": n,
        "result": str(factorial_result),
        "memory_allocated": len(memory_block)
    }


@app.get("/health")
def health():
    """
    Health check endpoint.
    """
    return {"status": "healthy", "timestamp": time.time()}


@app.get("/")
def root():
    """
    Endpoint raiz com informações da API.
    """
    return {
        "name": "Compute Service",
        "version": "2.0",
        "endpoints": {
            "mixed": ["/mixed"],
            "status": ["/health"],
        },
    }


# Configura métricas
setup_metrics(app)
