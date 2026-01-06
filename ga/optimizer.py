# ga/optimizer.py
"""
Executor principal do Algoritmo Genético refatorado.
Usa módulos modulares: population, fitness, cache, etc.
"""
import time
import concurrent.futures
from typing import List, Optional, Dict, Any
from datetime import datetime

from ga.types import Individual, GenerationStats, EvaluationResult
from ga.config import GAParameters, AppConfig
from ga.population import PopulationManager, Population
from ga.fitness import FitnessEvaluator, FitnessCalculator
from ga.cache import EvaluationCache
from integrations.prometheus_client import PrometheusClient
from integrations.k8s_client import KubernetesClient
from load.load_test import LoadTester
from load.config import LoadTestConfig
from shared.utils import log
from ga.exceptions import GAException


class GeneticOptimizer:
    """
    Otimizador genético.
    """

    def __init__(
        self,
        params: Optional[GAParameters] = None,
        app_config: Optional[AppConfig] = None,
        parallel_evaluations: bool = False,
        max_workers: int = 2
    ):
        """
        Inicializa o otimizador.

        Args:
            params: Parâmetros do GA
            app_config: Configuração da aplicação
            parallel_evaluations: Se True, avalia em paralelo
            max_workers: Número máximo de workers paralelos
        """
        self.params = params or GAParameters.from_env()
        self.app_config = app_config or AppConfig.from_env()
        self.parallel_evaluations = parallel_evaluations
        self.max_workers = max_workers

        # Inicializa componentes
        self.pop_manager = PopulationManager(self.params)
        self.prometheus = PrometheusClient()
        self.k8s = KubernetesClient(self.app_config)
        self.load_tester = LoadTester()
        self.fitness_calc = FitnessCalculator()
        self.evaluator = FitnessEvaluator(
            self.prometheus,
            self.k8s,
            self.load_tester,
            self.app_config,
            self.fitness_calc
        )
        self.cache = EvaluationCache(ttl=3600.0)

        # Histórico
        self.history: List[GenerationStats] = []
        self.evaluation_results: List[EvaluationResult] = []

    def _evaluate_individual(self, individual: Individual) -> EvaluationResult:
        """
        Avalia um indivíduo (com cache).

        Args:
            individual: Indivíduo a avaliar

        Returns:
            Resultado da avaliação
        """
        # Verifica cache
        cached = self.cache.get(individual)
        if cached:
            return cached

        # Avalia
        import time as time_module
        start_time = time_module.time()

        try:
            fitness, metrics = self.evaluator.evaluate(individual)
            evaluation_time = time_module.time() - start_time

            result = EvaluationResult(
                individual=individual,
                fitness=fitness,
                metrics=metrics,
                evaluation_time=evaluation_time
            )

            # Armazena no cache
            self.cache.put(individual, result)

            return result

        except Exception as e:
            log(f"Evaluation failed for {individual}: {e}", level="error")
            return EvaluationResult(
                individual=individual,
                fitness=0.0,
                metrics=None,
                evaluation_time=time_module.time() - start_time,
                error=str(e)
            )

    def _evaluate_population(
        self,
        population: Population
    ) -> List[EvaluationResult]:
        """
        Avalia toda a população.

        Args:
            population: População a avaliar

        Returns:
            Lista de resultados
        """
        if self.parallel_evaluations and len(population.individuals) > 1:
            # Avaliação paralela (limitada para evitar sobrecarga do cluster)
            log(f"Evaluating {len(population.individuals)} individuals in parallel (max {self.max_workers} workers)")

            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(self._evaluate_individual, ind): ind
                    for ind in population.individuals
                }

                results = []
                for future in concurrent.futures.as_completed(futures):
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        ind = futures[future]
                        log(f"Parallel evaluation failed for {ind}: {e}", level="error")
                        results.append(EvaluationResult(
                            individual=ind,
                            fitness=0.0,
                            metrics=None,
                            error=str(e)
                        ))

            # Ordena resultados na mesma ordem dos indivíduos
            result_map = {r.individual: r for r in results}
            return [result_map[ind] for ind in population.individuals]
        else:
            # Avaliação sequencial
            results = []
            for idx, individual in enumerate(population.individuals):
                log(f"Evaluating individual {idx+1}/{len(population.individuals)}: {individual}")
                result = self._evaluate_individual(individual)
                results.append(result)

            return results

    def _calculate_generation_stats(
        self,
        population: Population,
        results: List[EvaluationResult]
    ) -> GenerationStats:
        """
        Calcula estatísticas da geração.

        Args:
            population: População
            results: Resultados de avaliação

        Returns:
            Estatísticas da geração
        """
        fitness_scores = [r.fitness for r in results]

        if not fitness_scores:
            raise GAException("No fitness scores available")

        avg_fitness = sum(fitness_scores) / len(fitness_scores)
        max_fitness = max(fitness_scores)
        min_fitness = min(fitness_scores)

        # Melhor indivíduo
        best_idx = max(range(len(fitness_scores)), key=lambda i: fitness_scores[i])
        best_individual = results[best_idx].individual

        # Diversidade
        diversity = population.get_diversity()

        # Convergência (variação dos scores)
        if len(fitness_scores) > 1:
            variance = sum((s - avg_fitness) ** 2 for s in fitness_scores) / len(fitness_scores)
            convergence = 1.0 / (1.0 + variance)  # menor variância = maior convergência
        else:
            convergence = 0.0

        return GenerationStats(
            generation=population.generation,
            population_size=len(population.individuals),
            avg_fitness=avg_fitness,
            max_fitness=max_fitness,
            min_fitness=min_fitness,
            best_individual=best_individual,
            diversity=diversity,
            convergence=convergence
        )

    def run(self) -> Individual:
        """
        Executa o algoritmo genético completo.

        Returns:
            Melhor indivíduo encontrado
        """
        log("=" * 80)
        log("Starting Genetic Algorithm Optimizer")
        log(f"Population size: {self.params.population_size}")
        log(f"Generations: {self.params.generations}")
        log(f"Mutation rate: {self.params.mutation_rate}")
        log(f"Crossover rate: {self.params.crossover_rate}")
        log(f"Elitism: {self.params.elitism_count}")
        log(f"Parallel evaluations: {self.parallel_evaluations}")
        log("=" * 80)

        # Cria população inicial
        population = self.pop_manager.create_initial_population()

        best_individual: Optional[Individual] = None
        best_fitness = float("-inf")

        # Loop de gerações
        for gen in range(self.params.generations):
            log(f"\n{'=' * 80}")
            log(f"Generation {population.generation + 1}/{self.params.generations}")
            log(f"{'=' * 80}")

            # Avalia população
            results = self._evaluate_population(population)
            self.evaluation_results.extend(results)

            # Calcula estatísticas
            stats = self._calculate_generation_stats(population, results)
            self.history.append(stats)

            # Atualiza melhor global
            fitness_scores = [r.fitness for r in results]
            current_best_idx = max(range(len(fitness_scores)), key=lambda i: fitness_scores[i])
            current_best = results[current_best_idx]

            if current_best.fitness > best_fitness:
                best_fitness = current_best.fitness
                best_individual = current_best.individual
                log(f"✨ New global best: {best_individual} (fitness: {best_fitness:.4f})")

            # Log estatísticas
            log(f"\nGeneration {stats.generation} statistics:")
            log(f"  Average fitness: {stats.avg_fitness:.4f}")
            log(f"  Max fitness: {stats.max_fitness:.4f}")
            log(f"  Min fitness: {stats.min_fitness:.4f}")
            log(f"  Diversity: {stats.diversity:.4f}")
            log(f"  Convergence: {stats.convergence:.4f}")
            log(f"  Best individual: {stats.best_individual}")

            # Evolui para próxima geração
            if gen < self.params.generations - 1:  # Não evolui na última geração
                fitness_scores = [r.fitness for r in results]
                population = self.pop_manager.evolve(population, fitness_scores)

        # Aplica melhor configuração
        if best_individual:
            log(f"\n{'=' * 80}")
            log("Applying best configuration...")
            log(f"Best individual: {best_individual}")
            log(f"Best fitness: {best_fitness:.4f}")
            log(f"{'=' * 80}")

            try:
                self.k8s.apply_configuration(best_individual, save_for_rollback=False)
                log("✅ Best configuration applied successfully")
            except Exception as e:
                log(f"❌ Failed to apply best configuration: {e}", level="error")

        return best_individual

    def get_history(self) -> List[GenerationStats]:
        """Retorna histórico de gerações."""
        return self.history

    def get_evaluation_results(self) -> List[EvaluationResult]:
        """Retorna todos os resultados de avaliação."""
        return self.evaluation_results


def run() -> Optional[Individual]:
    """
    Função de conveniência para executar o GA.

    Returns:
        Melhor indivíduo encontrado
    """
    optimizer = GeneticOptimizer()
    return optimizer.run()


if __name__ == "__main__":
    run()
