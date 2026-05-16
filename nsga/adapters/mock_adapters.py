"""
Mock adapters para testes sem cluster real.
"""
import time
import random

from typing_extensions import override

from nsga.domain import Genome, RawMetrics
from nsga.adapters.k8s_adapter import K8sAdapter
from nsga.adapters.prometheus_adapter import PrometheusAdapter
from nsga.adapters.load_adapter import LoadAdapter


class MockK8sAdapter(K8sAdapter):
    """
    Mock do adapter K8s para testes.
    Simula aplicação de config e rollout sem cluster real.
    """

    def __init__(self, namespace: str = "default", apply_delay_s: float = 0.05):
        self.namespace: str = namespace
        self.apply_delay_s: float = apply_delay_s
        self.current_config: Genome | None = None

    @override
    def apply_config(self, genome: Genome, deployment_name: str) -> bool:
        time.sleep(self.apply_delay_s)
        self.current_config = genome
        return True

    @override
    def wait_ready(self, deployment_name: str, timeout_s: int = 300) -> bool:
        if self.current_config:
            rollout_time = min(0.05 + self.current_config.replicas * 0.01, timeout_s)
            time.sleep(rollout_time)
        return True

    @override
    def cleanup(self) -> None:
        pass


class MockPrometheusAdapter(PrometheusAdapter):
    """
    Mock do adapter Prometheus para testes.
    Gera métricas sintéticas baseadas no genome com comportamento realista.
    """

    def __init__(self, seed: int = 42):
        self.rng: random.Random = random.Random(seed)

    @override
    def collect_metrics(
        self,
        genome: Genome,
        deployment_name: str,
        start_time: float,
        end_time: float,
    ) -> RawMetrics:
        """
        Gera métricas sintéticas a partir do genome.
        O throughput vem do LoadAdapter, então aqui retornamos 0.0 para ele.
        """
        time.sleep(0.01)

        cpu_throttle_rate = self._calculate_cpu_throttle(genome.cpu_m)
        mem_peak_ratio = self._calculate_mem_peak(genome.mem_mib)

        return RawMetrics(
            throughput_rps=0.0,
            cpu_throttle_rate=cpu_throttle_rate,
            mem_peak_ratio=mem_peak_ratio,
        )

    def _calculate_cpu_throttle(self, cpu_m: int) -> float:
        if cpu_m < 500:
            base = 0.3 + (500 - cpu_m) / 500.0 * 0.4
        elif cpu_m < 1000:
            base = 0.1 + (1000 - cpu_m) / 500.0 * 0.2
        else:
            base = 0.05
        noise = self.rng.uniform(0.9, 1.1)
        return max(0.0, min(1.0, base * noise))

    def _calculate_mem_peak(self, mem_mib: int) -> float:
        if mem_mib < 512:
            base = 0.7 + (512 - mem_mib) / 512.0 * 0.25
        elif mem_mib < 1024:
            base = 0.5 + (1024 - mem_mib) / 512.0 * 0.2
        else:
            base = 0.4
        noise = self.rng.uniform(0.9, 1.1)
        return max(0.0, min(1.0, base * noise))

    @override
    def cleanup(self) -> None:
        pass


def create_mock_adapters(seed: int = 42) -> tuple[MockK8sAdapter, MockPrometheusAdapter, LoadAdapter]:
    """
    Cria todos os mock adapters para testes.

    Args:
        seed: Seed para geração determinística

    Returns:
        Tupla (k8s_adapter, prometheus_adapter, load_adapter)
    """
    from nsga.adapters.load_adapter import MockLoadAdapter

    k8s = MockK8sAdapter()
    prom = MockPrometheusAdapter(seed=seed)
    load = MockLoadAdapter(seed=seed)
    return k8s, prom, load
