# shared/utils.py
"""
Utilitários compartilhados entre módulos.
"""

import os
import logging
import json
from typing import Any, Dict
from datetime import datetime

# Configura logger simples
LOG_LEVEL = os.environ.get("LOG_LEVEL", "DEBUG").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("app")
logger.setLevel(LOG_LEVEL)

# Silencia logs DEBUG do cliente Kubernetes
logging.getLogger("kubernetes.client.rest").setLevel(logging.WARNING)
logging.getLogger("kubernetes").setLevel(logging.WARNING)

# Silencia logs DEBUG do urllib3 (usado pelo Prometheus client)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
logging.getLogger("prometheus_api_client").setLevel(logging.WARNING)
logging.getLogger("prometheus_api_client.prometheus_connect").setLevel(logging.WARNING)


def log(*args, level: str = "info") -> None:
    """
    Função de logging unificada.

    Args:
        *args: Argumentos a serem logados (serão convertidos para string)
        level: Nível de log (debug, info, warning, error)
    """
    msg = " ".join(str(a) for a in args)
    level_lower = level.lower()

    if level_lower == "debug":
        logger.debug(msg)
    elif level_lower == "warning":
        logger.warning(msg)
    elif level_lower == "error":
        logger.error(msg)
    else:
        logger.info(msg)


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """
    Divisão segura que evita divisão por zero.

    Args:
        numerator: Numerador
        denominator: Denominador
        default: Valor padrão se denominador for zero

    Returns:
        Resultado da divisão ou default
    """
    if denominator == 0 or abs(denominator) < 1e-10:
        return default
    return numerator / denominator


def calculate_variance(values: list) -> float:
    """
    Calcula a variância de uma lista de valores.

    Args:
        values: Lista de valores numéricos

    Returns:
        Variância dos valores (0.0 se lista vazia ou com 1 elemento)
    """
    if not values or len(values) < 2:
        return 0.0
    
    mean = sum(values) / len(values)
    return sum((x - mean) ** 2 for x in values) / len(values)
