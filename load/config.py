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
    profile: str = "sustained"  # sustained, burst, ramp-up

    @classmethod
    def from_env(cls) -> "LoadTestConfig":
        """Carrega configuração de variáveis de ambiente."""
        return cls(
            duration=int(os.environ.get("LOAD_TEST_DURATION", "30")),
            concurrency=int(os.environ.get("LOAD_TEST_CONCURRENCY", "20")),
            timeout=int(os.environ.get("LOAD_TEST_TIMEOUT", "10")),
            ramp_up=int(os.environ.get("LOAD_TEST_RAMP_UP", "0")),
            profile=os.environ.get("LOAD_TEST_PROFILE", "sustained")
        )

