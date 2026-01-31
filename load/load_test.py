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

from .workload_profiles import WorkloadProfile, get_profile
from .config import LoadTestConfig
from .exceptions import LoadTestError
from shared.utils import log


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
            "duration": self.duration,
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
    
    def is_valid(self, min_requests: int = 50, max_error_rate: float = 0.8) -> tuple[bool, str]:
        """
        Valida se o resultado do load test é confiável.
        
        Args:
            min_requests: Número mínimo de requisições
            max_error_rate: Taxa máxima de erro aceitável (0.0 - 1.0)
        
        Returns:
            Tupla (is_valid, reason)
        """
        # Verifica se houve requisições suficientes
        if self.total < min_requests:
            return False, f"Too few requests: {self.total} < {min_requests}"
        
        # Verifica taxa de erro
        error_rate = self.fail / self.total if self.total > 0 else 1.0
        if error_rate > max_error_rate:
            return False, f"High error rate: {error_rate:.1%} > {max_error_rate:.1%}"
        
        # Verifica se houve alguma requisição bem-sucedida
        if self.success == 0:
            return False, "No successful requests"
        
        return True, "OK"


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
                log(
                    f"Failed to load profile {self.config.profile}: {e}. Using fixed concurrency.",
                    level="warning",
                )

    def _run_phase(
        self,
        url: str,
        duration: int,
        concurrency: int,
        timeout: int,
        phase_name: str = "test",
    ) -> LoadTestResult:
        """
        Executa uma fase de teste de carga (warm-up ou teste real).

        Args:
            url: URL para testar
            duration: Duração em segundos
            concurrency: Número de workers concorrentes
            timeout: Timeout por requisição
            phase_name: Nome da fase (para logging)

        Returns:
            Resultado do teste

        Raises:
            LoadTestError: Se o teste falhar
        """

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

            while time.time() < end_time:
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
                            log(
                                f"Request status_code not 200: {response.status_code} - {response.text}",
                                level="debug",
                            )
                            fail_count += 1

                except requests.exceptions.Timeout:
                    with lock:
                        fail_count += 1
                    log(f"Request timed out for worker {worker_id}", level="debug")
                except Exception as e:
                    with lock:
                        fail_count += 1
                    log(f"Request failed in worker {worker_id}: {e}", level="debug")

                # Pequeno delay para evitar sobrecarga
                time.sleep(0.01)

            # Adiciona latências ao pool global com lock
            with lock:
                latencies.extend(worker_latencies)

        num_workers = concurrency

        log(
            f"Starting {phase_name} phase: url={url}, duration={duration}s, workers={num_workers}"
        )

        try:
            # Executa workers
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=num_workers
            ) as executor:
                futures = [executor.submit(worker, i) for i in range(num_workers)]
                concurrent.futures.wait(futures)

            # Finaliza resultado
            result.duration = time.time() - start_time
            result.latencies = latencies
            result.success = success_count
            result.fail = fail_count
            result.finalize()

            log(f"{phase_name.capitalize()} phase completed:")
            log(
                f"  Requisições: {result.total} total ({result.success} sucesso, {result.fail} falhas)"
            )
            log(f"  Taxa de sucesso: {result.success_rate*100:.2f}%")
            log(f"  Throughput: {result.throughput:.2f} req/s")
            log(f"  Duração: {result.duration:.2f}s")
            log("  Latências:")
            log(f"    Média: {result.avg_latency*1000:.2f}ms")
            log(f"    Mínima: {result.min_latency*1000:.2f}ms")
            log(f"    Máxima: {result.max_latency*1000:.2f}ms")
            log(f"    P50: {result.p50_latency*1000:.2f}ms")
            log(f"    P95: {result.p95_latency*1000:.2f}ms")
            log(f"    P99: {result.p99_latency*1000:.2f}ms")

            return result

        except Exception as e:
            raise LoadTestError(f"{phase_name.capitalize()} phase failed: {e}") from e
    
    def run(
        self,
        url: str,
        duration: Optional[int] = None,
        concurrency: Optional[int] = None,
        profile: Optional[WorkloadProfile] = None,
        timeout: Optional[int] = None,
        skip_warmup: bool = False,
    ) -> LoadTestResult:
        """
        Executa um teste de carga completo (com warm-up opcional).

        Args:
            url: URL para testar
            duration: Duração em segundos (usa config se None)
            concurrency: Concorrência fixa (usa profile se None)
            profile: Perfil de carga (usa config se None)
            timeout: Timeout por requisição (usa config se None)
            skip_warmup: Se True, pula fase de warm-up

        Returns:
            Resultado do teste (apenas da fase principal, não inclui warm-up)

        Raises:
            LoadTestError: Se o teste falhar
        """
        duration = duration or self.config.duration
        timeout = timeout or self.config.timeout
        profile = profile or self.profile
        
        # Determina concorrência
        if profile and not concurrency:
            concurrency = profile.max_concurrency
        else:
            concurrency = concurrency or self.config.concurrency
        
        # Fase 1: Warm-up (opcional)
        if not skip_warmup and self.config.warmup_duration > 0:
            log(f"🔥 Starting warm-up phase ({self.config.warmup_duration}s with {self.config.warmup_concurrency} workers)...")
            try:
                warmup_result = self._run_phase(
                    url=url,
                    duration=self.config.warmup_duration,
                    concurrency=self.config.warmup_concurrency,
                    timeout=timeout,
                    phase_name="warm-up",
                )
                log(f"✅ Warm-up completed: {warmup_result.total} requests, {warmup_result.success_rate*100:.1f}% success")
            except Exception as e:
                log(f"⚠️ Warm-up failed: {e}. Continuing with main test...", level="warning")
        
        # Fase 2: Teste principal
        log(f"🚀 Starting main load test ({duration}s with {concurrency} workers)...")
        result = self._run_phase(
            url=url,
            duration=duration,
            concurrency=concurrency,
            timeout=timeout,
            phase_name="load test",
        )
        
        # Validação
        is_valid, reason = result.is_valid(
            min_requests=self.config.min_requests,
            max_error_rate=self.config.max_error_rate,
        )
        
        if not is_valid:
            log(f"⚠️ Load test validation failed: {reason}", level="warning")
        else:
            log(f"✅ Load test validation passed")
        
        return result
