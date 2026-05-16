"""
Adapter para Prometheus — interface abstrata e implementação real.
"""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from typing_extensions import override

from nsga.domain import Genome, RawMetrics

if TYPE_CHECKING:
    from integrations.prometheus_client import PrometheusClient


class PrometheusAdapter(ABC):
    """Interface para coletar métricas do Prometheus."""

    @abstractmethod
    def collect_metrics(
        self,
        genome: Genome,
        deployment_name: str,
        start_time: float,
        end_time: float,
    ) -> RawMetrics:
        """
        Coleta métricas do Prometheus para uma janela de tempo já finalizada.

        Args:
            genome: Genome avaliado (usado para calcular mem_peak_ratio)
            deployment_name: Nome/label do deployment monitorado
            start_time: Unix timestamp do início da janela
            end_time: Unix timestamp do fim da janela

        Returns:
            RawMetrics com throughput_rps, cpu_throttle_rate, mem_peak_ratio
        """
        ...

    @abstractmethod
    def cleanup(self) -> None:
        """Limpeza de recursos, se necessário."""
        ...


class RealPrometheusAdapter(PrometheusAdapter):
    """
    Implementação real que delega para o PrometheusClient existente
    em integrations/prometheus_client.py.

    Adiciona apenas métodos novos para não afetar o GA de objetivo único.
    """

    def __init__(self, prometheus_url: str, app_label: str = "app-ga"):
        """
        Args:
            prometheus_url: URL do servidor Prometheus
            app_label: Label do pod/deployment usado nas queries PromQL
        """
        self.prometheus_url: str = prometheus_url
        self.app_label: str = app_label
        self._client: "PrometheusClient | None" = None

    @property
    def client(self) -> "PrometheusClient":
        if self._client is None:
            from integrations.prometheus_client import PrometheusClient
            from ga.config import PrometheusConfig

            config = PrometheusConfig(url=self.prometheus_url)
            self._client = PrometheusClient(config=config)
        return self._client

    @override
    def collect_metrics(
        self,
        genome: Genome,
        deployment_name: str,
        start_time: float,
        end_time: float,
    ) -> RawMetrics:
        """
        Coleta cpu_throttle_rate e mem_peak_ratio do Prometheus.
        O throughput_rps vem do load test e é injetado externamente
        pelo EvaluatePipeline, portanto aqui retornamos 0.0.
        """
        from shared.utils import log

        label = self.app_label
        window = int(end_time - start_time)
        window = max(window, 30)

        cpu_throttle = self._get_cpu_throttle_rate(label, window, start_time, end_time)
        mem_peak_ratio = self._get_mem_peak_ratio(genome, label, window, start_time, end_time)

        log(
            f"[NSGA-Prom] throttle={cpu_throttle:.4f}, "
            + f"mem_peak_ratio={mem_peak_ratio:.4f}",
            level="info",
        )

        return RawMetrics(
            throughput_rps=0.0,
            cpu_throttle_rate=cpu_throttle,
            mem_peak_ratio=mem_peak_ratio,
        )

    # ------------------------------------------------------------------
    # Métodos novos — não modificam PrometheusClient existente
    # ------------------------------------------------------------------

    def _get_cpu_throttle_rate(
        self, label: str, window: int, start_time: float, end_time: float
    ) -> float:
        """
        Calcula a fração do tempo de CPU que foi throttled.

        Usa rate(throttled) / rate(total_periods) para obter um valor em [0, 1].
        Retorna 0.0 se não houver dados (sem throttle).
        """
        selector = f'{{namespace="default", pod=~"{label}.*", container!="POD"}}'
        query = (
            f"sum(rate(container_cpu_cfs_throttled_periods_total{selector}[{window}s])) "
            f"/ sum(rate(container_cpu_cfs_periods_total{selector}[{window}s]))"
        )
        value = self.client.query_range(
            query, start_time, end_time, step="15s", default=0.0, log_result=False
        )
        return max(0.0, min(1.0, value))

    def _get_mem_peak_ratio(
        self, genome: Genome, label: str, window: int, start_time: float, end_time: float
    ) -> float:
        """
        Calcula peak_memory / memory_limit usando o limite do genome.

        Usa query_range_max para pegar o pico real no período.
        """
        selector = f'{{namespace="default", pod=~"{label}.*", container!="POD"}}'
        query = f"max(container_memory_working_set_bytes{selector})"
        peak_bytes = self.client.query_range_max(
            query, start_time, end_time, step="15s", default=0.0
        )

        limit_bytes = genome.mem_mib * 1024 * 1024
        if limit_bytes <= 0:
            return 1.0

        ratio = peak_bytes / limit_bytes
        return max(0.0, min(1.0, ratio))

    @override
    def cleanup(self) -> None:
        self.client.clear_cache()
