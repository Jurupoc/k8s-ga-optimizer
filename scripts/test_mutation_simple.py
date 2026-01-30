#!/usr/bin/env python3
"""Teste simples de mutação."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ga.population import PopulationManager
from ga.config import GAParameters
from ga.types import Individual

# Cria indivíduo de teste
ind = Individual(replicas=3, cpu_limit=0.28, memory_limit=879)
print(f"Original: {ind}")

# Cria manager
params = GAParameters(mutation_rate=1.0)  # 100% de chance
manager = PopulationManager(params)

# Testa mutação 10 vezes
print("\nTesting 10 mutations:")
for i in range(10):
    mutated = manager.mutate(ind, strength=0.3)
    print(f"  {i+1}. {mutated}")
    if mutated == ind:
        print(f"     [NO CHANGE]")
    else:
        print(f"     [CHANGED]")
