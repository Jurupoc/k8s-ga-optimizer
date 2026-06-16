"""
Persistência de resultados por geração.
"""
import json
import csv
from pathlib import Path
from typing import Any
from nsga.domain import Individual
from nsga.search_space import SearchSpace


class ExperimentStorage:
    """
    Armazena resultados de experimentos em disco.
    
    Formato:
    - manifest.json: parâmetros do experimento
    - generation_N.csv: população da geração N com todos os dados
    """
    
    def __init__(self, output_dir: Path):
        """
        Inicializa o storage.
        
        Args:
            output_dir: Diretório de saída para resultados
        """
        self.output_dir: Path = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def save_manifest(
        self,
        pop_size: int,
        num_generations: int,
        seed: int,
        load_profile: str,
        search_space: SearchSpace,
        pc: float,
        pm: float,
        **kwargs: Any,
    ) -> None:
        """
        Salva manifest com parâmetros do experimento.
        
        Args:
            pop_size: Tamanho da população
            num_generations: Número de gerações
            seed: Seed aleatória
            load_profile: Perfil de carga
            search_space: Espaço de busca
            pc: Probabilidade de crossover
            pm: Probabilidade de mutação
            **kwargs: Outros parâmetros
        """
        manifest: dict[str, Any] = {
            "pop_size": pop_size,
            "num_generations": num_generations,
            "seed": seed,
            "load_profile": load_profile,
            "search_space": search_space.to_dict(),
            "pc": pc,
            "pm": pm,
            **kwargs
        }
        
        manifest_file = self.output_dir / "manifest.json"
        with open(manifest_file, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)
    
    def save_generation(self, generation: int, population: list[Individual]) -> None:
        """
        Salva população de uma geração em CSV.
        
        Args:
            generation: Número da geração
            population: Lista de indivíduos
        """
        csv_file = self.output_dir / f"generation_{generation:03d}.csv"
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                'cpu_m', 'mem_mib', 'replicas',
                'f1', 'f2', 'f3',
                'rank', 'crowding_distance',
                'status', 'eval_time_s'
            ])
            
            # Dados
            for ind in population:
                writer.writerow([
                    ind.genome.cpu_m,
                    ind.genome.mem_mib,
                    ind.genome.replicas,
                    ind.objectives.f1,
                    ind.objectives.f2,
                    ind.objectives.f3,
                    ind.rank,
                    ind.crowding_distance,
                    ind.eval_result.status.value if ind.eval_result else 'unknown',
                    ind.eval_result.eval_time_s if ind.eval_result else 0.0
                ])
    
    def save_pareto_front(self, generation: int, pareto_front: list[Individual]) -> None:
        """
        Salva frente de Pareto (rank 0) em arquivo separado.
        
        Args:
            generation: Número da geração
            pareto_front: Lista de indivíduos na frente de Pareto
        """
        csv_file = self.output_dir / f"pareto_front_{generation:03d}.csv"
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                'cpu_m', 'mem_mib', 'replicas',
                'f1', 'f2', 'f3',
                'crowding_distance',
                'status', 'eval_time_s'
            ])
            
            # Dados
            for ind in pareto_front:
                writer.writerow([
                    ind.genome.cpu_m,
                    ind.genome.mem_mib,
                    ind.genome.replicas,
                    ind.objectives.f1,
                    ind.objectives.f2,
                    ind.objectives.f3,
                    ind.crowding_distance,
                    ind.eval_result.status.value if ind.eval_result else 'unknown',
                    ind.eval_result.eval_time_s if ind.eval_result else 0.0
                ])
    
    def save_summary(self, summary: dict[str, Any]) -> None:
        """
        Salva resumo do experimento.
        
        Args:
            summary: Dicionário com estatísticas do experimento
        """
        summary_file = self.output_dir / "summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)

    EVALUATIONS_HEADER = [
        "generation",
        "idx",
        "cpu_m",
        "mem_mib",
        "replicas",
        "f1",
        "f2",
        "f3",
        "throughput_rps",
        "cpu_throttle_rate",
        "mem_peak_ratio",
        "rank",
        "crowding_distance",
        "status",
        "eval_time_s",
    ]

    def save_evaluations(
        self, generations: list[list[Individual]]
    ) -> None:
        """
        Salva ``evaluations.csv`` em formato long: uma linha por indivíduo
        em cada geração, com objetivos + métricas brutas + status.

        Args:
            generations: Lista de populações por geração (ordem cronológica).
                Cada elemento é uma lista de ``Individual`` da geração N.

        Schema alinhado conceitualmente com ``ga/storage.py``
        (``EVALUATIONS_HEADER``) — mas usando os nomes nativos do NSGA-II
        (``throughput_rps``, ``cpu_throttle_rate``, ``mem_peak_ratio``)
        para preservar a semântica original das métricas.
        """
        path = self.output_dir / "evaluations.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(self.EVALUATIONS_HEADER)
            for gen, population in enumerate(generations):
                for idx, ind in enumerate(population):
                    raw = ind.eval_result.raw_metrics if ind.eval_result else None
                    writer.writerow([
                        gen,
                        idx,
                        ind.genome.cpu_m,
                        ind.genome.mem_mib,
                        ind.genome.replicas,
                        ind.objectives.f1,
                        ind.objectives.f2,
                        ind.objectives.f3,
                        raw.throughput_rps if raw else 0.0,
                        raw.cpu_throttle_rate if raw else 0.0,
                        raw.mem_peak_ratio if raw else 0.0,
                        ind.rank,
                        ind.crowding_distance,
                        ind.eval_result.status.value if ind.eval_result else "unknown",
                        ind.eval_result.eval_time_s if ind.eval_result else 0.0,
                    ])
