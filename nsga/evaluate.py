"""
Pipeline de avaliação de genomes.

Fluxo completo:
1. Aplica config no K8s
2. Aguarda rollout
3. Executa load test para gerar carga
4. Coleta métricas do Prometheus (janela do load test)
5. Combina throughput do load test + métricas Prometheus
6. Calcula objetivos
"""
import time
from nsga.domain import Genome, RawMetrics, EvaluationResult, EvaluationStatus
from nsga.objectives import calculate_objectives, penalty_objectives
from nsga.adapters.k8s_adapter import K8sAdapter
from nsga.adapters.prometheus_adapter import PrometheusAdapter
from nsga.adapters.load_adapter import LoadAdapter
from shared.utils import log


class EvaluatePipeline:
    """
    Pipeline para avaliar um genome aplicando no K8s, executando load test
    e coletando métricas do Prometheus.
    """

    def __init__(
        self,
        k8s_adapter: K8sAdapter,
        prometheus_adapter: PrometheusAdapter,
        load_adapter: LoadAdapter,
        deployment_name: str,
        app_url: str = "",
        rollout_timeout_s: int = 300,
        stabilization_s: int = 5,
    ):
        """
        Args:
            k8s_adapter: Adapter para Kubernetes
            prometheus_adapter: Adapter para Prometheus
            load_adapter: Adapter para load test
            deployment_name: Nome do deployment a ser otimizado
            app_url: URL base da aplicação (ex: http://app-ga:8080)
            rollout_timeout_s: Timeout para rollout do K8s
            stabilization_s: Segundos de espera após rollout antes do load test
        """
        self.k8s = k8s_adapter
        self.prometheus = prometheus_adapter
        self.load = load_adapter
        self.deployment_name = deployment_name
        self.app_url = app_url
        self.rollout_timeout_s = rollout_timeout_s
        self.stabilization_s = stabilization_s

    def evaluate(self, genome: Genome) -> EvaluationResult:
        """
        Avalia um genome completo.

        Args:
            genome: Configuração de recursos a ser avaliada

        Returns:
            EvaluationResult com status e objetivos
        """
        start_time = time.time()

        try:
            # 1. Aplicar config no K8s
            log(f"[Eval] Aplicando config: cpu={genome.cpu_m}m, mem={genome.mem_mib}Mi, rep={genome.replicas}")
            success = self.k8s.apply_config(genome, self.deployment_name)
            if not success:
                log("[Eval] Falha ao aplicar config", level="warning")
                return self._failed_result(genome, time.time() - start_time)

            # 2. Aguardar rollout
            log("[Eval] Aguardando rollout...")
            ready = self.k8s.wait_ready(self.deployment_name, self.rollout_timeout_s)
            if not ready:
                log("[Eval] Timeout no rollout", level="warning")
                return self._timeout_result(genome, time.time() - start_time)

            # 3. Estabilização pós-rollout
            if self.stabilization_s > 0:
                log(f"[Eval] Aguardando estabilização ({self.stabilization_s}s)...")
                time.sleep(self.stabilization_s)

            # 4. Executar load test
            log("[Eval] Executando load test...")
            load_result = self.load.run_load_test(genome, self.app_url)
            log(
                f"[Eval] Load test concluído: throughput={load_result.throughput_rps:.1f} rps, "
                + f"success_rate={load_result.success_rate:.2%}, "
                + f"p95={load_result.p95_latency_ms:.0f}ms"
            )

            # 5. Coletar métricas do Prometheus na janela do load test
            log("[Eval] Coletando métricas do Prometheus...")
            prom_metrics = self.prometheus.collect_metrics(
                genome,
                self.deployment_name,
                load_result.start_time,
                load_result.end_time,
            )

            # 6. Combinar throughput do load test com métricas do Prometheus
            metrics = RawMetrics(
                throughput_rps=load_result.throughput_rps,
                cpu_throttle_rate=prom_metrics.cpu_throttle_rate,
                mem_peak_ratio=prom_metrics.mem_peak_ratio,
            )

            # 7. Calcular objetivos
            objectives = calculate_objectives(genome, metrics)

            eval_time = time.time() - start_time
            log(
                f"[Eval] Resultado: f1={objectives.f1:.4f}, f2={objectives.f2:.4f}, "
                + f"f3={objectives.f3:.4f} (tempo={eval_time:.1f}s)"
            )

            return EvaluationResult(
                genome=genome,
                status=EvaluationStatus.OK,
                raw_metrics=metrics,
                objectives=objectives,
                eval_time_s=eval_time,
            )

        except Exception as e:
            log(f"[Eval] Erro ao avaliar genome {genome}: {e}", level="error")
            return self._failed_result(genome, time.time() - start_time)

    def _failed_result(self, genome: Genome, eval_time_s: float) -> EvaluationResult:
        objectives = penalty_objectives(genome)
        return EvaluationResult(
            genome=genome,
            status=EvaluationStatus.FAIL,
            raw_metrics=None,
            objectives=objectives,
            eval_time_s=eval_time_s,
        )

    def _timeout_result(self, genome: Genome, eval_time_s: float) -> EvaluationResult:
        objectives = penalty_objectives(genome)
        return EvaluationResult(
            genome=genome,
            status=EvaluationStatus.TIMEOUT,
            raw_metrics=None,
            objectives=objectives,
            eval_time_s=eval_time_s,
        )

    def cleanup(self) -> None:
        """Limpeza de recursos dos adapters."""
        self.k8s.cleanup()
        self.prometheus.cleanup()
        self.load.cleanup()
