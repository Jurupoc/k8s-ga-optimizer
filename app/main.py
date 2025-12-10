# app/main.py
"""
API de teste para simulação de microserviço real.
Inclui endpoints CPU-bound, IO-bound e DB-bound.
"""
import time
import asyncio
import socket
import psutil
from fastapi import FastAPI, Query
from typing import Optional

from app.compute import sort, search, prime
from app.metrics import setup_metrics
from app.db import insert_items, query_items, search_items, aggregate_values

app = FastAPI(title="Compute Service", description="Test workload API for GA optimization")


# ==================== CPU-Bound Endpoints ====================

@app.get("/sort")
def sort_numbers(size: int = Query(10000, ge=100, le=1000000)):
    """
    Endpoint CPU-bound: ordenação de vetor.
    """
    data = sort.generate_random_list(size)
    sorted_data = sort.quicksort(data)
    return {
        "sorted_first": sorted_data[0],
        "sorted_last": sorted_data[-1],
        "size": size
    }


@app.get("/search")
def search_number(
    size: int = Query(1000000, ge=1000, le=10000000),
    target: int = Query(42, ge=0)
):
    """
    Endpoint CPU-bound: busca binária.
    """
    data = search.generate_random_list(size)
    found = search.binary_search(sorted(data), target)
    return {"found": found, "size": size, "target": target}


@app.get("/prime")
def generate_primes(size: int = Query(10000, ge=100, le=100000)):
    """
    Endpoint CPU-bound: geração de números primos.
    """
    primes = prime.generate_primes(size)
    return {"count": len(primes), "max": size}


@app.get("/cpu-stress")
def cpu_stress(iterations: int = Query(1000000, ge=10000, le=100000000)):
    """
    Endpoint CPU-bound: stress test puro.
    """
    result = 0
    for i in range(iterations):
        result += i * i
    return {"result": result, "iterations": iterations}


# ==================== IO-Bound Endpoints ====================

@app.get("/io-read")
async def io_read(delay_ms: int = Query(10, ge=1, le=1000)):
    """
    Endpoint IO-bound: simula leitura (delay).
    """
    await asyncio.sleep(delay_ms / 1000.0)
    return {"delay_ms": delay_ms, "operation": "read"}


@app.get("/io-write")
async def io_write(
    size: int = Query(1024, ge=1, le=10485760),  # até 10MB
    delay_ms: int = Query(5, ge=1, le=1000)
):
    """
    Endpoint IO-bound: simula escrita (delay proporcional ao tamanho).
    """
    # Simula escrita com delay proporcional
    total_delay = (size / 1024) * (delay_ms / 1000.0)
    await asyncio.sleep(min(total_delay, 1.0))  # max 1 segundo
    return {"size": size, "delay_ms": delay_ms, "operation": "write"}


@app.get("/io-mixed")
async def io_mixed(
    operations: int = Query(10, ge=1, le=100),
    delay_ms: int = Query(20, ge=1, le=500)
):
    """
    Endpoint IO-bound: operações mistas de IO.
    """
    for _ in range(operations):
        await asyncio.sleep(delay_ms / 1000.0)
    return {"operations": operations, "delay_ms": delay_ms}


# ==================== DB-Bound Endpoints ====================

@app.get("/db/insert")
def db_insert(count: int = Query(100, ge=1, le=10000)):
    """
    Endpoint DB-bound: inserção de dados.
    """
    inserted = insert_items(count)
    return {"inserted": inserted, "count": count}


@app.get("/db/query")
def db_query(limit: int = Query(100, ge=1, le=10000)):
    """
    Endpoint DB-bound: consulta de dados.
    """
    items = query_items(limit)
    return {"count": len(items), "items": items[:10]}  # retorna apenas primeiros 10


@app.get("/db/search")
def db_search(pattern: str = Query("item", min_length=1, max_length=50)):
    """
    Endpoint DB-bound: busca com LIKE.
    """
    items = search_items(pattern)
    return {"count": len(items), "pattern": pattern, "items": items[:10]}


@app.get("/db/aggregate")
def db_aggregate():
    """
    Endpoint DB-bound: agregações (SUM, AVG, etc).
    """
    result = aggregate_values()
    return result


@app.get("/db/complex")
def db_complex(
    insert_count: int = Query(50, ge=1, le=1000),
    query_limit: int = Query(100, ge=1, le=1000)
):
    """
    Endpoint DB-bound: operação complexa (insert + query + aggregate).
    """
    # Insere dados
    insert_items(insert_count)

    # Consulta
    items = query_items(query_limit)

    # Agrega
    agg = aggregate_values()

    return {
        "inserted": insert_count,
        "queried": len(items),
        "aggregation": agg
    }


# ==================== Mixed Workload Endpoints ====================

@app.get("/mixed")
async def mixed_workload(
    cpu_iterations: int = Query(100000, ge=1000, le=10000000),
    io_ops: int = Query(5, ge=1, le=50),
    db_count: int = Query(10, ge=1, le=1000)
):
    """
    Endpoint misto: CPU + IO + DB.
    """
    # CPU
    result = 0
    for i in range(cpu_iterations):
        result += i

    # IO
    for _ in range(io_ops):
        await asyncio.sleep(0.01)

    # DB
    insert_items(db_count)
    items = query_items(100)

    return {
        "cpu_result": result,
        "io_operations": io_ops,
        "db_items": len(items)
    }


# ==================== Status and Health ====================

@app.get("/status")
def get_status():
    """
    Status do nó e recursos.
    """
    return {
        "node": socket.gethostname(),
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory_percent": psutil.virtual_memory().percent,
        "memory_available_mb": psutil.virtual_memory().available / (1024 * 1024)
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
            "cpu_bound": ["/sort", "/search", "/prime", "/cpu-stress"],
            "io_bound": ["/io-read", "/io-write", "/io-mixed"],
            "db_bound": ["/db/insert", "/db/query", "/db/search", "/db/aggregate", "/db/complex"],
            "mixed": ["/mixed"],
            "status": ["/status", "/health"]
        }
    }


# Configura métricas
setup_metrics(app)
