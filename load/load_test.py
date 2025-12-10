# load/load_test.py
"""
Sistema de load testing robusto com suporte a perfis de carga.
"""
import time
import requests
import concurrent.futures
from dataclasses import dataclass
from typing import Dict, List, Optional
from threading import Lock

from load.workload_profiles import WorkloadProfile, get_profile
from ga.config import LoadTestConfig
from ga.exceptions import LoadTestError
from ga.utils import log


@dataclass
class LoadTestResult:
    """Resultado de um teste de carga."""
    success: int = 0
    fail: int = 0
    total: int = 0
    avg_latency: float = 0.0
    min_latency: float = 0.0
    max_latency: float = 0.0
    p50_latency: float = 0.0
    p95_latency: float = 0.0
    p99_latency: float = 0.0
    throughput: float = 0.0
    success_rate: float = 0.0
    duration: float = 0.0
    latencies: List[float] = None

    def __post_init__(self):
        if self.latencies is None:
            self.latencies = []

    def to_dict(self) -> Dict:
        """Converte para dicionário."""
        return {
            "success": self.success,
            "fail": self.fail,
            "total": self.total,
            "avg_latency": self.avg_latency,
            "min_latency": self.min_latency,
            "max_latency": self.max_latency,
            "p50_latency": self.p50_latency,
            "p95_latency": self.p95_latency,
            "p99_latency": self.p99_latency,
            "throughput": self.throughput,
            "success_rate": self.success_rate,
            "duration": self.duration
        }

    def _calculate_percentile(self, percentile: float) -> float:
        """Calcula percentil das latências."""
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        index = int(len(sorted_latencies) * percentile)
        index = min(index, len(sorted_latencies) - 1)
        return sorted_latencies[index]

    def finalize(self):
        """Calcula métricas finais."""
        if not self.latencies:
            return

        sorted_latencies = sorted(self.latencies)
        self.avg_latency = sum(sorted_latencies) / len(sorted_latencies)
        self.min_latency = sorted_latencies[0]
        self.max_latency = sorted_latencies[-1]
        self.p50_latency = self._calculate_percentile(0.50)
        self.p95_latency = self._calculate_percentile(0.95)
        self.p99_latency = self._calculate_percentile(0.99)

        self.total = self.success + self.fail
        self.success_rate = self.success / self.total if self.total > 0 else 0.0
        self.throughput = self.total / self.duration if self.duration > 0 else 0.0


class LoadTester:
    """
    Executor de testes de carga com suporte a perfis dinâmicos.
    """

    def __init__(self, config: Optional[LoadTestConfig] = None):
        """
        Inicializa o load tester.

        Args:
            config: Configuração (default: carrega de env)
        """
        self.config = config or LoadTestConfig.from_env()
        self.profile: Optional[WorkloadProfile] = None

        # Carrega perfil se especificado
        if self.config.profile:
            try:
                self.profile = get_profile(self.config.profile)
                log(f"Loaded workload profile: {self.profile.name}")
            except ValueError as e:
                log(f"Failed to load profile {self.config.profile}: {e}. Using default.", level="warning")

    def run(
        self,
        url: str,
        duration: Optional[int] = None,
        concurrency: Optional[int] = None,
        profile: Optional[WorkloadProfile] = None,
        timeout: Optional[int] = None
    ) -> LoadTestResult:
        """
        Executa um teste de carga.

        Args:
            url: URL para testar
            duration: Duração em segundos (usa config se None)
            concurrency: Concorrência fixa (usa profile se None)
            profile: Perfil de carga (usa config se None)
            timeout: Timeout por requisição (usa config se None)

        Returns:
            Resultado do teste

        Raises:
            LoadTestError: Se o teste falhar
        """
        duration = duration or self.config.duration
        timeout = timeout or self.config.timeout
        profile = profile or self.profile

        result = LoadTestResult()
        start_time = time.time()
        end_time = start_time + duration

        # Lock para thread-safety
        lock = Lock()
        latencies: List[float] = []
        success_count = 0
        fail_count = 0

        def worker(worker_id: int):
            """Worker thread que executa requisições."""
            nonlocal success_count, fail_count
            worker_latencies = []
            last_concurrency_check = start_time
            current_concurrency = concurrency or (profile.base_concurrency if profile else self.config.concurrency)

            while time.time() < end_time:
                # Atualiza concorrência se usando perfil dinâmico
                if profile and not concurrency:
                    elapsed = time.time() - start_time
                    current_concurrency = profile.get_concurrency_at(elapsed)

                # Executa requisição
                req_start = time.time()
                try:
                    response = requests.get(url, timeout=timeout)
                    latency = time.time() - req_start

                    with lock:
                        if response.status_code == 200:
                            success_count += 1
                            worker_latencies.append(latency)
                        else:
                            fail_count += 1
                except Exception as e:
                    with lock:
                        fail_count += 1
                    log(f"Request failed in worker {worker_id}: {e}", level="debug")

                # Pequeno delay para evitar sobrecarga
                time.sleep(0.01)

            # Adiciona latências ao pool global
            with lock:
                latencies.extend(worker_latencies)

        # Determina número de workers
        if profile and not concurrency:
            # Usa max_concurrency do perfil
            num_workers = profile.max_concurrency
        else:
            num_workers = concurrency or self.config.concurrency

        log(f"Starting load test: url={url}, duration={duration}s, workers={num_workers}, profile={profile.name if profile else 'fixed'}")

        try:
            # Executa workers
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
                futures = [executor.submit(worker, i) for i in range(num_workers)]
                concurrent.futures.wait(futures)

            # Finaliza resultado
            result.duration = time.time() - start_time
            result.latencies = latencies
            result.success = success_count
            result.fail = fail_count
            result.finalize()

            log(f"Load test completed: {result.success} success, {result.fail} failed, "
                f"throughput={result.throughput:.2f} req/s, avg_latency={result.avg_latency*1000:.2f}ms")

            return result

        except Exception as e:
            raise LoadTestError(f"Load test failed: {e}") from e


