"""
Adapter de load test para o pipeline NSGA-II.

Fornece uma interface abstrata e duas implementações:
- RealLoadAdapter: executa load test real via LoadTester existente
- MockLoadAdapter: gera métricas sintéticas para testes offline
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
import random
from typing import TYPE_CHECKING

from typing_extensions import override

from nsga.domain import Genome

if TYPE_CHECKING:
    from load import LoadTester, LoadTestConfig


@dataclass
class LoadResult:
    """Resultado resumido de um load test para o NSGA-II."""
    throughput_rps: float
    start_time: float
    end_time: float
    success_rate: float
    avg_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    total_requests: int
    failed_requests: int


class LoadAdapter(ABC):
    """Interface para executar load tests."""

    @abstractmethod
    def run_load_test(self, genome: Genome, target_url: str) -> LoadResult:
        """
        Executa um load test contra a aplicação alvo.

        Args:
            genome: Genome sendo avaliado (informacional)
            target_url: URL base da aplicação

        Returns:
            LoadResult com métricas do load test
        """
        ...

    @abstractmethod
    def cleanup(self) -> None:
        ...


class RealLoadAdapter(LoadAdapter):
    """
    Executa load tests reais usando o LoadTester existente em load/.
    """

    def __init__(
        self,
        duration: int = 60,
        concurrency: int = 20,
        timeout: int = 10,
        warmup_duration: int = 10,
        warmup_concurrency: int = 2,
        endpoint: str = "/mixed",
    ):
        """
        Args:
            duration: Duração do load test principal (segundos)
            concurrency: Número de workers concorrentes
            timeout: Timeout por requisição (segundos)
            warmup_duration: Duração do warmup (0 = sem warmup)
            warmup_concurrency: Workers durante warmup
            endpoint: Endpoint da API a ser testado
        """
        from load import LoadTester, LoadTestConfig

        self.config: "LoadTestConfig" = LoadTestConfig(
            duration=duration,
            concurrency=concurrency,
            timeout=timeout,
            warmup_duration=warmup_duration,
            warmup_concurrency=warmup_concurrency,
        )
        self.tester: "LoadTester" = LoadTester(config=self.config)
        self.endpoint: str = endpoint

    @override
    def run_load_test(self, genome: Genome, target_url: str) -> LoadResult:
        url = target_url.rstrip("/") + self.endpoint
        result = self.tester.run(url=url)

        return LoadResult(
            throughput_rps=result.throughput,
            start_time=result.start_time,
            end_time=result.end_time,
            success_rate=result.success_rate,
            avg_latency_ms=result.avg_latency * 1000,
            p95_latency_ms=result.p95_latency * 1000,
            p99_latency_ms=result.p99_latency * 1000,
            total_requests=result.total,
            failed_requests=result.fail,
        )

    @override
    def cleanup(self) -> None:
        pass


class MockLoadAdapter(LoadAdapter):
    """
    Gera resultados sintéticos de load test baseados no genome.
    Permite testar o pipeline sem um cluster real.
    """

    def __init__(self, seed: int = 42, base_duration: float = 60.0):
        self.rng: random.Random = random.Random(seed)
        self.base_duration: float = base_duration
        self._fake_clock: float = 1_700_000_000.0

    @override
    def run_load_test(self, genome: Genome, target_url: str) -> LoadResult:
        import time
        time.sleep(0.05)

        cpu_factor = min(genome.cpu_m / 1000.0, 1.0)
        mem_factor = min(genome.mem_mib / 1024.0, 1.0)
        capacity_per_replica = 100.0 * cpu_factor * mem_factor
        replica_factor = genome.replicas * (1.0 - 0.05 * max(0, genome.replicas - 8))
        throughput = max(10.0, capacity_per_replica * replica_factor * self.rng.uniform(0.92, 1.08))

        avg_latency_ms = max(5.0, 200.0 / (cpu_factor + 0.1) * self.rng.uniform(0.9, 1.1))
        p95_latency_ms = avg_latency_ms * self.rng.uniform(1.8, 2.5)
        p99_latency_ms = p95_latency_ms * self.rng.uniform(1.3, 1.8)

        total_requests = int(throughput * self.base_duration)
        fail_rate = max(0.0, 0.02 * (1.0 - cpu_factor) * self.rng.uniform(0.5, 1.5))
        failed = int(total_requests * fail_rate)

        start = self._fake_clock
        end = start + self.base_duration
        self._fake_clock = end + 5.0

        return LoadResult(
            throughput_rps=throughput,
            start_time=start,
            end_time=end,
            success_rate=(total_requests - failed) / max(total_requests, 1),
            avg_latency_ms=avg_latency_ms,
            p95_latency_ms=p95_latency_ms,
            p99_latency_ms=p99_latency_ms,
            total_requests=total_requests,
            failed_requests=failed,
        )

    @override
    def cleanup(self) -> None:
        pass
