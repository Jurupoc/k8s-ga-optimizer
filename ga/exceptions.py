# ga/exceptions.py
"""
Exceções customizadas para o módulo GA.
"""


class GAException(Exception):
    """Exceção base para erros do GA."""
    pass


class ConfigurationError(GAException):
    """Erro relacionado a configuração inválida."""
    pass


class EvaluationError(GAException):
    """Erro durante avaliação de fitness."""
    pass


class KubernetesError(GAException):
    """Erro relacionado a operações no Kubernetes."""
    pass


class PrometheusError(GAException):
    """Erro relacionado a consultas no Prometheus."""
    pass


class LoadTestError(GAException):
    """Erro durante execução de load test."""
    pass


