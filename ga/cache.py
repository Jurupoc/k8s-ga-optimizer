# ga/cache.py
"""
Sistema de cache para resultados de avaliação.
Evita reavaliar configurações idênticas.
"""
import time
import hashlib
import json
from typing import Dict, Optional, Tuple
from functools import lru_cache

from ga.types import Individual, EvaluationResult
from shared.utils import log


class EvaluationCache:
    """
    Cache de resultados de avaliação.
    """

    def __init__(self, ttl: float = 3600.0):
        """
        Inicializa o cache.

        Args:
            ttl: Time-to-live em segundos (default: 1 hora)
        """
        self.cache: Dict[str, Tuple[float, EvaluationResult]] = {}
        self.ttl = ttl

    def _get_key(self, individual: Individual) -> str:
        """
        Gera chave única para um indivíduo.

        Args:
            individual: Indivíduo

        Returns:
            Chave hash
        """
        data = json.dumps(individual.to_dict(), sort_keys=True)
        return hashlib.md5(data.encode()).hexdigest()

    def get(self, individual: Individual) -> Optional[EvaluationResult]:
        """
        Obtém resultado do cache se disponível e válido.

        Args:
            individual: Indivíduo a buscar

        Returns:
            Resultado em cache ou None
        """
        key = self._get_key(individual)

        if key in self.cache:
            timestamp, result = self.cache[key]
            if time.time() - timestamp < self.ttl:
                log(f"Cache hit for individual: {individual}", level="debug")
                return result
            else:
                # Expirou
                del self.cache[key]

        return None

    def put(self, individual: Individual, result: EvaluationResult) -> None:
        """
        Armazena resultado no cache.

        Args:
            individual: Indivíduo
            result: Resultado da avaliação
        """
        key = self._get_key(individual)
        self.cache[key] = (time.time(), result)
        log(f"Cached result for individual: {individual}", level="debug")

    def clear(self) -> None:
        """Limpa o cache."""
        self.cache.clear()
        log("Cache cleared")

    def size(self) -> int:
        """Retorna tamanho do cache."""
        return len(self.cache)

    def cleanup_expired(self) -> int:
        """
        Remove entradas expiradas.

        Returns:
            Número de entradas removidas
        """
        now = time.time()
        expired_keys = [
            key for key, (timestamp, _) in self.cache.items()
            if now - timestamp >= self.ttl
        ]

        for key in expired_keys:
            del self.cache[key]

        if expired_keys:
            log(f"Cleaned up {len(expired_keys)} expired cache entries")

        return len(expired_keys)


