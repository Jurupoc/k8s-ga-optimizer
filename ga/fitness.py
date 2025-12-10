# ga/fitness.py
"""
Cálculo de fitness multicritério para o algoritmo genético.
Considera throughput, latência, uso de recursos e taxa de erros.
"""
from typing import Dict, Optional
from dataclasses import dataclass

from ga.types import Individual, FitnessMetrics
from ga.utils import log, safe_divide


@dataclass
class FitnessWeights:
    """
    Pesos para cálculo de fitness multicritério.
    """
    throughput_weight: float = 0.3
    latency_weight: float = 0.25
    resource_efficiency_weight: float = 0.25
    reliability_weight: float = 0.2

    def normalize(self):
        """Normaliza os pesos para somarem 1.0."""
        total = (self.throughput_weight + self.latency_weight +
                self.resource_efficiency_weight + self.reliability_weight)
        if total > 0:
            self.throughput_weight /= total
            self.latency_weight /= total
            self.resource_efficiency_weight /= total
            self.reliability_weight /= total


class FitnessCalculator:
    """
    Calcula fitness de indivíduos baseado em métricas coletadas.
    """

    def __init__(self, weights: Optional[FitnessWeights] = None):
        """
        Inicializa o calculador de fitness.

        Args:
            weights: Pesos para cálculo (default: pesos balanceados)
        """
        self.weights = weights or FitnessWeights()
        self.weights.normalize()

    def calculate(
        self,
        individual: Individual,
        metrics: FitnessMetrics
    ) -> float:
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
        # 1. Throughput score (normalizado)
        # Maior throughput é melhor
        throughput_score = self._normalize_throughput(metrics.throughput)

        # 2. Latency score (invertido: menor latência é melhor)
        latency_score = self._normalize_latency(metrics.avg_latency, metrics.p95_latency)

        # 3. Resource efficiency score
        # Penaliza uso excessivo de recursos sem benefício proporcional
        efficiency_score = self._calculate_efficiency(individual, metrics)

        # 4. Reliability score
        # Penaliza alta taxa de erros
        reliability_score = self._calculate_reliability(metrics)

        # Fitness combinado
        fitness = (
            self.weights.throughput_weight * throughput_score +
            self.weights.latency_weight * latency_score +
            self.weights.resource_efficiency_weight * efficiency_score +
            self.weights.reliability_weight * reliability_score
        )

        log(f"Fitness breakdown: throughput={throughput_score:.3f}, "
            f"latency={latency_score:.3f}, efficiency={efficiency_score:.3f}, "
            f"reliability={reliability_score:.3f}, total={fitness:.4f}")

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

    def _normalize_latency(self, avg_latency: float, p95_latency: float) -> float:
        """
        Normaliza latência para [0, 1] (invertido: menor é melhor).

        Considera tanto latência média quanto p95.
        """
        if avg_latency <= 0:
            return 1.0

        # Penaliza tanto latência média alta quanto p95 alto
        # Latência < 100ms = excelente, > 1s = ruim
        avg_score = 1.0 / (1.0 + avg_latency * 10)  # 100ms = 0.5, 1s = 0.09
        p95_score = 1.0 / (1.0 + p95_latency * 5) if p95_latency > 0 else 1.0

        # Média ponderada (p95 tem mais peso)
        return 0.4 * avg_score + 0.6 * p95_score

    def _calculate_efficiency(self, individual: Individual, metrics: FitnessMetrics) -> float:
        """
        Calcula score de eficiência de recursos.

        Penaliza configurações que usam muitos recursos sem benefício proporcional.
        """
        # Utilização de recursos (0.0 a 1.0)
        cpu_util = metrics.cpu_utilization
        mem_util = metrics.memory_utilization

        # Utilização média
        avg_util = (cpu_util + mem_util) / 2.0

        # Eficiência: melhor se usar recursos de forma equilibrada
        # Utilização muito baixa (< 0.3) = desperdício
        # Utilização muito alta (> 0.9) = risco de saturação
        # Utilização ideal = 0.5-0.7

        if avg_util < 0.3:
            # Desperdício de recursos
            efficiency = avg_util / 0.3  # penaliza
        elif avg_util > 0.9:
            # Risco de saturação
            efficiency = (1.0 - avg_util) / 0.1  # penaliza
        else:
            # Zona ideal
            efficiency = 1.0 - abs(avg_util - 0.6) / 0.3  # pico em 0.6

        # Bonus por throughput alto com recursos baixos
        if metrics.throughput > 50 and avg_util < 0.5:
            efficiency *= 1.2  # bonus de 20%

        return min(1.0, max(0.0, efficiency))

    def _calculate_reliability(self, metrics: FitnessMetrics) -> float:
        """
        Calcula score de confiabilidade.

        Penaliza alta taxa de erros e baixa taxa de sucesso.
        """
        # Taxa de sucesso (0.0 a 1.0)
        success_rate = metrics.success_rate

        # Taxa de erros normalizada
        error_rate_norm = min(1.0, metrics.error_rate / 10.0)  # > 10 errors/s = ruim

        # Score de confiabilidade
        reliability = success_rate * (1.0 - error_rate_norm * 0.5)

        return max(0.0, reliability)


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
        fitness_calculator: Optional[FitnessCalculator] = None
    ):
        """
        Inicializa o avaliador.

        Args:
            prometheus_client: Cliente Prometheus
            k8s_client: Cliente Kubernetes
            load_tester: Load tester
            app_config: Configuração da aplicação
            fitness_calculator: Calculador de fitness (default: cria novo)
        """
        self.prometheus = prometheus_client
        self.k8s = k8s_client
        self.load_tester = load_tester
        self.app_config = app_config
        self.calculator = fitness_calculator or FitnessCalculator()

    def evaluate(self, individual: Individual) -> tuple:
        """
        Avalia um indivíduo completo.

        Args:
            individual: Indivíduo a avaliar

        Returns:
            Tupla (fitness_score, metrics)
        """
        import time
        start_time = time.time()

        try:
            # 1. Aplica configuração no cluster
            self.k8s.apply_configuration(individual, save_for_rollback=True)

            # 2. Aguarda rollout
            rollout_success = self.k8s.wait_for_rollout()
            if not rollout_success:
                log("Rollout failed, returning low fitness", level="warning")
                metrics = FitnessMetrics()
                return 0.0, metrics

            # 3. Executa load test
            load_test_url = f"{self.app_config.url}/sort?size=5000"
            load_result = self.load_tester.run(load_test_url)

            # 4. Coleta métricas do Prometheus
            cpu_usage = self.prometheus.get_cpu_usage(self.app_config.label, minutes=1)
            memory_usage = self.prometheus.get_memory_usage(self.app_config.label)
            request_rate = self.prometheus.get_request_rate(self.app_config.label, minutes=1)
            p95_latency = self.prometheus.get_request_latency(self.app_config.label, quantile=0.95, minutes=1)
            p99_latency = self.prometheus.get_request_latency(self.app_config.label, quantile=0.99, minutes=1)
            error_rate = self.prometheus.get_error_rate(self.app_config.label, minutes=1)

            # 5. Constrói métricas
            metrics = FitnessMetrics(
                throughput=load_result.throughput,
                avg_latency=load_result.avg_latency,
                p95_latency=p95_latency if p95_latency > 0 else load_result.p95_latency,
                p99_latency=p99_latency if p99_latency > 0 else load_result.p99_latency,
                success_rate=load_result.success_rate,
                total_requests=load_result.total,
                failed_requests=load_result.fail,
                cpu_usage=cpu_usage,
                memory_usage=memory_usage,
                cpu_utilization=safe_divide(cpu_usage, individual.cpu_limit),
                memory_utilization=safe_divide(memory_usage / (1024 * 1024), individual.memory_limit),
                request_rate=request_rate,
                error_rate=error_rate
            )

            # 6. Calcula fitness
            fitness = self.calculator.calculate(individual, metrics)

            evaluation_time = time.time() - start_time
            log(f"Evaluation completed in {evaluation_time:.2f}s: fitness={fitness:.4f}")

            return fitness, metrics

        except Exception as e:
            log(f"Evaluation failed: {e}", level="error")
            metrics = FitnessMetrics()
            return 0.0, metrics

