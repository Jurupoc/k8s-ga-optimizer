# ga/__init__.py
"""
Pacote GA para otimização de cluster Kubernetes.
Arquitetura modular e escalável.
"""

from .optimizer import GeneticOptimizer, run
from .types import Individual, FitnessMetrics, EvaluationResult, GenerationStats
from .config import GAParameters, AppConfig, PrometheusConfig, LoadTestConfig
from .exceptions import (
    GAException,
    ConfigurationError,
    EvaluationError,
    KubernetesError,
    PrometheusError,
    LoadTestError
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
    "LoadTestConfig",
    # Exceptions
    "GAException",
    "ConfigurationError",
    "EvaluationError",
    "KubernetesError",
    "PrometheusError",
    "LoadTestError",
]
