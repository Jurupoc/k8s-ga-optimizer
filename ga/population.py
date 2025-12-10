# ga/population.py
"""
Gerenciamento de população do algoritmo genético.
Inclui inicialização, seleção, crossover e mutação.
"""
import random
import copy
from typing import List, Tuple, Optional
from dataclasses import dataclass

from ga.types import Individual
from ga.config import GAParameters
from ga.exceptions import ConfigurationError
from ga.utils import log


@dataclass
class Population:
    """Representa uma população de indivíduos."""
    individuals: List[Individual]
    generation: int = 0

    def size(self) -> int:
        """Retorna o tamanho da população."""
        return len(self.individuals)

    def get_best(self, fitness_scores: List[float]) -> Tuple[Individual, float]:
        """
        Retorna o melhor indivíduo e seu score.

        Args:
            fitness_scores: Lista de scores correspondentes

        Returns:
            Tupla (melhor indivíduo, melhor score)
        """
        if not self.individuals or not fitness_scores:
            raise ValueError("Empty population or scores")

        best_idx = max(range(len(fitness_scores)), key=lambda i: fitness_scores[i])
        return self.individuals[best_idx], fitness_scores[best_idx]

    def get_diversity(self) -> float:
        """
        Calcula diversidade da população (variação dos parâmetros).

        Returns:
            Medida de diversidade (0.0 a 1.0)
        """
        if len(self.individuals) < 2:
            return 0.0

        # Calcula variância normalizada dos parâmetros
        replicas = [ind.replicas for ind in self.individuals]
        cpu_limits = [ind.cpu_limit for ind in self.individuals]
        mem_limits = [ind.memory_limit for ind in self.individuals]

        def variance(values):
            if not values:
                return 0.0
            mean = sum(values) / len(values)
            return sum((x - mean) ** 2 for x in values) / len(values)

        # Normaliza variâncias
        max_range = {
            'replicas': (1, 6),
            'cpu': (0.1, 2.0),
            'mem': (128, 1024)
        }

        var_replicas = variance(replicas) / ((max_range['replicas'][1] - max_range['replicas'][0]) ** 2)
        var_cpu = variance(cpu_limits) / ((max_range['cpu'][1] - max_range['cpu'][0]) ** 2)
        var_mem = variance(mem_limits) / ((max_range['mem'][1] - max_range['mem'][0]) ** 2)

        # Média das variâncias normalizadas
        diversity = (var_replicas + var_cpu + var_mem) / 3.0
        return min(1.0, diversity)


class PopulationManager:
    """
    Gerencia população do GA: criação, seleção, crossover, mutação.
    """

    def __init__(self, params: Optional[GAParameters] = None):
        """
        Inicializa o gerenciador de população.

        Args:
            params: Parâmetros do GA (default: carrega de env)
        """
        self.params = params or GAParameters.from_env()

    def create_random_individual(self) -> Individual:
        """
        Cria um indivíduo aleatório dentro dos limites.

        Returns:
            Indivíduo aleatório
        """
        return Individual(
            replicas=random.randint(*self.params.replicas_bounds),
            cpu_limit=round(random.uniform(*self.params.cpu_limit_bounds), 2),
            memory_limit=random.randint(*self.params.memory_limit_bounds)
        )

    def create_initial_population(self, size: Optional[int] = None) -> Population:
        """
        Cria população inicial aleatória.

        Args:
            size: Tamanho da população (usa params se None)

        Returns:
            População inicial
        """
        size = size or self.params.population_size
        individuals = [self.create_random_individual() for _ in range(size)]
        log(f"Created initial population of {size} individuals")
        return Population(individuals=individuals, generation=0)

    def validate_individual(self, individual: Individual) -> Individual:
        """
        Valida e corrige um indivíduo para garantir limites.

        Args:
            individual: Indivíduo a validar

        Returns:
            Indivíduo validado (nova cópia)
        """
        validated = copy.deepcopy(individual)

        validated.replicas = max(
            self.params.replicas_bounds[0],
            min(self.params.replicas_bounds[1], validated.replicas)
        )
        validated.cpu_limit = round(
            max(
                self.params.cpu_limit_bounds[0],
                min(self.params.cpu_limit_bounds[1], validated.cpu_limit)
            ),
            2
        )
        validated.memory_limit = max(
            self.params.memory_limit_bounds[0],
            min(self.params.memory_limit_bounds[1], validated.memory_limit)
        )

        return validated

    def mutate(self, individual: Individual, strength: float = 0.1) -> Individual:
        """
        Aplica mutação em um indivíduo.

        Args:
            individual: Indivíduo a mutar
            strength: Força da mutação (0.0 a 1.0)

        Returns:
            Indivíduo mutado (nova cópia)
        """
        if random.random() > self.params.mutation_rate:
            return copy.deepcopy(individual)

        mutated = copy.deepcopy(individual)

        # Escolhe parâmetro aleatório para mutar
        param = random.choice(["replicas", "cpu_limit", "memory_limit"])

        if param == "replicas":
            min_val, max_val = self.params.replicas_bounds
            range_size = max_val - min_val
            delta = random.randint(-int(range_size * strength), int(range_size * strength))
            mutated.replicas = max(min_val, min(max_val, mutated.replicas + delta))

        elif param == "cpu_limit":
            min_val, max_val = self.params.cpu_limit_bounds
            range_size = max_val - min_val
            # Mutação gaussiana para valores contínuos
            delta = random.gauss(0, range_size * strength)
            mutated.cpu_limit = round(max(min_val, min(max_val, mutated.cpu_limit + delta)), 2)

        else:  # memory_limit
            min_val, max_val = self.params.memory_limit_bounds
            range_size = max_val - min_val
            delta = random.randint(-int(range_size * strength), int(range_size * strength))
            mutated.memory_limit = max(min_val, min(max_val, mutated.memory_limit + delta))

        return self.validate_individual(mutated)

    def crossover(self, parent1: Individual, parent2: Individual) -> Individual:
        """
        Realiza crossover entre dois pais.

        Args:
            parent1: Primeiro pai
            parent2: Segundo pai

        Returns:
            Filho gerado
        """
        if random.random() > self.params.crossover_rate:
            # Sem crossover: retorna cópia de um dos pais
            return copy.deepcopy(random.choice([parent1, parent2]))

        child = Individual(
            replicas=0,
            cpu_limit=0.0,
            memory_limit=0
        )

        # Réplicas: escolha aleatória ou média arredondada
        if random.random() < 0.5:
            child.replicas = random.choice([parent1.replicas, parent2.replicas])
        else:
            child.replicas = int(round((parent1.replicas + parent2.replicas) / 2))

        # CPU: média ponderada
        alpha = random.uniform(0.3, 0.7)
        child.cpu_limit = round(
            alpha * parent1.cpu_limit + (1 - alpha) * parent2.cpu_limit,
            2
        )

        # Memória: escolha aleatória ou média arredondada
        if random.random() < 0.5:
            child.memory_limit = random.choice([parent1.memory_limit, parent2.memory_limit])
        else:
            child.memory_limit = int(round((parent1.memory_limit + parent2.memory_limit) / 2))

        return self.validate_individual(child)

    def tournament_select(
        self,
        population: Population,
        fitness_scores: List[float],
        tournament_size: Optional[int] = None
    ) -> Individual:
        """
        Seleção por torneio.

        Args:
            population: População
            fitness_scores: Scores de fitness
            tournament_size: Tamanho do torneio (usa params se None)

        Returns:
            Indivíduo selecionado
        """
        tournament_size = tournament_size or self.params.tournament_size

        if len(population.individuals) < tournament_size:
            tournament_size = len(population.individuals)

        # Seleciona participantes aleatórios
        indices = random.sample(range(len(population.individuals)), tournament_size)
        tournament = [(population.individuals[i], fitness_scores[i]) for i in indices]

        # Retorna o melhor do torneio
        return max(tournament, key=lambda x: x[1])[0]

    def select_parents(
        self,
        population: Population,
        fitness_scores: List[float]
    ) -> Tuple[Individual, Individual]:
        """
        Seleciona dois pais para crossover.

        Args:
            population: População
            fitness_scores: Scores de fitness

        Returns:
            Tupla com dois pais
        """
        parent1 = self.tournament_select(population, fitness_scores)
        parent2 = self.tournament_select(population, fitness_scores)

        # Garante que são diferentes
        attempts = 0
        while parent1 == parent2 and len(population.individuals) > 1 and attempts < 10:
            parent2 = self.tournament_select(population, fitness_scores)
            attempts += 1

        return parent1, parent2

    def evolve(
        self,
        population: Population,
        fitness_scores: List[float],
        elite_count: Optional[int] = None
    ) -> Population:
        """
        Evolui a população para a próxima geração.

        Args:
            population: População atual
            fitness_scores: Scores de fitness
            elite_count: Número de elite a manter (usa params se None)

        Returns:
            Nova população
        """
        elite_count = elite_count or self.params.elitism_count

        # Ordena por fitness (decrescente)
        sorted_pop = sorted(
            zip(population.individuals, fitness_scores),
            key=lambda x: x[1],
            reverse=True
        )

        # Mantém elite
        elite = [ind for ind, _ in sorted_pop[:elite_count]]

        # Seleciona sobreviventes (metade da população)
        survivor_count = max(1, len(population.individuals) // 2)
        survivors = [ind for ind, _ in sorted_pop[:survivor_count]]
        survivor_scores = [score for _, score in sorted_pop[:survivor_count]]

        # Cria população temporária para seleção
        survivor_pop = Population(individuals=survivors)

        # Gera filhos
        children = []
        while len(children) < len(population.individuals) - len(elite):
            parent1, parent2 = self.select_parents(survivor_pop, survivor_scores)
            child = self.crossover(parent1, parent2)
            child = self.mutate(child)
            children.append(child)

        # Nova população = elite + filhos
        new_individuals = elite + children
        new_population = Population(
            individuals=new_individuals,
            generation=population.generation + 1
        )

        log(f"Evolved population: {len(elite)} elite + {len(children)} children")

        return new_population


