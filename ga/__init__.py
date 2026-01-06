# ga/__init__.py
"""
Pacote GA para otimização de cluster Kubernetes.
Arquitetura modular e escalável.
"""

from .optimizer import GeneticOptimizer, run
from .types import Individual, FitnessMetrics, EvaluationResult, GenerationStats
from .config import GAParameters, AppConfig, PrometheusConfig
from .exceptions import (
    GAException,
    ConfigurationError,
    EvaluationError,
    KubernetesError,
    PrometheusError
)

__all__ = [
    # Main
    "GeneticOptimizer",
    "run",
    # Types
    "Individual",
    "FitnessMetrics",
    "EvaluationResult",
    "GenerationStats",
    # Config
    "GAParameters",
    "AppConfig",
    "PrometheusConfig",
    # Exceptions
    "GAException",
    "ConfigurationError",
    "EvaluationError",
    "KubernetesError",
    "PrometheusError",
]
