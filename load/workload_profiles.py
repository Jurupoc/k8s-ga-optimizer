# load/workload_profiles.py
"""
Perfis de carga para testes realistas.
"""
from dataclasses import dataclass
from typing import Callable, Optional
from enum import Enum


class LoadProfileType(Enum):
    """Tipos de perfis de carga."""
    SUSTAINED = "sustained"  # Carga constante
    BURST = "burst"  # Picos de carga
    RAMP_UP = "ramp_up"  # Aumento gradual
    SPIKY = "spiky"  # Cargas irregulares
    WAVE = "wave"  # Padrão de ondas


@dataclass
class WorkloadProfile:
    """
    Perfil de carga para testes.
    """
    name: str
    description: str
    duration: int  # segundos
    base_concurrency: int
    max_concurrency: int
    ramp_up_duration: int = 0  # segundos para atingir max_concurrency
    pattern_func: Optional[Callable[[float], int]] = None  # função que retorna concurrency em função do tempo

    def get_concurrency_at(self, elapsed_time: float) -> int:
        """
        Retorna a concorrência no tempo especificado.

        Args:
            elapsed_time: Tempo decorrido em segundos

        Returns:
            Número de threads concorrentes
        """
        if self.pattern_func:
            return int(self.pattern_func(elapsed_time))

        # Padrão padrão: ramp-up linear
        if elapsed_time < self.ramp_up_duration:
            # Ramp-up linear
            progress = elapsed_time / self.ramp_up_duration
            return int(self.base_concurrency + (self.max_concurrency - self.base_concurrency) * progress)
        else:
            # Mantém max_concurrency
            return self.max_concurrency


def _sustained_pattern(base: int, max_c: int) -> Callable[[float], int]:
    """Carga constante."""
    def pattern(t: float) -> int:
        return base
    return pattern


def _burst_pattern(base: int, max_c: int) -> Callable[[float], int]:
    """Picos de carga periódicos."""
    def pattern(t: float) -> int:
        cycle = t % 30  # ciclo de 30 segundos
        if 0 <= cycle < 5:
            return max_c  # pico
        elif 5 <= cycle < 10:
            return int(base * 0.5)  # queda
        else:
            return base  # normal
    return pattern


def _ramp_up_pattern(base: int, max_c: int, ramp_duration: int) -> Callable[[float], int]:
    """Aumento gradual até máximo."""
    def pattern(t: float) -> int:
        if t < ramp_duration:
            progress = t / ramp_duration
            return int(base + (max_c - base) * progress)
        return max_c
    return pattern


def _spiky_pattern(base: int, max_c: int) -> Callable[[float], int]:
    """Cargas irregulares e imprevisíveis."""
    import random
    def pattern(t: float) -> int:
        # Variação aleatória entre base e max
        variation = random.uniform(0.3, 1.0)
        return int(base + (max_c - base) * variation)
    return pattern


def _wave_pattern(base: int, max_c: int) -> Callable[[float], int]:
    """Padrão de ondas senoidais."""
    import math
    def pattern(t: float) -> int:
        # Onda senoidal com período de 20 segundos
        wave = math.sin(t * 2 * math.pi / 20)
        # Normaliza para [0, 1] e escala
        normalized = (wave + 1) / 2
        return int(base + (max_c - base) * normalized)
    return pattern


_PROFILES = {
    LoadProfileType.SUSTAINED: WorkloadProfile(
        name="sustained",
        description="Carga constante e sustentada",
        duration=60,
        base_concurrency=20,
        max_concurrency=20,
        pattern_func=_sustained_pattern(20, 20)
    ),
    LoadProfileType.BURST: WorkloadProfile(
        name="burst",
        description="Picos periódicos de carga",
        duration=90,
        base_concurrency=10,
        max_concurrency=50,
        pattern_func=_burst_pattern(10, 50)
    ),
    LoadProfileType.RAMP_UP: WorkloadProfile(
        name="ramp_up",
        description="Aumento gradual de carga",
        duration=60,
        base_concurrency=5,
        max_concurrency=40,
        ramp_up_duration=30,
        pattern_func=_ramp_up_pattern(5, 40, 30)
    ),
    LoadProfileType.SPIKY: WorkloadProfile(
        name="spiky",
        description="Cargas irregulares e variáveis",
        duration=60,
        base_concurrency=10,
        max_concurrency=60,
        pattern_func=_spiky_pattern(10, 60)
    ),
    LoadProfileType.WAVE: WorkloadProfile(
        name="wave",
        description="Padrão de ondas senoidais",
        duration=60,
        base_concurrency=5,
        max_concurrency=30,
        pattern_func=_wave_pattern(5, 30)
    )
}


def get_profile(profile_type: str) -> WorkloadProfile:
    """
    Obtém um perfil de carga.

    Args:
        profile_type: Nome do perfil (sustained, burst, ramp_up, spiky, wave)

    Returns:
        Perfil de carga

    Raises:
        ValueError: Se o perfil não existir
    """
    try:
        enum_type = LoadProfileType(profile_type.lower())
        return _PROFILES[enum_type]
    except (ValueError, KeyError):
        raise ValueError(f"Unknown profile: {profile_type}. Available: {[p.value for p in LoadProfileType]}")


def list_profiles() -> list[str]:
    """Lista todos os perfis disponíveis."""
    return [p.value for p in LoadProfileType]


