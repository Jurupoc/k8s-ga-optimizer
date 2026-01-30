#!/usr/bin/env python3
"""Teste simples de mutação - conta quantas mutações acontecem."""
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Desabilita logs de debug
os.environ["LOG_LEVEL"] = "ERROR"

from ga.population import PopulationManager
from ga.config import GAParameters
from ga.types import Individual

# Cria indivíduo de teste
ind = Individual(replicas=3, cpu_limit=0.28, memory_limit=879)
print(f"Original: replicas={ind.replicas}, cpu={ind.cpu_limit}, mem={ind.memory_limit}")

# Cria manager
params = GAParameters(mutation_rate=0.3)  # 30% de chance
manager = PopulationManager(params)

# Testa mutação 100 vezes
mutations = 0
for i in range(100):
    mutated = manager.mutate(ind, strength=0.3)
    if mutated != ind:
        mutations += 1

print(f"\nMutations: {mutations}/100 ({mutations}%)")
print(f"Expected: ~30% (mutation_rate=0.3)")

if mutations > 0:
    print("Result: MUTATION IS WORKING")
else:
    print("Result: MUTATION IS BROKEN")
