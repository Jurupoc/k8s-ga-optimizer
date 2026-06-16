"""
Runner principal do experimento NSGA-II.
"""
import random
import time
from typing import Any

from nsga.domain import EvaluationStatus, Individual, Objectives
from nsga.search_space import SearchSpace
from nsga.evaluate import EvaluatePipeline
from nsga.cache import EvaluationCache
from nsga.storage import ExperimentStorage
from nsga.operators import crossover_and_mutate
from nsga.nsga2 import (
    fast_non_dominated_sort,
    crowding_distance_assignment,
    binary_tournament_selection,
    select_next_population
)


class NSGA2Runner:
    """
    Runner para executar experimentos NSGA-II completos.
    """
    
    def __init__(
        self,
        search_space: SearchSpace,
        evaluator: EvaluatePipeline,
        cache: EvaluationCache,
        storage: ExperimentStorage,
        pop_size: int,
        num_generations: int,
        pc: float = 0.9,
        pm: float = 0.1,
        seed: int = 42,
        verbose: bool = True,
        use_cache: bool = True,
        eliminate_duplicates: bool = True,
        dedup_max_attempts: int = 50,
    ):
        """
        Inicializa o runner.
        
        Args:
            search_space: Espaço de busca
            evaluator: Pipeline de avaliação
            cache: Cache de avaliações
            storage: Storage para resultados
            pop_size: Tamanho da população
            num_generations: Número de gerações
            pc: Probabilidade de crossover
            pm: Probabilidade de mutação por gene
            seed: Seed aleatória
            verbose: Se True, imprime progresso
            use_cache: Se False, bypassa completamente o cache (não lê nem grava).
                Útil para forçar reavaliação sem precisar limpar o arquivo do PVC.
            eliminate_duplicates: Se True (default), tenta evitar genomes
                duplicados na população combinada (parents + offspring) antes
                da seleção. Replica o comportamento padrão do ``pymoo`` —
                importante para espaços de busca discretos pequenos, onde
                colisões de crossover/mutação são frequentes e inflam a
                frente final com cópias idênticas.
            dedup_max_attempts: Máximo de re-amostragens por offspring antes
                de aceitar um duplicado (default 50). Em espaços muito
                pequenos pode ser necessário aceitar para não travar.
        """
        self.search_space = search_space
        self.evaluator = evaluator
        self.cache = cache
        self.storage = storage
        self.pop_size = pop_size
        self.num_generations = num_generations
        self.pc = pc
        self.pm = pm
        self.seed = seed
        self.verbose = verbose
        self.use_cache = use_cache
        self.eliminate_duplicates = eliminate_duplicates
        self.dedup_max_attempts = dedup_max_attempts
        
        self.rng = random.Random(seed)
        
        # Estatísticas
        self.cache_hits = 0
        self.cache_misses = 0
        self.total_eval_time = 0.0
        self.dedup_replacements = 0  # quantas vezes substituímos um duplicado
        self.dedup_unresolved = 0    # quantas vezes aceitamos duplicado após max_attempts
    
    def run(self) -> list[Individual]:
        """
        Executa o experimento NSGA-II completo.
        
        Returns:
            População final
        """
        start_time = time.time()
        
        if self.verbose:
            print(f"Iniciando NSGA-II: pop={self.pop_size}, gen={self.num_generations}, seed={self.seed}")
            print(
                f"SearchSpace: CPU [{self.search_space.cpu_min}:{self.search_space.cpu_max}:{self.search_space.cpu_step}], "
                + f"MEM [{self.search_space.mem_min}:{self.search_space.mem_max}:{self.search_space.mem_step}], "
                + f"REP [{self.search_space.rep_min}:{self.search_space.rep_max}]"
            )
        
        # Histórico de populações por geração (para evaluations.csv long-format)
        history: list[list[Individual]] = []

        # Gerar população inicial
        population = self._initialize_population()
        
        # Avaliar população inicial
        if self.verbose:
            print(f"\nGeração 0: Avaliando {len(population)} indivíduos...")
        population = self._evaluate_population(population)
        
        # Classificar e salvar
        self._classify_population(population)
        self.storage.save_generation(0, population)
        pareto_front = [ind for ind in population if ind.rank == 0]
        self.storage.save_pareto_front(0, pareto_front)
        history.append(list(population))
        
        if self.verbose:
            self._print_generation_stats(0, population)
        
        # Loop de gerações
        for gen in range(1, self.num_generations):
            if self.verbose:
                print(f"\nGeração {gen}:")
            
            # Gerar offspring
            offspring = self._generate_offspring(population)
            
            # Avaliar offspring
            if self.verbose:
                print(f"  Avaliando {len(offspring)} offspring...")
            offspring = self._evaluate_population(offspring)
            
            # Combinar população e offspring
            combined = population + offspring
            
            # Selecionar próxima população (elitismo)
            population = select_next_population(combined, self.pop_size)
            
            # Salvar geração
            self.storage.save_generation(gen, population)
            pareto_front = [ind for ind in population if ind.rank == 0]
            self.storage.save_pareto_front(gen, pareto_front)
            history.append(list(population))
            
            if self.verbose:
                self._print_generation_stats(gen, population)
        
        # Salvar resumo
        total_time = time.time() - start_time
        # Overhead = tempo total menos o tempo gasto efetivamente em
        # avaliações K8s/load test. Mede o custo do algoritmo em si
        # (operadores genéticos, salvamento, etc.) vs o custo da fitness.
        overhead_time = max(total_time - self.total_eval_time, 0.0)
        final_pareto = [ind for ind in population if ind.rank == 0]
        unique_genomes = {ind.genome for ind in final_pareto}
        summary: dict[str, Any] = {
            "algorithm": "nsga",
            "total_time_s": total_time,
            "total_evaluation_time_s": self.total_eval_time,
            "overhead_time_s": overhead_time,
            "overhead_fraction": (
                overhead_time / total_time if total_time > 0 else 0.0
            ),
            "total_evaluations": self.cache_hits + self.cache_misses,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": self.cache.hit_rate(self.cache_hits, self.cache_hits + self.cache_misses),
            "avg_eval_time_s": self.total_eval_time / self.cache_misses if self.cache_misses > 0 else 0.0,
            "final_pareto_size": len(final_pareto),
            "final_pareto_unique": len(unique_genomes),
            "eliminate_duplicates": self.eliminate_duplicates,
            "dedup_replacements": self.dedup_replacements,
            "dedup_unresolved": self.dedup_unresolved,
        }
        self.storage.save_summary(summary)
        # Long-format CSV: 1 linha por indivíduo por geração — habilita
        # análise estatística direta com pandas/R sem precisar parsear o
        # cache.jsonl.
        try:
            self.storage.save_evaluations(history)
        except Exception as e:
            # Não-fatal: o experimento já completou e tudo o mais foi salvo.
            print(f"Aviso: falha ao salvar evaluations.csv: {e}")
        
        if self.verbose:
            print(f"\n{'='*60}")
            print(f"Experimento concluído em {total_time:.2f}s")
            print(f"Avaliações: {summary['total_evaluations']} (cache hits: {self.cache_hits}, misses: {self.cache_misses})")
            print(f"Taxa de cache: {summary['cache_hit_rate']:.2%}")
            print(f"Frente de Pareto final: {summary['final_pareto_size']} indivíduos")
            print(f"Resultados salvos em: {self.storage.output_dir}")
        
        return population
    
    def _initialize_population(self) -> list[Individual]:
        """
        Gera população inicial aleatória.
        
        Returns:
            Lista de indivíduos (sem avaliação)
        """
        population: list[Individual] = []
        for _ in range(self.pop_size):
            genome = self.search_space.random_genome(self.rng)
            # Criar indivíduo placeholder (será avaliado depois)
            ind = Individual(
                genome=genome,
                objectives=Objectives(f1=0.0, f2=0.0, f3=0.0)
            )
            population.append(ind)
        return population
    
    def _evaluate_population(self, population: list[Individual]) -> list[Individual]:
        """
        Avalia população usando cache quando possível.
        
        Args:
            population: Lista de indivíduos a serem avaliados
            
        Returns:
            Lista de indivíduos avaliados
        """
        evaluated: list[Individual] = []
        
        for ind in population:
            # Tentar buscar no cache (a menos que esteja desabilitado)
            cached_result = self.cache.get(ind.genome) if self.use_cache else None

            if cached_result is not None:
                # Cache hit
                self.cache_hits += 1
                ind.objectives = cached_result.objectives
                ind.eval_result = cached_result
            else:
                # Cache miss, avaliar
                self.cache_misses += 1
                result = self.evaluator.evaluate(ind.genome)
                ind.objectives = result.objectives
                ind.eval_result = result
                self.total_eval_time += result.eval_time_s

                # Só cacheia resultados bem-sucedidos. Falhas (FAIL/TIMEOUT)
                # carregam objetivos de penalidade e não devem persistir entre runs.
                if self.use_cache and result.status == EvaluationStatus.OK:
                    self.cache.put(result)
            
            evaluated.append(ind)
        
        return evaluated
    
    def _classify_population(self, population: list[Individual]) -> None:
        """
        Classifica população (rank e crowding distance).
        
        Args:
            population: População a ser classificada (modificada in-place)
        """
        fronts = fast_non_dominated_sort(population)
        crowding_distance_assignment(fronts)
    
    def _generate_offspring(self, population: list[Individual]) -> list[Individual]:
        """
        Gera offspring usando seleção, crossover e mutação.

        Se ``self.eliminate_duplicates`` estiver ativo, cada offspring é
        comparado por genome contra (população atual ∪ offspring já gerado).
        Em caso de colisão, re-aplica seleção+crossover+mutação até
        ``dedup_max_attempts`` vezes; se ainda colidir, sorteia um genome
        completamente novo do espaço de busca. Se mesmo assim colidir
        (espaço pequeno e muito explorado), o duplicado é aceito e o
        contador ``dedup_unresolved`` é incrementado para diagnóstico.

        Args:
            population: População atual

        Returns:
            Lista de offspring
        """
        offspring: list[Individual] = []

        # Set de genomes já presentes (parents + offspring acumulado).
        # Usado só quando eliminate_duplicates=True; mas manter o branch
        # único simplifica a manutenção e o overhead é desprezível.
        seen: set = {ind.genome for ind in population}

        while len(offspring) < self.pop_size:
            # Seleção por torneio
            parent1 = binary_tournament_selection(population, self.rng)
            parent2 = binary_tournament_selection(population, self.rng)

            # Crossover e mutação
            child1_genome, child2_genome = crossover_and_mutate(
                parent1.genome,
                parent2.genome,
                self.search_space,
                self.pc,
                self.pm,
                self.rng,
            )

            for child_genome in (child1_genome, child2_genome):
                if len(offspring) >= self.pop_size:
                    break

                final_genome = child_genome
                if self.eliminate_duplicates and final_genome in seen:
                    final_genome = self._resolve_duplicate(final_genome, seen)

                offspring.append(Individual(
                    genome=final_genome,
                    objectives=Objectives(f1=0.0, f2=0.0, f3=0.0),
                ))
                seen.add(final_genome)

        return offspring[: self.pop_size]

    def _resolve_duplicate(self, genome, seen: set):
        """
        Tenta produzir um genome único quando ``genome`` já está em ``seen``.

        Estratégia:
        1. Re-amostra ``dedup_max_attempts`` genomes aleatórios do espaço
           de busca. Se algum não estiver em ``seen``, retorna-o.
        2. Caso todos colidam (espaço discreto muito pequeno), incrementa
           ``dedup_unresolved`` e devolve o genome original.

        Não fazemos re-crossover porque o efeito do operador depende de
        pais — re-amostragem random é mais robusta como fallback e ainda
        respeita o espaço de busca/steps via ``random_genome``.
        """
        for _ in range(self.dedup_max_attempts):
            candidate = self.search_space.random_genome(self.rng)
            if candidate not in seen:
                self.dedup_replacements += 1
                return candidate
        # Espaço esgotado — aceita o duplicado para não travar.
        self.dedup_unresolved += 1
        return genome
    
    def _print_generation_stats(self, generation: int, population: list[Individual]) -> None:
        """
        Imprime estatísticas da geração.
        
        Args:
            generation: Número da geração
            population: População atual
        """
        pareto_front = [ind for ind in population if ind.rank == 0]
        
        # Estatísticas dos objetivos na frente de Pareto
        if pareto_front:
            f1_values = [ind.objectives.f1 for ind in pareto_front]
            f2_values = [ind.objectives.f2 for ind in pareto_front]
            f3_values = [ind.objectives.f3 for ind in pareto_front]
            
            print(f"  Frente de Pareto: {len(pareto_front)} indivíduos")
            print(f"  f1 (saturação): [{min(f1_values):.4f}, {max(f1_values):.4f}]")
            print(f"  f2 (recursos): [{min(f2_values):.4f}, {max(f2_values):.4f}]")
            print(f"  f3 (-throughput): [{min(f3_values):.4f}, {max(f3_values):.4f}]")
            
            # Melhor em cada objetivo
            best_f1 = min(pareto_front, key=lambda ind: ind.objectives.f1)
            best_f2 = min(pareto_front, key=lambda ind: ind.objectives.f2)
            best_f3 = min(pareto_front, key=lambda ind: ind.objectives.f3)
            
            print(f"  Melhor saturação: cpu={best_f1.genome.cpu_m}, mem={best_f1.genome.mem_mib}, rep={best_f1.genome.replicas}")
            print(f"  Menor recurso: cpu={best_f2.genome.cpu_m}, mem={best_f2.genome.mem_mib}, rep={best_f2.genome.replicas}")
            print(f"  Maior throughput: cpu={best_f3.genome.cpu_m}, mem={best_f3.genome.mem_mib}, rep={best_f3.genome.replicas}")
