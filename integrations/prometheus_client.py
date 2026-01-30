# integrations/prometheus_client.py
"""
Cliente robusto para integração com Prometheus.
Inclui retries, timeouts, cache e tolerância a falhas.
"""
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from prometheus_api_client import PrometheusConnect

from ga.exceptions import PrometheusError
from ga.config import PrometheusConfig
from shared.utils import log


class PrometheusClient:
    """
    Cliente Prometheus com retries, cache e tratamento robusto de erros.
    """

    def __init__(self, config: Optional[PrometheusConfig] = None):
        """
        Inicializa o cliente Prometheus.

        Args:
            config: Configuração do Prometheus (default: carrega de env)
        """
        self.config = config or PrometheusConfig.from_env()
        self._client: Optional[PrometheusConnect] = None
        self._cache: Dict[str, tuple[float, Any]] = {}  # query -> (timestamp, result)
        self._cache_ttl = 5.0  # segundos

    def _get_client(self) -> PrometheusConnect:
        """Obtém ou cria o cliente Prometheus."""
        if self._client is None:
            try:
                self._client = PrometheusConnect(
                    url=self.config.url,
                    disable_ssl=True
                )
                # Testa conexão
                end_time = datetime.now()
                start_time = end_time - timedelta(minutes=1)
                self._client.get_metric_range_data("up", start_time=start_time, end_time=end_time)

                log(f"Prometheus connection established: {self.config.url}")
            except Exception as e:
                log(f"Failed to connect to Prometheus: {e}", level="error")
                raise PrometheusError(f"Failed to connect to Prometheus: {e}") from e
        return self._client

    def _retry_query(self, func, *args, **kwargs):
        """
        Executa uma query com retry automático.

        Args:
            func: Função a ser executada
            *args, **kwargs: Argumentos da função

        Returns:
            Resultado da função

        Raises:
            PrometheusError: Se todas as tentativas falharem
        """
        last_error = None
        for attempt in range(self.config.retry_attempts):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.config.retry_attempts - 1:
                    wait_time = self.config.retry_delay * (2 ** attempt)  # exponential backoff
                    log(f"Prometheus query failed (attempt {attempt+1}/{self.config.retry_attempts}): {e}. Retrying in {wait_time}s...", level="warning")
                    time.sleep(wait_time)
                else:
                    log(f"Prometheus query failed after {self.config.retry_attempts} attempts: {e}", level="error")

        raise PrometheusError(f"Query failed after {self.config.retry_attempts} attempts: {last_error}") from last_error

    def _query_with_cache(self, query: str, use_cache: bool = True) -> Any:
        """
        Executa query com cache opcional.

        Args:
            query: Query PromQL
            use_cache: Se True, usa cache se disponível

        Returns:
            Resultado da query
        """
        if use_cache and query in self._cache:
            timestamp, result = self._cache[query]
            if time.time() - timestamp < self._cache_ttl:
                log(f"Using cached result for query: {query[:50]}...", level="debug")
                return result

        # Garante que o cliente está inicializado
        client = self._get_client()

        def _execute():
            return client.custom_query(query=query)

        result = self._retry_query(_execute)

        if use_cache:
            self._cache[query] = (time.time(), result)

        return result

    def query_instant(self, query: str, default: float = 0.0, use_cache: bool = False) -> float:
        """
        Executa uma query instantânea e retorna valor numérico.

        Args:
            query: Query PromQL
            default: Valor padrão se falhar
            use_cache: Se True, usa cache

        Returns:
            Valor numérico ou default
        """
        try:
            result = self._query_with_cache(query, use_cache)
            if result and len(result) > 0:
                if "value" in result[0]:
                    value = result[0]["value"][1]
                    return float(value)
                elif isinstance(result[0].get("value"), list):
                    return float(result[0]["value"][1])
            log(f"Query returned no results.\nQUERY: {query}\nRESULT: {result}", level="warning")
            return default
        except PrometheusError:
            raise
        except Exception as e:
            log(f"Query failed: {query}... | Error: {e}", level="warning")
            return default

    def get_cpu_usage(self, app_label: str, segundos: int = 30) -> float:
        """Retorna uso médio de CPU em núcleos."""
        query = f'avg(rate(container_cpu_usage_seconds_total{{namespace="default", pod=~"{app_label}.*", container!="POD"}}[{segundos}s]))'
        return self.query_instant(query)

    def get_memory_usage(self, app_label: str, segundos: int = 30) -> float:
        """Retorna uso médio de memória em bytes."""
        query = f'avg_over_time(container_memory_working_set_bytes{{namespace="default", pod=~"{app_label}.*", container!="POD"}}[{segundos}s])'
        return self.query_instant(query)

    def clear_cache(self):
        """Limpa o cache de queries."""
        self._cache.clear()
        log("Prometheus cache cleared", level="debug")
