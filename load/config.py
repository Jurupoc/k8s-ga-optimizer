# load/config.py
"""
Configuração de load test.
"""

import os
from dataclasses import dataclass


@dataclass
class LoadTestConfig:
    """Configuração de load test."""

    duration: int = 30  # seconds
    concurrency: int = 20
    timeout: int = 5  # seconds
    ramp_up: int = 0  # seconds
    profile: str = ""  # sustained, burst, ramp_up, spiky, wave (vazio = sem perfil)
    
    # Warm-up configuration
    warmup_duration: int = 5  # seconds
    warmup_concurrency: int = 2  # low concurrency during warm-up
    
    # Validation thresholds
    min_requests: int = 50  # Minimum requests for valid test
    max_error_rate: float = 0.8  # Maximum acceptable error rate (80%)

    @classmethod
    def from_env(cls) -> "LoadTestConfig":
        """Carrega configuração de variáveis de ambiente com validação."""
        duration = int(os.environ.get("LOAD_TEST_DURATION", "30"))
        concurrency = int(os.environ.get("LOAD_TEST_CONCURRENCY", "20"))
        timeout = int(os.environ.get("LOAD_TEST_TIMEOUT", "10"))
        ramp_up = int(os.environ.get("LOAD_TEST_RAMP_UP", "0"))
        profile = os.environ.get("LOAD_TEST_PROFILE", "")
        warmup_duration = int(os.environ.get("LOAD_TEST_WARMUP_DURATION", "5"))
        warmup_concurrency = int(os.environ.get("LOAD_TEST_WARMUP_CONCURRENCY", "2"))
        min_requests = int(os.environ.get("LOAD_TEST_MIN_REQUESTS", "50"))
        max_error_rate = float(os.environ.get("LOAD_TEST_MAX_ERROR_RATE", "0.8"))
        
        # Validações
        if duration < 1:
            raise ValueError(f"LOAD_TEST_DURATION deve ser >= 1, recebido: {duration}")
        if concurrency < 1:
            raise ValueError(f"LOAD_TEST_CONCURRENCY deve ser >= 1, recebido: {concurrency}")
        if timeout < 1:
            raise ValueError(f"LOAD_TEST_TIMEOUT deve ser >= 1, recebido: {timeout}")
        if warmup_duration < 0:
            raise ValueError(f"LOAD_TEST_WARMUP_DURATION deve ser >= 0, recebido: {warmup_duration}")
        if warmup_concurrency < 1:
            raise ValueError(f"LOAD_TEST_WARMUP_CONCURRENCY deve ser >= 1, recebido: {warmup_concurrency}")
        if min_requests < 1:
            raise ValueError(f"LOAD_TEST_MIN_REQUESTS deve ser >= 1, recebido: {min_requests}")
        if not 0.0 <= max_error_rate <= 1.0:
            raise ValueError(f"LOAD_TEST_MAX_ERROR_RATE deve estar entre 0.0 e 1.0, recebido: {max_error_rate}")
        
        return cls(
            duration=duration,
            concurrency=concurrency,
            timeout=timeout,
            ramp_up=ramp_up,
            profile=profile,
            warmup_duration=warmup_duration,
            warmup_concurrency=warmup_concurrency,
            min_requests=min_requests,
            max_error_rate=max_error_rate,
        )
