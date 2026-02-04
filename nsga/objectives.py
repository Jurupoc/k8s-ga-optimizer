"""
Cálculo de objetivos a partir de métricas cruas e genome.
"""
from nsga.domain import Genome, RawMetrics, Objectives


def calculate_objectives(genome: Genome, metrics: RawMetrics) -> Objectives:
    """
    Calcula os três objetivos a partir do genome e métricas.
    
    Objetivos (todos para minimização):
    - f1: Saturação = 0.5 * cpu_throttle_rate + 0.5 * mem_peak_ratio
    - f2: Recursos provisionados = replicas * (cpu_cores + mem_gib)
    - f3: -throughput (negativo para minimizar)
    
    Args:
        genome: Configuração de recursos
        metrics: Métricas cruas do Prometheus
        
    Returns:
        Objectives calculados
    """
    # f1: saturação (combinação de CPU throttle e memory peak)
    f1 = 0.5 * metrics.cpu_throttle_rate + 0.5 * metrics.mem_peak_ratio
    
    # f2: recursos provisionados (CPU em cores + MEM em GiB)
    cpu_cores = genome.cpu_m / 1000.0
    mem_gib = genome.mem_mib / 1024.0
    f2 = genome.replicas * (cpu_cores + mem_gib)
    
    # f3: negativo do throughput (para minimização)
    f3 = -metrics.throughput_rps
    
    return Objectives(f1=f1, f2=f2, f3=f3)


def penalty_objectives(genome: Genome) -> Objectives:
    """
    Retorna objetivos com penalidade para avaliações que falharam.
    
    Penalidades:
    - f1: 10.0 (muito alto, pior saturação)
    - f2: calculado normalmente (recursos provisionados)
    - f3: 0.0 (throughput zero, pior possível)
    
    Args:
        genome: Configuração de recursos
        
    Returns:
        Objectives com penalidade
    """
    # f1: penalidade alta para saturação
    f1 = 10.0
    
    # f2: calculado normalmente (recursos foram provisionados)
    cpu_cores = genome.cpu_m / 1000.0
    mem_gib = genome.mem_mib / 1024.0
    f2 = genome.replicas * (cpu_cores + mem_gib)
    
    # f3: throughput zero (pior caso)
    f3 = 0.0
    
    return Objectives(f1=f1, f2=f2, f3=f3)
