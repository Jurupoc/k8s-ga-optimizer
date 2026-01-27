# ga/evaluator.py
"""
Consultas ao Prometheus e cálculo de fitness.
Configurações via variáveis de ambiente:
- PROMETHEUS_URL: url do Prometheus (default: http://localhost:9090)
- PROM_QUERY_TIMEOUT: timeout de requests em segundos
- LOAD_TEST_DURATION: duração do load test em segundos (default: 30)
- LOAD_TEST_CONCURRENCY: número de threads concorrentes (default: 20)
- APP_URL: URL da aplicação para load test (default: http://app-ga.default.svc.cluster.local:8080)
- APP_LABEL: label da aplicação no Prometheus (default: app-ga)
"""

import os
import requests
from typing import Dict, Optional
from .utils import log
from .tests.load_test import run_load_test
from .k8s_manager import wait_for_rollout
from integrations.prometheus_client import PrometheusClient
from ga.config import PrometheusConfig

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")
PROM_QUERY_TIMEOUT = int(os.environ.get("PROM_QUERY_TIMEOUT", "10"))
LOAD_TEST_DURATION = int(os.environ.get("LOAD_TEST_DURATION", "30"))
LOAD_TEST_CONCURRENCY = int(os.environ.get("LOAD_TEST_CONCURRENCY", "20"))
APP_URL = os.environ.get("APP_URL", "http://app-ga.default.svc.cluster.local:8080")
APP_LABEL = os.environ.get("APP_LABEL", "app-ga")


def calculate_fitness(
    load_metrics: Dict,
    cpu_usage: float,
    memory_usage: float,
    config: Dict
) -> float:
    """
    Calcula o fitness score baseado em múltiplas métricas.

    Fórmula: throughput / (latency * resource_usage * penalty_factor)

    Onde:
    - throughput: requisições por segundo
    - latency: latência média em segundos
    - resource_usage: uso combinado de CPU e memória (normalizado)
    - penalty_factor: penaliza configurações que usam muitos recursos sem benefício
    """
    if load_metrics["avg_latency"] <= 0 or load_metrics["throughput"] <= 0:
        log("Invalid load metrics, returning low fitness", level="warning")
        return 0.0

    # Normaliza uso de recursos (CPU em cores, memória em MB)
    # Penaliza uso excessivo de recursos
    cpu_normalized = cpu_usage / max(config.get("cpu_limit", 1.0), 0.1)
    memory_mb = memory_usage / (1024 * 1024)  # bytes para MB
    memory_normalized = memory_mb / max(config.get("memory_limit", 256), 1.0)

    resource_usage = (cpu_normalized + memory_normalized) / 2.0

    # Fator de eficiência: throughput alto com baixa latência e baixo uso de recursos
    efficiency = load_metrics["throughput"] / (
        load_metrics["avg_latency"] * (resource_usage + 0.1)  # +0.1 para evitar divisão por zero
    )

    # Penaliza alta taxa de falhas
    failure_rate = load_metrics.get("fail", 0) / max(load_metrics.get("total", 1), 1)
    failure_penalty = 1.0 - (failure_rate * 0.5)  # até 50% de penalidade

    fitness = efficiency * failure_penalty

    log(f"Fitness calculation: efficiency={efficiency:.4f}, "
        f"failure_penalty={failure_penalty:.4f}, "
        f"final_fitness={fitness:.4f}")

    return fitness


def evaluate_individual(config: Dict, skip_load_test: bool = False) -> float:
    """
    Avalia um indivíduo (configuração) do algoritmo genético.

    Args:
        config: Dicionário com configuração (replicas, cpu_limit, memory_limit)
        skip_load_test: Se True, pula o load test (útil quando já foi aplicado)

    Returns:
        Score de fitness (float). Valores maiores são melhores.
    """
    try:
        # 1. Aguardar rollout completo (se necessário)
        deployment_name = os.environ.get("K8S_DEPLOYMENT_NAME", "app-ga")
        namespace = os.environ.get("K8S_NAMESPACE", "default")

        log(f"Waiting for rollout of {deployment_name}...")
        rollout_success = wait_for_rollout(deployment_name, namespace)
        if not rollout_success:
            log("Rollout failed or timeout, assigning low fitness", level="warning")
            return 0.0

        # 2. Rodar teste de carga
        if not skip_load_test:
            load_test_url = f"{APP_URL}/mixed"
            log(f"Running load test: {load_test_url}")
            load_metrics = run_load_test(
                load_test_url,
                duration=LOAD_TEST_DURATION,
                concurrency=LOAD_TEST_CONCURRENCY
            )
            log(f"Load test results: {load_metrics}")
        else:
            # Se pulou o load test, usa valores padrão (não ideal, mas permite continuar)
            load_metrics = {
                "success": 100,
                "fail": 0,
                "total": 100,
                "avg_latency": 0.1,
                "throughput": 10.0
            }
            log("Skipped load test, using default metrics", level="warning")

        # 3. Consultar Prometheus para métricas de recursos
        prom_client = PrometheusClient(PrometheusConfig.from_env())

        # Usa queries com namespace e container filter para compatibilidade
        cpu_query = f'avg(rate(container_cpu_usage_seconds_total{{namespace="default", pod=~"{APP_LABEL}.*", container!="POD"}}[1m]))'
        memory_query = f'avg(container_memory_working_set_bytes{{namespace="default", pod=~"{APP_LABEL}.*", container!="POD"}})'

        cpu_usage = prom_client.query_instant(cpu_query)
        memory_usage = prom_client.query_instant(memory_query)

        log(f"Prometheus metrics: CPU={cpu_usage:.4f}, "
            f"Memory={memory_usage:.2f} bytes")

        # 4. Calcular fitness
        score = calculate_fitness(
            load_metrics,
            cpu_usage,
            memory_usage,
            config
        )

        log(f"Individual evaluated: config={config}, score={score:.4f}")
        return score

    except Exception as e:
        log(f"Error evaluating individual {config}: {e}", level="error")
        return 0.0
