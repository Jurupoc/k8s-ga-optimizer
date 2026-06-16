# ga/optimizer.py
"""
Executor principal do Algoritmo Genético refatorado.
Usa módulos modulares: population, fitness, cache, etc.
"""

import time
import json
import random
from dataclasses import replace
from pathlib import Path
from datetime import datetime
from typing import Any, List, Optional

from ga.types import Individual, GenerationStats, EvaluationResult, EvaluationStatus
from ga.config import GAParameters, AppConfig
from ga.population import PopulationManager, Population
from ga.fitness import FitnessEvaluator, FitnessCalculator
from ga.cache import EvaluationCache
from integrations.prometheus_client import PrometheusClient
from integrations.k8s_client import KubernetesClient
from load.load_test import LoadTester
from shared.utils import log, calculate_variance
from ga.exceptions import GAException


class GeneticOptimizer:
    """
    Otimizador genético.
    """

    def __init__(
        self,
        params: Optional[GAParameters] = None,
        app_config: Optional[AppConfig] = None,
        checkpoint_file: Optional[str] = None,
    ):
        """
        Inicializa o otimizador.

        Args:
            params: Parâmetros do GA
            app_config: Configuração da aplicação
            checkpoint_file: Arquivo para salvar checkpoints incrementais (opcional)
        """
        self.params = params or GAParameters.from_env()
        self.app_config = app_config or AppConfig.from_env()
        self.checkpoint_file = checkpoint_file

        # Reprodutibilidade: semeia o módulo random global, usado por
        # ga/population.py para inicialização, crossover, mutação e
        # seleção por torneio. Roda em runs idênticas → mesma trajetória.
        random.seed(self.params.seed)
        log(f"Random seed: {self.params.seed}")

        # Inicializa componentes
        self.pop_manager = PopulationManager(self.params)
        self.prometheus = PrometheusClient()
        self.k8s = KubernetesClient(self.app_config)
        self.load_tester = LoadTester()
        self.fitness_calc = FitnessCalculator(sla_latency_ms=self.params.sla_latency_ms)
        self.evaluator = FitnessEvaluator(
            self.prometheus,
            self.k8s,
            self.load_tester,
            self.app_config,
            self.fitness_calc,
            require_prometheus_metrics=self.params.require_prometheus_metrics,
        )

        # Cache persistente em disco (append-only JSONL) ao lado do checkpoint.
        # Sobrevive a crash da run e permite reaproveitar avaliações entre runs
        # com mesma seed/config.
        #
        # ``load_profile`` e ``load_params`` entram na chave (alinhamento
        # semântico com ``nsga/cache.py``), de modo que mudanças no perfil
        # de carga invalidam medições antigas automaticamente.
        if self.checkpoint_file:
            cache_path = Path(self.checkpoint_file).parent / "cache.jsonl"
        else:
            cache_path = Path("/results/cache.jsonl")
        self.cache = EvaluationCache(
            cache_file=cache_path,
            load_profile=self.params.load_profile,
            load_params=self.params.cache_load_params(),
        )

        # Histórico
        self.history: List[GenerationStats] = []
        self.evaluation_results: List[EvaluationResult] = []
        # Estatísticas de cache (para summary.json)
        self.cache_hits: int = 0
        self.cache_misses: int = 0

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
            self.cache_hits += 1
            return cached
        self.cache_misses += 1

        # Avalia
        start_time = time.time()

        try:
            fitness, metrics = self.evaluator.evaluate(individual)
            evaluation_time = time.time() - start_time

            result = EvaluationResult(
                individual=individual,
                fitness=fitness,
                metrics=metrics,
                evaluation_time=evaluation_time,
                status=EvaluationStatus.OK,
            )

            # Armazena no cache apenas se fitness > 0 (resultado válido)
            # Resultados com fitness 0.0 podem indicar erro e não devem ser cacheados
            if fitness > 0.0:
                self.cache.put(individual, result)
            else:
                log(f"⚠️ Not caching result with fitness=0.0 for {individual}", level="debug")

            return result

        except Exception as e:
            log(f"❌ Evaluation failed for {individual}: {e}", level="error")
            # NÃO cacheia resultados de erro - permite retry em futuras gerações.
            # O status é derivado automaticamente da mensagem de erro (TIMEOUT
            # se a string indica "timeout"/"timed out"/"deadline", senão FAIL).
            err_str = str(e)
            return EvaluationResult(
                individual=individual,
                fitness=0.0,
                metrics=None,
                evaluation_time=time.time() - start_time,
                error=err_str,
                status=EvaluationStatus.from_error(err_str),
            )

    def _evaluate_population(
        self, population: Population, generation: int
    ) -> List[EvaluationResult]:
        """
        Avalia toda a população.

        Args:
            population: População a avaliar
            generation: Número da geração à qual estas avaliações pertencem.
                Anotado em cada ``EvaluationResult`` para permitir reconstrução
                fiel da trajetória (não depende de ``idx // population_size``,
                que quebra com cache hits ou populações de tamanho variável).

        Returns:
            Lista de resultados
        """
        # Delay entre avaliações para evitar sobrecarga da API do Kubernetes
        evaluation_delay = self.params.evaluation_delay

        # Avaliação sequencial
        results = []
        for idx, individual in enumerate(population.individuals):
            log(
                f"Evaluating individual {idx+1}/{len(population.individuals)}"
            )
            result = self._evaluate_individual(individual)
            # Marca a geração em que esta avaliação foi USADA (registramos
            # também para cache hits — facilita auditoria por geração).
            # Usa replace() para não mutar o objeto cacheado, caso o mesmo
            # genome reapareça em gerações futuras.
            result = replace(result, generation=generation)
            results.append(result)

            # Delay entre avaliações (exceto após a última)
            if idx < len(population.individuals) - 1 and evaluation_delay > 0:
                log(f"Waiting {evaluation_delay}s before next evaluation...", level="debug")
                time.sleep(evaluation_delay)

        return results

    def _calculate_generation_stats(
        self, population: Population, results: List[EvaluationResult]
    ) -> GenerationStats:
        """
        Calcula estatísticas da geração usando métodos da classe Population.

        Args:
            population: População
            results: Resultados de avaliação

        Returns:
            Estatísticas da geração
        """
        fitness_scores = [r.fitness for r in results]

        if not fitness_scores:
            raise GAException("No fitness scores available")

        # Estatísticas básicas de fitness
        avg_fitness = sum(fitness_scores) / len(fitness_scores)
        max_fitness = max(fitness_scores)
        min_fitness = min(fitness_scores)

        # Melhor indivíduo usando método da Population
        best_individual, best_score = population.get_best(fitness_scores)

        # Diversidade usando método da Population
        diversity = population.get_diversity()

        # Convergência (variação dos scores) usando função utilitária
        # Menor variância = maior convergência
        variance = calculate_variance(fitness_scores)
        convergence = 1.0 / (1.0 + variance)

        return GenerationStats(
            generation=population.generation,
            population_size=len(population.individuals),
            avg_fitness=avg_fitness,
            max_fitness=max_fitness,
            min_fitness=min_fitness,
            best_individual=best_individual,
            diversity=diversity,
            convergence=convergence,
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
        log("=" * 80)

        # Cria população inicial
        population = self.pop_manager.create_initial_population()

        best_individual: Optional[Individual] = None
        best_fitness = float("-inf")

        # Loop de gerações
        for gen in range(self.params.generations):
            log(f"{'=' * 80}")
            log(f"Generation {population.generation + 1}/{self.params.generations}")
            log(f"{'=' * 80}")

            # Avalia população
            results = self._evaluate_population(
                population, generation=population.generation
            )
            self.evaluation_results.extend(results)

            # Calcula estatísticas
            stats = self._calculate_generation_stats(population, results)
            self.history.append(stats)

            # Atualiza melhor global usando método da Population
            fitness_scores = [r.fitness for r in results]
            current_best_individual, current_best_fitness = population.get_best(fitness_scores)

            if current_best_fitness > best_fitness:
                best_fitness = current_best_fitness
                best_individual = current_best_individual
                log(
                    f"✨ New global best: {best_individual} (fitness: {best_fitness:.4f})"
                )

            # Log estatísticas
            log(f"Generation {stats.generation + 1} statistics:")
            log(f"  Average fitness: {stats.avg_fitness:.4f}")
            log(f"  Max fitness: {stats.max_fitness:.4f}")
            log(f"  Min fitness: {stats.min_fitness:.4f}")
            log(f"  Diversity: {stats.diversity:.4f}")
            log(f"  Convergence: {stats.convergence:.4f}")
            log(f"  Best individual: {stats.best_individual}")

            # Log detalhado de cada indivíduo com fitness
            log(f"Population details (Generation {stats.generation + 1}):")
            for idx, individual in enumerate(population.individuals):
                fitness = fitness_scores[idx] if idx < len(fitness_scores) else 0.0
                log(
                    f"  Individual {idx + 1}: REPLICAS={individual.replicas}, CPU={individual.cpu_limit}, MEMORY={individual.memory_limit} → fitness={fitness:.4f}"
                )

            # Salva checkpoint (inclui população atual e RNG state — habilita
            # retomada de runs interrompidas a partir desta geração).
            self.save_checkpoint(
                gen + 1, best_individual, best_fitness,
                population=population,
            )

            # Evolui para próxima geração
            if gen < self.params.generations - 1:  # Não evolui na última geração
                population = self.pop_manager.evolve(population, fitness_scores)

            log(f"{'=' * 80}")

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

    def save_checkpoint(
        self,
        generation: int,
        best_individual: Optional[Individual],
        best_fitness: float,
        population: Optional[Population] = None,
    ) -> None:
        """
        Salva checkpoint incremental do progresso.

        Conteúdo persistido:

        - Identificação: timestamp, generation, total_generations
        - Melhor global: best_individual + best_fitness
        - Estatísticas: completed_generations, total_evaluations, cache_size,
          cache_hits, cache_misses
        - **População atual** (se ``population`` for fornecido): lista de
          indivíduos com geração — permite reconstruir o estado evolutivo
          de onde parou.
        - **RNG state** (``random.getstate()``): tornar a retomada do GA
          determinística. Sem isso, o `random.seed(seed)` do __init__ não
          é suficiente — o avanço do PRNG durante a run precisa ser
          preservado para evitar viés de re-execução.

        O checkpoint é sobrescrito a cada chamada (não é append-only). Se
        precisar de histórico completo, use `evaluations.csv` + `cache.jsonl`.

        Args:
            generation: Geração atual (1-indexed para humano).
            best_individual: Melhor indivíduo até agora.
            best_fitness: Melhor fitness até agora.
            population: População atual (opcional). Se fornecida, é
                persistida para permitir retomada.
        """
        if not self.checkpoint_file:
            return

        try:
            checkpoint_data: dict[str, Any] = {
                "timestamp": datetime.now().isoformat(),
                "generation": generation,
                "total_generations": self.params.generations,
                "seed": self.params.seed,
                "best_individual": best_individual.to_dict() if best_individual else None,
                "best_fitness": best_fitness,
                "completed_generations": len(self.history),
                "total_evaluations": len(self.evaluation_results),
                "cache_size": self.cache.size(),
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
            }

            if population is not None:
                checkpoint_data["population"] = {
                    "generation": population.generation,
                    "individuals": [
                        ind.to_dict() for ind in population.individuals
                    ],
                }

            # RNG state: tupla complexa (versão, estado interno, gauss_next).
            # `random.getstate()` retorna formato não-JSON-nativo; salvamos
            # como lista para round-trip via json.
            try:
                rng_state = random.getstate()
                checkpoint_data["rng_state"] = [
                    rng_state[0],            # version
                    list(rng_state[1]),      # internal state (tuple → list)
                    rng_state[2],            # gauss_next (float ou None)
                ]
            except Exception as rng_err:
                # RNG state é nice-to-have; não bloqueia o checkpoint.
                log(f"Could not capture RNG state: {rng_err}", level="debug")

            checkpoint_path = Path(self.checkpoint_file)
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

            with open(checkpoint_path, "w") as f:
                json.dump(checkpoint_data, f, indent=2, default=str)

            log(f"Checkpoint saved: generation {generation}/{self.params.generations}", level="debug")

            # Limpa cache expirado periodicamente (a cada checkpoint)
            expired = self.cache.cleanup_expired()
            if expired > 0:
                log(f"Cleaned up {expired} expired cache entries", level="debug")

        except Exception as e:
            log(f"Failed to save checkpoint: {e}", level="warning")


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
