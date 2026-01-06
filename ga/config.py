# ga/config.py
"""
Configurações centralizadas do GA.
"""
import os
from typing import Tuple
from dataclasses import dataclass


@dataclass
class GAParameters:
    """Parâmetros do algoritmo genético."""
    population_size: int = 6
    generations: int = 5
    mutation_rate: float = 0.2
    crossover_rate: float = 0.8
    elitism_count: int = 1
    tournament_size: int = 2
    stabilization_seconds: int = 30

    # Limites dos parâmetros
    replicas_bounds: Tuple[int, int] = (1, 6)
    cpu_limit_bounds: Tuple[float, float] = (0.1, 2.0)
    memory_limit_bounds: Tuple[int, int] = (128, 1024)

    @classmethod
    def from_env(cls) -> "GAParameters":
        """Carrega configuração de variáveis de ambiente."""
        return cls(
            population_size=int(os.environ.get("GA_POPULATION", "6")),
            generations=int(os.environ.get("GA_GENERATIONS", "5")),
            mutation_rate=float(os.environ.get("GA_MUTATION_RATE", "0.2")),
            crossover_rate=float(os.environ.get("GA_CROSSOVER_RATE", "0.8")),
            elitism_count=int(os.environ.get("GA_ELITISM_COUNT", "1")),
            tournament_size=int(os.environ.get("GA_TOURNAMENT_SIZE", "2")),
            stabilization_seconds=int(os.environ.get("GA_STABILIZATION_SECONDS", "30")),
            replicas_bounds=(
                int(os.environ.get("GA_REPLICAS_MIN", "1")),
                int(os.environ.get("GA_REPLICAS_MAX", "6"))
            ),
            cpu_limit_bounds=(
                float(os.environ.get("GA_CPU_MIN", "0.1")),
                float(os.environ.get("GA_CPU_MAX", "2.0"))
            ),
            memory_limit_bounds=(
                int(os.environ.get("GA_MEMORY_MIN", "128")),
                int(os.environ.get("GA_MEMORY_MAX", "1024"))
            )
        )


@dataclass
class AppConfig:
    """Configuração da aplicação."""
    url: str = "http://app-ga.default.svc.cluster.local:8080"
    label: str = "app-ga"
    deployment_name: str = "app-ga"
    namespace: str = "default"
    container_name: str = "app-ga"

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Carrega configuração de variáveis de ambiente."""
        return cls(
            url=os.environ.get("APP_URL", "http://app-ga.default.svc.cluster.local:8080"),
            label=os.environ.get("APP_LABEL", "app-ga"),
            deployment_name=os.environ.get("K8S_DEPLOYMENT_NAME", "app-ga"),
            namespace=os.environ.get("K8S_NAMESPACE", "default"),
            container_name=os.environ.get("K8S_CONTAINER_NAME", "app-ga")
        )


@dataclass
class PrometheusConfig:
    """Configuração do Prometheus."""
    url: str = "http://prometheus-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090"
    query_timeout: int = 10
    retry_attempts: int = 3
    retry_delay: float = 1.0

    @classmethod
    def from_env(cls) -> "PrometheusConfig":
        """Carrega configuração de variáveis de ambiente."""
        return cls(
            url=os.environ.get(
                "PROMETHEUS_URL",
                "http://prometheus-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090"
            ),
            query_timeout=int(os.environ.get("PROM_QUERY_TIMEOUT", "10")),
            retry_attempts=int(os.environ.get("PROM_RETRY_ATTEMPTS", "3")),
            retry_delay=float(os.environ.get("PROM_RETRY_DELAY", "1.0"))
        )


