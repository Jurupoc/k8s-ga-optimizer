# ga/tests/load_test.py
"""
Script de teste de carga para avaliar performance da aplicação.
"""
import requests
import concurrent.futures
import time
from typing import Dict
from threading import Lock

# Lock para thread-safety nas métricas compartilhadas
_metrics_lock = Lock()


def run_load_test(url: str, duration: int = 30, concurrency: int = 20, timeout: int = 5) -> Dict:
    """
    Executa um teste de carga na URL especificada.

    Args:
        url: URL para testar
        duration: Duração do teste em segundos
        concurrency: Número de threads concorrentes
        timeout: Timeout para cada requisição em segundos

    Returns:
        Dicionário com métricas do teste:
        - success: Número de requisições bem-sucedidas
        - fail: Número de requisições que falharam
        - total: Total de requisições
        - avg_latency: Latência média em segundos
        - min_latency: Latência mínima em segundos
        - max_latency: Latência máxima em segundos
        - p95_latency: Percentil 95 da latência
        - throughput: Requisições por segundo
        - success_rate: Taxa de sucesso (0.0 a 1.0)
    """
    start_time = time.time()
    end_time = start_time + duration

    # Métricas thread-safe
    success = 0
    fail = 0
    latencies = []
    lock = Lock()

    def worker():
        """Worker thread que executa requisições."""
        nonlocal success, fail
        worker_latencies = []

        while time.time() < end_time:
            t0 = time.time()
            try:
                r = requests.get(url, timeout=timeout)
                latency = time.time() - t0

                with lock:
                    if r.status_code == 200:
                        success += 1
                        worker_latencies.append(latency)
                    else:
                        fail += 1
            except Exception:
                with lock:
                    fail += 1

        # Adiciona latências ao pool global
        with lock:
            latencies.extend(worker_latencies)

    # Executa workers
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(worker) for _ in range(concurrency)]
        # Aguarda conclusão de todos
        concurrent.futures.wait(futures)

    # Calcula métricas
    total_requests = success + fail
    actual_duration = time.time() - start_time

    if latencies:
        latencies.sort()
        avg_latency = sum(latencies) / len(latencies)
        min_latency = latencies[0]
        max_latency = latencies[-1]
        p95_index = int(len(latencies) * 0.95)
        p95_latency = latencies[p95_index] if p95_index < len(latencies) else max_latency
    else:
        avg_latency = float("inf")
        min_latency = float("inf")
        max_latency = float("inf")
        p95_latency = float("inf")

    throughput = total_requests / actual_duration if actual_duration > 0 else 0.0
    success_rate = success / total_requests if total_requests > 0 else 0.0

    return {
        "success": success,
        "fail": fail,
        "total": total_requests,
        "avg_latency": avg_latency,
        "min_latency": min_latency,
        "max_latency": max_latency,
        "p95_latency": p95_latency,
        "throughput": throughput,
        "success_rate": success_rate,
        "duration": actual_duration
    }
