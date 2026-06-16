# ga/fitness.py
"""
Cálculo de fitness multicritério para o algoritmo genético.
Considera throughput, latência, uso de recursos e taxa de erros.
"""

import time
from typing import Optional
from dataclasses import dataclass

from ga.types import Individual, FitnessMetrics
from shared.utils import log, safe_divide


@dataclass
class FitnessWeights:
    """
    Pesos para cálculo de fitness multicritério.
    """

    latency_weight: float = 0.35
    resource_efficiency_weight: float = 0.4
    reliability_weight: float = 0.25

    def normalize(self):
        """Normaliza os pesos para somarem 1.0."""
        total = (
            + self.latency_weight
            + self.resource_efficiency_weight
            + self.reliability_weight
        )
        if total > 0:
            self.latency_weight /= total
            self.resource_efficiency_weight /= total
            self.reliability_weight /= total


class FitnessCalculator:
    """
    Calcula fitness de indivíduos baseado em métricas coletadas.
    """

    def __init__(self, weights: Optional[FitnessWeights] = None, sla_latency_ms: float = 2000.0):
        """
        Inicializa o calculador de fitness.

        Args:
            weights: Pesos para cálculo (default: pesos balanceados)
            sla_latency_ms: SLA de latência em milissegundos (default: 2000ms)
        """
        self.weights = weights or FitnessWeights()
        self.weights.normalize()
        self.sla_latency_ms = sla_latency_ms

    def calculate(self, individual: Individual, metrics: FitnessMetrics) -> float:
        """
        Calcula fitness score de um indivíduo.

        Fórmula geral:
        fitness = w1*throughput_score + w2*latency_score +
                 w3*efficiency_score + w4*reliability_score

        Args:
            individual: Indivíduo avaliado
            metrics: Métricas coletadas

        Returns:
            Score de fitness (valores maiores são melhores)
        """
        # 2. Latency score (invertido: menor latência é melhor)
        latency_score = self._normalize_latency(
            metrics.avg_latency, metrics.p95_latency, metrics.p99_latency
        )

        # 3. Resource efficiency score
        # Penaliza uso excessivo de recursos sem benefício proporcional
        efficiency_score = self._calculate_efficiency(individual, metrics)

        # 4. Reliability score
        # Penaliza alta taxa de erros
        reliability_score = self._calculate_reliability(metrics)

        # Fitness combinado
        fitness = (
            + self.weights.latency_weight * latency_score
            + self.weights.resource_efficiency_weight * efficiency_score
            + self.weights.reliability_weight * reliability_score
        )

        log(
            f"Fitness breakdown: "
            f"latency={latency_score:.3f}, efficiency={efficiency_score:.3f}, "
            f"reliability={reliability_score:.3f}, total={fitness:.4f}"
        )

        return fitness

    def _normalize_throughput(self, throughput: float) -> float:
        """
        Normaliza throughput para [0, 1].

        Assume que throughput > 100 req/s é excelente.
        """
        if throughput <= 0:
            return 0.0

        # Normalização sigmóide: 100 req/s = 0.9, 200 req/s = 0.99
        normalized = 1.0 / (1.0 + 100.0 / throughput)
        return min(1.0, normalized)

    def _normalize_latency(
        self,
        avg_latency: float,
        p95_latency: float,
        p99_latency: float,
    ) -> float:
        """
        Normaliza latência para [0,1] (maior é melhor).

        Baseada em:
        - Média (impacto geral)
        - P95 (tail latency)
        - P99 (cauda extrema)

        Usa o SLA configurado para definir quando a latência passa a ser inaceitável.
        """
        # Penalização suave baseada em SLA
        def latency_score(lat_ms: float) -> float:
            if lat_ms <= 0:
                return 1.0
            # lat <= SLA → score ~1
            # lat >> SLA → score → 0
            return 1.0 / (1.0 + (lat_ms / self.sla_latency_ms))

        avg_score = latency_score(avg_latency)
        p95_score = latency_score(p95_latency)
        p99_score = latency_score(p99_latency)

        return (
            0.2 * avg_score +
            0.4 * p95_score +
            0.4 * p99_score
        )

    def _calculate_efficiency(
        self, individual: Individual, metrics: FitnessMetrics
    ) -> float:
        """
        Calcula eficiência de recursos (0–1) combinando:
          1) Produtividade por recurso (throughput por CPU e por memória)
          2) Qualidade de utilização (evita underuse e saturação)
          3) Penalização por CPU throttling
          4) Penalização por pico de memória (risco de OOM)

        Premissa: throughput/latência vêm do load test; CPU/mem vêm do Prometheus.
        """
        eps = 1e-6

        # ---------------------------
        # 1) Produtividade por recurso
        # ---------------------------
        # CPU usage em "cores" (ex: 0.52 = 52% de um core)
        cpu_usage_cores = max(metrics.cpu_usage, 0.0)

        # Memory usage em bytes -> MiB
        mem_usage_mib = max(metrics.memory_usage / (1024 * 1024), 0.0)

        # Throughput em req/s
        thr = max(metrics.throughput, 0.0)

        # Eficiência "req/s por core" e "req/s por MiB"
        cpu_eff = thr / (cpu_usage_cores + eps)
        mem_eff = thr / (mem_usage_mib + eps)

        # Normalização suave em [0,1] sem depender de constantes globais:
        # x/(x+1) comprime valores grandes e evita explosões numéricas.
        cpu_eff_score = cpu_eff / (cpu_eff + 1.0)
        mem_eff_score = mem_eff / (mem_eff + 1.0)

        # ---------------------------
        # 2) Qualidade de utilização
        # ---------------------------
        # Queremos evitar:
        # - underuse (muito abaixo de ~0.3)
        # - saturação (muito acima de ~0.9)
        #
        # target define a zona de melhor equilíbrio.
        def util_quality(u: float, low: float = 0.3, high: float = 0.9, target: float = 0.6) -> float:
            # clamp
            u = 0.0 if u is None else max(0.0, min(1.0, u))
            if u < low:
                return u / low  # 0..1
            if u > high:
                return max(0.0, (1.0 - u) / (1.0 - high))  # 1..0
            # triangular peak at target within [low, high]
            width = (high - low)
            return max(0.0, 1.0 - abs(u - target) / (width / 2.0))

        cpu_q = util_quality(metrics.cpu_utilization)
        mem_q = util_quality(metrics.memory_utilization)

        util_score = 0.6 * cpu_q + 0.4 * mem_q  # CPU tende a ser mais dinâmico que memória

        # ---------------------------
        # 3) Penalização por throttling (CPU)
        # ---------------------------
        # cpu_throttling é a fração de períodos CFS que foram throttled, em [0, 1]
        # (calculada por integrations/prometheus_client.get_cpu_throttling como
        # rate(throttled_periods_total) / rate(periods_total)).
        # Penalidade suave: 0 -> 1.0; 0.5 -> ~0.286; 0.9 -> ~0.182.
        thrott = max(min(metrics.cpu_throttling or 0.0, 1.0), 0.0)
        thrott_penalty = 1.0 / (1.0 + 5.0 * thrott)

        # ---------------------------
        # 4) Penalização por pico de memória (risco OOM)
        # ---------------------------
        # memory_peak_usage em bytes. Convertemos para MiB e calculamos pico/limite.
        peak_mib = max((metrics.memory_peak_usage or 0.0) / (1024 * 1024), 0.0)
        mem_limit_mib = max(float(individual.memory_limit), eps)

        peak_ratio = peak_mib / mem_limit_mib  # ideal < 0.9
        # penaliza forte quando passa de 0.9
        if peak_ratio <= 0.9:
            mem_peak_penalty = 1.0
        else:
            # cai rapidamente acima de 0.9; ex: 1.0 -> 0.5, 1.1 -> ~0.33
            mem_peak_penalty = 1.0 / (1.0 + 10.0 * (peak_ratio - 0.9))

        # ---------------------------
        # 5) Combinação final
        # ---------------------------
        # Produtividade por recurso (cpu/mem) + saúde de uso + penalidades
        productivity_score = 0.7 * cpu_eff_score + 0.3 * mem_eff_score

        efficiency = (
            0.55 * productivity_score +
            0.45 * util_score
        )

        efficiency *= thrott_penalty
        efficiency *= mem_peak_penalty

        return max(0.0, min(1.0, efficiency))

    def _calculate_reliability(self, metrics: FitnessMetrics) -> float:
        """
        Calcula confiabilidade (0–1).

        Objetivo:
        - Recompensar alta taxa de sucesso
        - Penalizar qualquer erro
        - Penalizar instabilidade (erros concentrados ou frequentes)
        """

        success = max(0.0, min(1.0, metrics.success_rate))
        error_rate = max(0.0, metrics.error_rate)

        # Penalização suave por erros:
        # 0 erros -> 1.0
        # cresce rapidamente com erros
        error_penalty = 1.0 / (1.0 + 20.0 * error_rate)
        reliability = success * error_penalty

        return max(0.0, min(1.0, reliability))


class FitnessEvaluator:
    """
    Avalia indivíduos coletando métricas e calculando fitness.
    """

    def __init__(
        self,
        prometheus_client,
        k8s_client,
        load_tester,
        app_config,
        fitness_calculator: Optional[FitnessCalculator] = None,
        require_prometheus_metrics: bool = False,
    ):
        """
        Inicializa o avaliador.

        Args:
            prometheus_client: Cliente Prometheus
            k8s_client: Cliente Kubernetes
            load_tester: Load tester
            app_config: Configuração da aplicação
            fitness_calculator: Calculador de fitness (default: cria novo)
            require_prometheus_metrics: Se True, falha avaliação se métricas não disponíveis
        """
        self.prometheus = prometheus_client
        self.k8s = k8s_client
        self.load_tester = load_tester
        self.app_config = app_config
        self.calculator = fitness_calculator or FitnessCalculator()
        self.require_prometheus_metrics = require_prometheus_metrics

    def evaluate(self, individual: Individual) -> tuple:
        """
        Avalia um indivíduo completo.

        Args:
            individual: Indivíduo a avaliar

        Returns:
            Tupla (fitness_score, metrics)
        """
        start_time = time.time()

        try:
            # 1. Aplica configuração no cluster
            self.k8s.apply_configuration(individual, save_for_rollback=True)

            # 1.5. Pequena pausa para garantir que o Kubernetes registrou as mudanças
            log(
                "Waiting for Kubernetes to register configuration changes...",
                level="debug",
            )
            time.sleep(3)

            # 2. Aguarda rollout
            rollout_success = self.k8s.wait_for_rollout()
            if not rollout_success:
                log("Rollout failed, returning low fitness", level="warning")
                metrics = FitnessMetrics()
                return 0.0, metrics

            # 3. Executa load test
            load_test_url = f"{self.app_config.url}/mixed"
            load_result = self.load_tester.run(load_test_url)

            # 4. Coleta métricas do Prometheus usando timestamps do load test
            log(f"📊 Collecting metrics from Prometheus for {self.app_config.label}...")
            log(f"📊 Using time range: {load_result.start_time} to {load_result.end_time} ({load_result.duration:.2f}s)", level="debug")

            cpu_usage = self.prometheus.get_cpu_usage(
                self.app_config.label,
                start_time=load_result.start_time,
                end_time=load_result.end_time
            )
            cpu_throttling = self.prometheus.get_cpu_throttling(
                self.app_config.label,
                start_time=load_result.start_time,
                end_time=load_result.end_time
            )
            memory_usage = self.prometheus.get_memory_usage(
                self.app_config.label,
                start_time=load_result.start_time,
                end_time=load_result.end_time
            )
            memory_peak_usage = self.prometheus.get_peak_memory_usage(
                self.app_config.label,
                start_time=load_result.start_time,
                end_time=load_result.end_time
            )

            log(
                f"📊 Metrics collected: CPU={cpu_usage:.4f} cores, "
                f"CPU_THROTTLING={cpu_throttling:.4f}, "
                f"MEMORY={memory_usage / (1024*1024):.2f}MB, "
                f"MEMORY_PEAK={memory_peak_usage / (1024*1024):.2f}MB"
            )

            # Validação: Verifica se métricas são válidas
            metrics_valid = cpu_usage > 0 or memory_usage > 0
            if not metrics_valid:
                log(
                    "⚠️ WARNING: All Prometheus metrics returned 0.0! "
                    "This may indicate that metrics are not available yet. "
                    "Fitness calculation will be based only on load test results.",
                    level="warning"
                )

                # Se configurado para requerer métricas, falha a avaliação
                if self.require_prometheus_metrics:
                    raise Exception(
                        "Prometheus metrics are required but returned 0.0. "
                        "Possible causes: pods not running, metrics not collected yet, "
                        "or incorrect labels. Set GA_REQUIRE_PROMETHEUS_METRICS=false "
                        "to allow evaluation without Prometheus metrics."
                    )

            # 5. Constrói métricas
            metrics = FitnessMetrics(
                throughput=load_result.throughput,
                avg_latency=load_result.avg_latency,
                p95_latency=load_result.p95_latency,
                p99_latency=load_result.p99_latency,
                request_rate=load_result.throughput,
                error_rate=load_result.fail / load_result.total,
                success_rate=load_result.success_rate,
                total_requests=load_result.total,
                failed_requests=load_result.fail,
                cpu_usage=cpu_usage,
                memory_usage=memory_usage,
                cpu_utilization=safe_divide(cpu_usage, individual.cpu_limit),
                memory_utilization=safe_divide(
                    memory_usage / (1024 * 1024), individual.memory_limit
                ),
                cpu_throttling=cpu_throttling,
                memory_peak_usage=memory_peak_usage,
            )

            # 6. Calcula fitness
            fitness = self.calculator.calculate(individual, metrics)

            evaluation_time = time.time() - start_time
            log(
                f"Evaluation completed in {evaluation_time:.2f}s: fitness={fitness:.4f}"
            )

            return fitness, metrics

        except Exception as e:
            log(f"Evaluation failed: {e}", level="error")
            # Re-lança a exceção para que o optimizer possa decidir o que fazer
            # (não cachear resultados de erro)
            raise
