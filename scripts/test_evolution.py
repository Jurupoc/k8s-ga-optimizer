#!/usr/bin/env python3
"""
Script para testar a evolução da população isoladamente.
"""
import sys
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ga.population import PopulationManager
from ga.config import GAParameters
from shared.utils import log

def test_evolution():
    """Testa a evolução da população."""
    
    # Cria parâmetros
    params = GAParameters(
        population_size=5,
        mutation_rate=0.3,
        crossover_rate=0.8,
        elitism_count=1,
        tournament_size=2
    )
    
    log("=" * 80)
    log("Testing Population Evolution")
    log("=" * 80)
    log(f"Parameters:")
    log(f"  Population size: {params.population_size}")
    log(f"  Mutation rate: {params.mutation_rate}")
    log(f"  Crossover rate: {params.crossover_rate}")
    log(f"  Elitism: {params.elitism_count}")
    log("=" * 80)
    
    # Cria população inicial
    manager = PopulationManager(params)
    population = manager.create_initial_population()
    
    # Simula fitness scores (todos iguais para forçar o problema)
    fitness_scores = [0.4089] * params.population_size
    
    log("\n" + "=" * 80)
    log("Generation 0 (Initial)")
    log("=" * 80)
    for i, ind in enumerate(population.individuals):
        log(f"Individual {i+1}: {ind} → fitness={fitness_scores[i]:.4f}")
    
    # Evolui para próxima geração
    log("\n" + "=" * 80)
    log("Evolving to Generation 1...")
    log("=" * 80)
    
    new_population = manager.evolve(population, fitness_scores)
    
    log("\n" + "=" * 80)
    log("Generation 1 (After Evolution)")
    log("=" * 80)
    for i, ind in enumerate(new_population.individuals):
        log(f"Individual {i+1}: {ind}")
    
    # Verifica diversidade
    unique = set()
    for ind in new_population.individuals:
        unique.add((ind.replicas, ind.cpu_limit, ind.memory_limit))
    
    log("\n" + "=" * 80)
    log(f"Diversity Check: {len(unique)}/{len(new_population.individuals)} unique individuals")
    log("=" * 80)
    
    if len(unique) == 1:
        log("❌ FAILED: All individuals are identical!", level="error")
        return False
    else:
        log(f"✅ PASSED: {len(unique)} unique individuals", level="info")
        return True

if __name__ == "__main__":
    success = test_evolution()
    sys.exit(0 if success else 1)
