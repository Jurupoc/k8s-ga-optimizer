# ga/utils.py
"""
Utilitários gerais para o módulo GA.
"""
import os
import logging
import json
from typing import Any, Dict, Optional
from datetime import datetime

# Configura logger simples
LOG_LEVEL = os.environ.get("GA_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("ga")


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


def format_dict(d: Dict[str, Any], indent: int = 2) -> str:
    """
    Formata um dicionário para exibição legível.

    Args:
        d: Dicionário a ser formatado
        indent: Nível de indentação

    Returns:
        String formatada
    """
    return json.dumps(d, indent=indent, ensure_ascii=False)


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


def clamp(value: float, min_val: float, max_val: float) -> float:
    """
    Limita um valor entre min e max.

    Args:
        value: Valor a ser limitado
        min_val: Valor mínimo
        max_val: Valor máximo

    Returns:
        Valor limitado
    """
    return max(min_val, min(max_val, value))


def format_duration(seconds: float) -> str:
    """
    Formata duração em segundos para string legível.

    Args:
        seconds: Duração em segundos

    Returns:
        String formatada (ex: "1h 23m 45s")
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours}h {minutes}m {secs}s"


def get_timestamp() -> str:
    """
    Retorna timestamp formatado.

    Returns:
        String com timestamp (YYYY-MM-DD HH:MM:SS)
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
