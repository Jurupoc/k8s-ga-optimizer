"""
Tipos e classes de domínio para o NSGA-II.
"""
from dataclasses import dataclass
from enum import Enum


class EvaluationStatus(Enum):
    """Status da avaliação de um indivíduo."""
    OK = "ok"
    FAIL = "fail"
    TIMEOUT = "timeout"


@dataclass
class Genome:
    """
    Representa a configuração de recursos de um deployment.
    
    Attributes:
        cpu_m: CPU em millicores (int)
        mem_mib: Memória em MiB (int)
        replicas: Número de réplicas (int)
    """
    cpu_m: int
    mem_mib: int
    replicas: int
    
    def __hash__(self) -> int:
        """Hash para uso em cache."""
        return hash((self.cpu_m, self.mem_mib, self.replicas))
    
    def __eq__(self, other) -> bool:
        """Igualdade para comparação."""
        if not isinstance(other, Genome):
            return False
        return (self.cpu_m == other.cpu_m and 
                self.mem_mib == other.mem_mib and 
                self.replicas == other.replicas)
    
    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "cpu_m": self.cpu_m,
            "mem_mib": self.mem_mib,
            "replicas": self.replicas
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Genome":
        """Cria Genome a partir de dicionário."""
        return cls(
            cpu_m=data["cpu_m"],
            mem_mib=data["mem_mib"],
            replicas=data["replicas"]
        )


@dataclass
class RawMetrics:
    """
    Métricas cruas coletadas do Prometheus.
    
    Attributes:
        throughput_rps: Requisições por segundo
        cpu_throttle_rate: Taxa de throttling de CPU (0..1)
        mem_peak_ratio: Razão entre pico e limite de memória (0..1)
    """
    throughput_rps: float
    cpu_throttle_rate: float
    mem_peak_ratio: float
    
    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "throughput_rps": self.throughput_rps,
            "cpu_throttle_rate": self.cpu_throttle_rate,
            "mem_peak_ratio": self.mem_peak_ratio
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "RawMetrics":
        """Cria RawMetrics a partir de dicionário."""
        return cls(
            throughput_rps=data["throughput_rps"],
            cpu_throttle_rate=data["cpu_throttle_rate"],
            mem_peak_ratio=data["mem_peak_ratio"]
        )


@dataclass
class Objectives:
    """
    Objetivos calculados (todos para minimização).
    
    Attributes:
        f1: Saturação (combinação de CPU throttle e mem peak)
        f2: Recursos provisionados
        f3: Negativo do throughput (para minimização)
    """
    f1: float  # saturação
    f2: float  # recursos provisionados
    f3: float  # -throughput
    
    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {"f1": self.f1, "f2": self.f2, "f3": self.f3}
    
    @classmethod
    def from_dict(cls, data: dict) -> "Objectives":
        """Cria Objectives a partir de dicionário."""
        return cls(f1=data["f1"], f2=data["f2"], f3=data["f3"])


@dataclass
class EvaluationResult:
    """
    Resultado completo de uma avaliação.
    
    Attributes:
        genome: Configuração avaliada
        status: Status da avaliação
        raw_metrics: Métricas cruas (None se FAIL/TIMEOUT)
        objectives: Objetivos calculados (com penalidade se FAIL/TIMEOUT)
        eval_time_s: Tempo de avaliação em segundos
    """
    genome: Genome
    status: EvaluationStatus
    raw_metrics: RawMetrics | None
    objectives: Objectives
    eval_time_s: float
    
    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "genome": self.genome.to_dict(),
            "status": self.status.value,
            "raw_metrics": self.raw_metrics.to_dict() if self.raw_metrics else None,
            "objectives": self.objectives.to_dict(),
            "eval_time_s": self.eval_time_s
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "EvaluationResult":
        """Cria EvaluationResult a partir de dicionário."""
        return cls(
            genome=Genome.from_dict(data["genome"]),
            status=EvaluationStatus(data["status"]),
            raw_metrics=RawMetrics.from_dict(data["raw_metrics"]) if data["raw_metrics"] else None,
            objectives=Objectives.from_dict(data["objectives"]),
            eval_time_s=data["eval_time_s"]
        )


@dataclass
class Individual:
    """
    Indivíduo na população com informações de NSGA-II.
    
    Attributes:
        genome: Configuração de recursos
        objectives: Objetivos calculados
        rank: Rank da frente de Pareto (0 = melhor)
        crowding_distance: Distância de crowding
        eval_result: Resultado completo da avaliação
    """
    genome: Genome
    objectives: Objectives
    rank: int = -1
    crowding_distance: float = 0.0
    eval_result: EvaluationResult | None = None
    
    def dominates(self, other: "Individual") -> bool:
        """
        Verifica se este indivíduo domina outro (minimização).
        Domina se é melhor ou igual em todos os objetivos e estritamente melhor em pelo menos um.
        """
        better_in_any = False
        obj_self = [self.objectives.f1, self.objectives.f2, self.objectives.f3]
        obj_other = [other.objectives.f1, other.objectives.f2, other.objectives.f3]
        
        for s, o in zip(obj_self, obj_other):
            if s > o:  # pior em algum objetivo
                return False
            if s < o:  # melhor em algum objetivo
                better_in_any = True
        
        return better_in_any
    
    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "genome": self.genome.to_dict(),
            "objectives": self.objectives.to_dict(),
            "rank": self.rank,
            "crowding_distance": self.crowding_distance,
            "status": self.eval_result.status.value if self.eval_result else None,
            "eval_time_s": self.eval_result.eval_time_s if self.eval_result else None
        }
