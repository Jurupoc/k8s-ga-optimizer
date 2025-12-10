# ga/types.py
"""
Tipos de dados e modelos para o GA.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime


@dataclass
class Individual:
    """
    Representa um indivíduo (configuração) do algoritmo genético.
    """
    replicas: int
    cpu_limit: float  # cores
    memory_limit: int  # MB
    container_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        result = {
            "replicas": self.replicas,
            "cpu_limit": self.cpu_limit,
            "memory_limit": self.memory_limit
        }
        if self.container_name:
            result["container_name"] = self.container_name
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Individual":
        """Cria a partir de um dicionário."""
        return cls(
            replicas=int(data.get("replicas", 1)),
            cpu_limit=float(data.get("cpu_limit", 0.5)),
            memory_limit=int(data.get("memory_limit", 256)),
            container_name=data.get("container_name")
        )

    def __hash__(self):
        """Permite usar como chave de dicionário."""
        return hash((self.replicas, self.cpu_limit, self.memory_limit))

    def __eq__(self, other):
        """Comparação de igualdade."""
        if not isinstance(other, Individual):
            return False
        return (self.replicas == other.replicas and
                self.cpu_limit == other.cpu_limit and
                self.memory_limit == other.memory_limit)


@dataclass
class FitnessMetrics:
    """
    Métricas coletadas para cálculo de fitness.
    """
    # Load test metrics
    throughput: float = 0.0  # req/s
    avg_latency: float = 0.0  # seconds
    p95_latency: float = 0.0  # seconds
    p99_latency: float = 0.0  # seconds
    success_rate: float = 0.0  # 0.0-1.0
    total_requests: int = 0
    failed_requests: int = 0

    # Resource metrics
    cpu_usage: float = 0.0  # cores
    memory_usage: float = 0.0  # bytes
    cpu_utilization: float = 0.0  # 0.0-1.0 (usage/limit)
    memory_utilization: float = 0.0  # 0.0-1.0 (usage/limit)

    # Application metrics
    request_rate: float = 0.0  # req/s
    error_rate: float = 0.0  # errors/s

    # Timestamps
    evaluated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "throughput": self.throughput,
            "avg_latency": self.avg_latency,
            "p95_latency": self.p95_latency,
            "p99_latency": self.p99_latency,
            "success_rate": self.success_rate,
            "total_requests": self.total_requests,
            "failed_requests": self.failed_requests,
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
            "cpu_utilization": self.cpu_utilization,
            "memory_utilization": self.memory_utilization,
            "request_rate": self.request_rate,
            "error_rate": self.error_rate,
            "evaluated_at": self.evaluated_at.isoformat()
        }


@dataclass
class EvaluationResult:
    """
    Resultado completo de uma avaliação.
    """
    individual: Individual
    fitness: float
    metrics: FitnessMetrics
    evaluation_time: float = 0.0  # seconds
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "individual": self.individual.to_dict(),
            "fitness": self.fitness,
            "metrics": self.metrics.to_dict(),
            "evaluation_time": self.evaluation_time,
            "error": self.error
        }


@dataclass
class GenerationStats:
    """
    Estatísticas de uma geração do GA.
    """
    generation: int
    population_size: int
    avg_fitness: float
    max_fitness: float
    min_fitness: float
    best_individual: Individual
    diversity: float = 0.0  # medida de diversidade da população
    convergence: float = 0.0  # medida de convergência

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "generation": self.generation,
            "population_size": self.population_size,
            "avg_fitness": self.avg_fitness,
            "max_fitness": self.max_fitness,
            "min_fitness": self.min_fitness,
            "best_individual": self.best_individual.to_dict(),
            "diversity": self.diversity,
            "convergence": self.convergence
        }


