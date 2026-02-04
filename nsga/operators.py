"""
Operadores genéticos: crossover, mutação e repair.
"""
import random
from nsga.domain import Genome
from nsga.search_space import SearchSpace


def uniform_crossover(parent1: Genome, parent2: Genome, rng: random.Random) -> tuple[Genome, Genome]:
    """
    Crossover uniforme: cada gene é escolhido de um dos pais com 50% de chance.
    
    Args:
        parent1: Primeiro pai
        parent2: Segundo pai
        rng: Gerador de números aleatórios
        
    Returns:
        Tupla com dois filhos
    """
    # Filho 1
    cpu1 = parent1.cpu_m if rng.random() < 0.5 else parent2.cpu_m
    mem1 = parent1.mem_mib if rng.random() < 0.5 else parent2.mem_mib
    rep1 = parent1.replicas if rng.random() < 0.5 else parent2.replicas
    child1 = Genome(cpu_m=cpu1, mem_mib=mem1, replicas=rep1)
    
    # Filho 2
    cpu2 = parent2.cpu_m if rng.random() < 0.5 else parent1.cpu_m
    mem2 = parent2.mem_mib if rng.random() < 0.5 else parent1.mem_mib
    rep2 = parent2.replicas if rng.random() < 0.5 else parent1.replicas
    child2 = Genome(cpu_m=cpu2, mem_mib=mem2, replicas=rep2)
    
    return child1, child2


def mutate(genome: Genome, space: SearchSpace, pm: float, rng: random.Random) -> Genome:
    """
    Mutação por gene com probabilidade pm.
    
    - cpu_m: +/- step com prob pm
    - mem_mib: +/- step com prob pm
    - replicas: +/-1 com prob pm
    
    Args:
        genome: Genome a ser mutado
        space: Espaço de busca com limites
        pm: Probabilidade de mutação por gene
        rng: Gerador de números aleatórios
        
    Returns:
        Genome mutado (pode ser igual ao original se nenhuma mutação ocorreu)
    """
    cpu_m = genome.cpu_m
    mem_mib = genome.mem_mib
    replicas = genome.replicas
    
    # Mutar CPU
    if rng.random() < pm:
        delta = space.cpu_step if rng.random() < 0.5 else -space.cpu_step
        cpu_m += delta
    
    # Mutar memória
    if rng.random() < pm:
        delta = space.mem_step if rng.random() < 0.5 else -space.mem_step
        mem_mib += delta
    
    # Mutar réplicas
    if rng.random() < pm:
        delta = 1 if rng.random() < 0.5 else -1
        replicas += delta
    
    # Criar genome mutado (será reparado depois)
    return Genome(cpu_m=cpu_m, mem_mib=mem_mib, replicas=replicas)


def repair(genome: Genome, space: SearchSpace) -> Genome:
    """
    Repara um genome para garantir que está dentro dos limites.
    Wrapper para SearchSpace.repair().
    
    Args:
        genome: Genome a ser reparado
        space: Espaço de busca com limites
        
    Returns:
        Genome reparado
    """
    return space.repair(genome)


def crossover_and_mutate(
    parent1: Genome,
    parent2: Genome,
    space: SearchSpace,
    pc: float,
    pm: float,
    rng: random.Random
) -> tuple[Genome, Genome]:
    """
    Aplica crossover (com probabilidade pc) e mutação (com probabilidade pm por gene).
    
    Args:
        parent1: Primeiro pai
        parent2: Segundo pai
        space: Espaço de busca
        pc: Probabilidade de crossover
        pm: Probabilidade de mutação por gene
        rng: Gerador de números aleatórios
        
    Returns:
        Tupla com dois filhos (reparados)
    """
    # Crossover
    if rng.random() < pc:
        child1, child2 = uniform_crossover(parent1, parent2, rng)
    else:
        # Sem crossover, filhos são cópias dos pais
        child1 = Genome(parent1.cpu_m, parent1.mem_mib, parent1.replicas)
        child2 = Genome(parent2.cpu_m, parent2.mem_mib, parent2.replicas)
    
    # Mutação
    child1 = mutate(child1, space, pm, rng)
    child2 = mutate(child2, space, pm, rng)
    
    # Repair
    child1 = repair(child1, space)
    child2 = repair(child2, space)
    
    return child1, child2
