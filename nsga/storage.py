"""
Persistência de resultados por geração.
"""
import json
import csv
from pathlib import Path
from typing import List
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
        self.output_dir = output_dir
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
        **kwargs
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
        manifest = {
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
        with open(manifest_file, 'w') as f:
            json.dump(manifest, f, indent=2)
    
    def save_generation(self, generation: int, population: List[Individual]) -> None:
        """
        Salva população de uma geração em CSV.
        
        Args:
            generation: Número da geração
            population: Lista de indivíduos
        """
        csv_file = self.output_dir / f"generation_{generation:03d}.csv"
        
        with open(csv_file, 'w', newline='') as f:
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
    
    def save_pareto_front(self, generation: int, pareto_front: List[Individual]) -> None:
        """
        Salva frente de Pareto (rank 0) em arquivo separado.
        
        Args:
            generation: Número da geração
            pareto_front: Lista de indivíduos na frente de Pareto
        """
        csv_file = self.output_dir / f"pareto_front_{generation:03d}.csv"
        
        with open(csv_file, 'w', newline='') as f:
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
    
    def save_summary(self, summary: dict) -> None:
        """
        Salva resumo do experimento.
        
        Args:
            summary: Dicionário com estatísticas do experimento
        """
        summary_file = self.output_dir / "summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
    
    def append_log(self, message: str) -> None:
        """
        Adiciona mensagem ao log do experimento.
        
        Args:
            message: Mensagem a ser logada
        """
        log_file = self.output_dir / "experiment.log"
        with open(log_file, 'a') as f:
            f.write(message + '\n')
