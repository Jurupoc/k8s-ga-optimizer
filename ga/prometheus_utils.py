# ga/prometheus_utils.py
"""
Utilitários para consultas ao Prometheus.
Configurações via variáveis de ambiente:
- PROMETHEUS_URL: URL do Prometheus (default: http://prometheus-server.monitoring.svc.cluster.local:9090)
"""

import os
from typing import Optional
from prometheus_api_client import PrometheusConnect
from .utils import log

PROMETHEUS_URL = os.environ.get(
    "PROMETHEUS_URL",
    "http://prometheus-server.monitoring.svc.cluster.local:9090"
)


def get_prom_connection() -> PrometheusConnect:
    """
    Retorna uma conexão Prometheus válida.
    A URL pode ser configurada via variável de ambiente PROMETHEUS_URL.
    """
    try:
        prom = PrometheusConnect(
            url=PROMETHEUS_URL,
            disable_ssl=True
        )
        # Testa a conexão fazendo uma query simples
        prom.get_metric_range_data("up", start_time="1m", end_time="now")
        log(f"Prometheus connection established: {PROMETHEUS_URL}")
        return prom
    except Exception as e:
        log(f"Failed to connect to Prometheus at {PROMETHEUS_URL}: {e}", level="error")
        raise


def query_instant(prom: PrometheusConnect, query: str, default: float = 0.0) -> float:
    """
    Executa uma query instantânea e retorna o valor numérico.

    Args:
        prom: Conexão Prometheus
        query: Query PromQL
        default: Valor padrão se a query falhar ou não retornar resultado

    Returns:
        Valor numérico da query ou default
    """
    try:
        result = prom.custom_query(query=query)
        if result and len(result) > 0:
            # Prometheus retorna no formato [{"value": [timestamp, value]}]
            if "value" in result[0]:
                value = result[0]["value"][1]
                return float(value)
            # Ou pode retornar no formato {"metric": {...}, "value": [timestamp, value]}
            elif "value" in result[0] and isinstance(result[0]["value"], list):
                return float(result[0]["value"][1])
        log(f"Query returned no results: {query}", level="warning")
        return default
    except Exception as e:
        log(f"Query failed: {query} | Error: {e}", level="warning")
        return default


def query_range(
    prom: PrometheusConnect,
    query: str,
    start_time: str = "5m",
    end_time: str = "now",
    step: str = "15s"
) -> Optional[list]:
    """
    Executa uma query de range e retorna os resultados.

    Args:
        prom: Conexão Prometheus
        query: Query PromQL
        start_time: Tempo inicial (relativo ou absoluto)
        end_time: Tempo final (relativo ou absoluto)
        step: Intervalo de amostragem

    Returns:
        Lista de resultados ou None em caso de erro
    """
    try:
        result = prom.get_metric_range_data(
            metric_name=query,
            start_time=start_time,
            end_time=end_time,
            step=step
        )
        return result
    except Exception as e:
        log(f"Range query failed: {query} | Error: {e}", level="warning")
        return None


def get_avg_cpu_usage(prom: PrometheusConnect, app_label: str, minutes: int = 1) -> float:
    """
    Retorna o uso médio de CPU (em núcleos) nos últimos `minutes` minutos.

    Args:
        prom: Conexão Prometheus
        app_label: Label da aplicação (ex: "app-ga")
        minutes: Período em minutos para calcular a média

    Returns:
        Uso médio de CPU em núcleos
    """
    # Usa container_cpu_usage_seconds_total que mede CPU em segundos
    query = f'avg(rate(container_cpu_usage_seconds_total{{pod=~"{app_label}.*"}}[{minutes}m]))'
    return query_instant(prom, query)


def get_avg_memory_usage(prom: PrometheusConnect, app_label: str) -> float:
    """
    Retorna o uso médio de memória (em bytes) do app.

    Args:
        prom: Conexão Prometheus
        app_label: Label da aplicação

    Returns:
        Uso médio de memória em bytes
    """
    query = f'avg(container_memory_usage_bytes{{pod=~"{app_label}.*"}})'
    return query_instant(prom, query)


def get_request_rate(prom: PrometheusConnect, app_label: str, minutes: int = 1) -> float:
    """
    Retorna a taxa média de requisições por segundo.

    Args:
        prom: Conexão Prometheus
        app_label: Label da aplicação
        minutes: Período em minutos

    Returns:
        Taxa de requisições por segundo
    """
    query = f'rate(app_requests_total{{job="{app_label}"}}[{minutes}m])'
    return query_instant(prom, query)


def get_request_latency(prom: PrometheusConnect, app_label: str, minutes: int = 1, quantile: float = 0.5) -> float:
    """
    Retorna a latência de requisições (percentil).

    Args:
        prom: Conexão Prometheus
        app_label: Label da aplicação
        minutes: Período em minutos
        quantile: Percentil (0.0 a 1.0, default 0.5 = mediana)

    Returns:
        Latência em segundos
    """
    query = f'histogram_quantile({quantile}, rate(app_request_latency_seconds_bucket{{job="{app_label}"}}[{minutes}m]))'
    return query_instant(prom, query)


def get_error_rate(prom: PrometheusConnect, app_label: str, minutes: int = 1) -> float:
    """
    Retorna a taxa de erros (requisições com status != 200).

    Args:
        prom: Conexão Prometheus
        app_label: Label da aplicação
        minutes: Período em minutos

    Returns:
        Taxa de erros por segundo
    """
    query = f'rate(app_requests_total{{job="{app_label}", status_code!="200"}}[{minutes}m])'
    return query_instant(prom, query)


def get_pod_count(prom: PrometheusConnect, app_label: str) -> float:
    """
    Retorna o número de pods em execução.

    Args:
        prom: Conexão Prometheus
        app_label: Label da aplicação

    Returns:
        Número de pods
    """
    query = f'count(container_memory_usage_bytes{{pod=~"{app_label}.*"}})'
    return query_instant(prom, query)
