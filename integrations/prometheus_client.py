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
                self._client = PrometheusConnect(url=self.config.url, disable_ssl=True)
                # Testa conexão
                end_time = datetime.now()
                start_time = end_time - timedelta(minutes=1)
                self._client.get_metric_range_data(
                    "up", start_time=start_time, end_time=end_time
                )

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
                    wait_time = self.config.retry_delay * (
                        2**attempt
                    )  # exponential backoff
                    log(
                        f"Prometheus query failed (attempt {attempt+1}/{self.config.retry_attempts}): {e}. Retrying in {wait_time}s...",
                        level="warning",
                    )
                    time.sleep(wait_time)
                else:
                    log(
                        f"Prometheus query failed after {self.config.retry_attempts} attempts: {e}",
                        level="error",
                    )

        raise PrometheusError(
            f"Query failed after {self.config.retry_attempts} attempts: {last_error}"
        ) from last_error

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

    def query_instant(
        self, query: str, default: float = 0.0, use_cache: bool = False, log_result: bool = True
    ) -> float:
        """
        Executa uma query instantânea e retorna valor numérico.

        Args:
            query: Query PromQL
            default: Valor padrão se falhar
            use_cache: Se True, usa cache
            log_result: Se True, loga warning quando resultado é vazio (default: True)

        Returns:
            Valor numérico ou default
        """
        try:
            result = self._query_with_cache(query, use_cache)

            # Log do resultado bruto para debug
            log(
                f"Prometheus query result type: {type(result)}, length: {len(result) if result else 0}", level="debug")

            if result and len(result) > 0:
                # Log da estrutura do primeiro item
                log(f"First result item: {result[0]}", level="debug")

                # Tenta extrair valor de diferentes formatos
                first_item = result[0]

                # Formato 1: {"value": [timestamp, value]}
                if "value" in first_item and isinstance(first_item["value"], list):
                    if len(first_item["value"]) >= 2:
                        value = first_item["value"][1]
                        log(f"✅ Extracted value from format 1: {value}", level="debug")
                        return float(value)

                # Formato 2: {"value": value} (valor direto)
                if "value" in first_item and not isinstance(first_item["value"], list):
                    value = first_item["value"]
                    log(f"✅ Extracted value from format 2: {value}", level="debug")
                    return float(value)

                # Se chegou aqui, formato não reconhecido
                log(
                    f"⚠️ Unrecognized result format.\n"
                    f"QUERY: {query}\n"
                    f"RESULT: {result}\n"
                    f"FIRST_ITEM: {first_item}",
                    level="warning",
                )
            else:
                if log_result:
                    log(
                        f"Query returned empty result.\n"
                        f"QUERY: {query}\n"
                        f"RESULT: {result}",
                        level="warning",
                    )

            return default

        except PrometheusError:
            raise
        except Exception as e:
            log(f"Query failed: {query}... | Error: {e}", level="warning")
            import traceback
            log(f"Traceback: {traceback.format_exc()}", level="debug")
            return default

    def _get_max_from_range(
        self,
        query: str,
        start_time: float,
        end_time: float,
        step: str = "15s",
        default: float = 0.0
    ) -> float:
        """
        Executa query_range e retorna o MÁXIMO dos valores (não a média).

        Args:
            query: Query PromQL
            start_time: Unix timestamp do início
            end_time: Unix timestamp do fim
            step: Intervalo entre pontos
            default: Valor padrão se falhar

        Returns:
            Valor máximo encontrado ou default
        """
        try:
            client = self._get_client()
            start_dt = datetime.fromtimestamp(start_time)
            end_dt = datetime.fromtimestamp(end_time)

            def _execute():
                return client.custom_query_range(
                    query=query,
                    start_time=start_dt,
                    end_time=end_dt,
                    step=step
                )

            result = self._retry_query(_execute)

            if result and len(result) > 0:
                first_item = result[0]

                if "values" in first_item and isinstance(first_item["values"], list):
                    values = first_item["values"]

                    if len(values) > 0:
                        numeric_values = []
                        for item in values:
                            if isinstance(item, list) and len(item) >= 2:
                                try:
                                    numeric_values.append(float(item[1]))
                                except (ValueError, TypeError):
                                    continue

                        if numeric_values:
                            max_value = max(numeric_values)
                            log(f"✅ Found max value: {max_value} from {len(numeric_values)} points", level="debug")
                            return max_value

            return default

        except Exception as e:
            log(f"Get max from range failed: {e}", level="warning")
            return default

    def query_range(
        self,
        query: str,
        start_time: float,
        end_time: float,
        step: str = "15s",
        default: float = 0.0,
        log_result: bool = True
    ) -> float:
        """
        Executa uma query range e retorna a média dos valores.

        Args:
            query: Query PromQL (sem range vector, será aplicado automaticamente)
            start_time: Unix timestamp do início
            end_time: Unix timestamp do fim
            step: Intervalo entre pontos de dados (default: 15s)
            default: Valor padrão se falhar
            log_result: Se True, loga warning quando resultado é vazio

        Returns:
            Média dos valores ou default
        """
        try:
            client = self._get_client()

            # Converte timestamps para datetime
            start_dt = datetime.fromtimestamp(start_time)
            end_dt = datetime.fromtimestamp(end_time)

            log(f"Query range: {start_dt} to {end_dt}, step={step}", level="debug")

            def _execute():
                return client.custom_query_range(
                    query=query,
                    start_time=start_dt,
                    end_time=end_dt,
                    step=step
                )

            result = self._retry_query(_execute)

            log(f"Query range result type: {type(result)}, length: {len(result) if result else 0}", level="debug")
            if not result or len(result) <= 0:
                if log_result:
                    log(
                        f"Query range returned empty result.\n"
                        f"QUERY: {query}\n"
                        f"RESULT: {result}",
                        level="warning",
                    )
                return default

            first_item = result[0]
            log(f"First result item keys: {first_item.keys() if isinstance(first_item, dict) else 'not a dict'}", level="debug")

            if "values" not in first_item or not isinstance(first_item["values"], list):
                log(
                    f"⚠️ Unrecognized range result format.\n"
                    f"QUERY: {query}\n"
                    f"RESULT: {result}\n"
                    f"FIRST_ITEM: {first_item}",
                    level="warning",
                )

                return default

            values = first_item["values"]
            log(f"Found {len(values)} data points", level="debug")

            if len(values) > 0:
                # Extrai valores numéricos
                numeric_values = []
                for item in values:
                    if isinstance(item, list) and len(item) >= 2:
                        try:
                            numeric_values.append(float(item[1]))
                        except (ValueError, TypeError):
                            continue

                if numeric_values:
                    avg_value = sum(numeric_values) / len(numeric_values)
                    log(f"✅ Extracted {len(numeric_values)} values, average: {avg_value}", level="debug")
                    return avg_value

            # Se chegou aqui, não conseguiu extrair valores válidos
            return default

        except PrometheusError:
            raise
        except Exception as e:
            log(f"Query range failed: {query}... | Error: {e}", level="warning")
            import traceback
            log(f"Traceback: {traceback.format_exc()}", level="debug")
            return default

    def get_cpu_usage(self, app_label: str, segundos: int = 90, start_time: float = None, end_time: float = None) -> float:
        """
        Retorna uso médio de CPU em núcleos.

        Args:
            app_label: Label da aplicação
            segundos: Janela de tempo em segundos (usado se start_time/end_time não fornecidos)
            start_time: Unix timestamp do início do período (opcional)
            end_time: Unix timestamp do fim do período (opcional)
        """
        if start_time and end_time:
            # Usa query_range para obter média do período
            query = f'avg(rate(container_cpu_usage_seconds_total{{namespace="default", pod=~"{app_label}.*", container!="POD"}}[{segundos}s]))'
            return self.query_range(query, start_time, end_time, step="15s")
        else:
            # Fallback para query instantânea
            query = f'avg(rate(container_cpu_usage_seconds_total{{namespace="default", pod=~"{app_label}.*", container!="POD"}}[{segundos}s]))'
            return self.query_instant(query)

    def get_cpu_throttling(self, app_label: str, segundos: int = 30, start_time: float = None, end_time: float = None) -> float:
        """
        Retorna throttling de CPU.

        Args:
            app_label: Label da aplicação
            segundos: Janela de tempo em segundos (usado se start_time/end_time não fornecidos)
            start_time: Unix timestamp do início do período (opcional)
            end_time: Unix timestamp do fim do período (opcional)
        """
        if start_time and end_time:
            # Usa query_range para obter média do período
            query = f'sum(rate(container_cpu_cfs_throttled_seconds_total{{namespace="default", pod=~"{app_label}.*", container!="POD"}}[{segundos}s]))'
            return self.query_range(query, start_time, end_time, step="15s", log_result=False)
        else:
            # Fallback para query instantânea
            query = f'rate(container_cpu_cfs_throttled_seconds_total{{namespace="default", pod=~"{app_label}.*", container!="POD"}}[{segundos}s])'
            return self.query_instant(query, log_result=False)

    def get_memory_usage(self, app_label: str, segundos: int = 30, start_time: float = None, end_time: float = None) -> float:
        """
        Retorna uso médio de memória em bytes.

        Args:
            app_label: Label da aplicação
            segundos: Janela de tempo em segundos (usado se start_time/end_time não fornecidos)
            start_time: Unix timestamp do início do período (opcional)
            end_time: Unix timestamp do fim do período (opcional)
        """
        if start_time and end_time:
            # Usa query_range para obter média do período
            query = f'avg(container_memory_working_set_bytes{{namespace="default", pod=~"{app_label}.*", container!="POD"}})'
            return self.query_range(query, start_time, end_time, step="15s")
        else:
            # Fallback para query instantânea
            query = f'avg_over_time(container_memory_working_set_bytes{{namespace="default", pod=~"{app_label}.*", container!="POD"}}[{segundos}s])'
            return self.query_instant(query)

    def get_peak_memory_usage(self, app_label: str, segundos: int = 30, start_time: float = None, end_time: float = None) -> float:
        """
        Retorna uso maximo de memória em bytes.

        Args:
            app_label: Label da aplicação
            segundos: Janela de tempo em segundos (usado se start_time/end_time não fornecidos)
            start_time: Unix timestamp do início do período (opcional)
            end_time: Unix timestamp do fim do período (opcional)
        """
        if start_time and end_time:
            # Usa query_range para obter máximo do período
            query = f'avg(container_memory_working_set_bytes{{namespace="default", pod=~"{app_label}.*", container!="POD"}})'
            # Para pico, queremos o máximo dos valores retornados, não a média
            # Vamos usar uma abordagem diferente aqui
            return self._get_max_from_range(query, start_time, end_time)
        else:
            # Fallback para query instantânea
            query = f'max_over_time(container_memory_working_set_bytes{{namespace="default", pod=~"{app_label}.*", container!="POD"}}[{segundos}s])'
            return self.query_instant(query)

    def clear_cache(self):
        """Limpa o cache de queries."""
        self._cache.clear()
        log("Prometheus cache cleared", level="debug")

    def is_healthy(self) -> bool:
        """
        Verifica se o Prometheus está saudável e acessível.

        Returns:
            True se Prometheus está OK, False caso contrário
        """
        try:
            # Tenta fazer uma query simples
            query = "up"
            result = self.query_instant(query, default=None, use_cache=False)
            return result is not None
        except Exception as e:
            log(f"Prometheus health check failed: {e}", level="debug")
            return False
