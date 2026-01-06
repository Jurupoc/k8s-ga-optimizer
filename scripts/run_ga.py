# scripts/run_ga.py
"""
Script principal para executar o algoritmo genético.
"""
import sys
from pathlib import Path

# Adiciona o diretório raiz do projeto ao PYTHONPATH
# Isso permite que os imports funcionem independente de onde o script é executado
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

import argparse
import json
from datetime import datetime

from ga.optimizer import GeneticOptimizer
from ga.config import GAParameters, AppConfig
from shared.utils import log


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(description="Run Genetic Algorithm Optimizer")
    parser.add_argument("--config", help="JSON config file")
    parser.add_argument("--output", default="ga_results.json", help="Output file for results")
    parser.add_argument("--parallel", action="store_true", help="Enable parallel evaluations")
    parser.add_argument("--workers", type=int, default=2, help="Number of parallel workers")

    args = parser.parse_args()

    # Carrega configuração
    params = GAParameters.from_env()
    app_config = AppConfig.from_env()

    if args.config:
        with open(args.config, 'r') as f:
            config_data = json.load(f)
            # Atualiza params se especificado
            if "ga" in config_data:
                ga_data = config_data["ga"]
                params.population_size = ga_data.get("population_size", params.population_size)
                params.generations = ga_data.get("generations", params.generations)
                params.mutation_rate = ga_data.get("mutation_rate", params.mutation_rate)
                # ... outros parâmetros

    # Cria otimizador
    optimizer = GeneticOptimizer(
        params=params,
        app_config=app_config,
        parallel_evaluations=args.parallel,
        max_workers=args.workers
    )

    # Executa
    log("Starting GA optimization...")
    best = optimizer.run()

    # Salva resultados
    results = {
        "timestamp": datetime.now().isoformat(),
        "config": {
            "ga": {
                "population_size": params.population_size,
                "generations": params.generations,
                "mutation_rate": params.mutation_rate,
                "crossover_rate": params.crossover_rate
            }
        },
        "best_individual": best.to_dict() if best else None,
        "evaluations": [r.to_dict() for r in optimizer.get_evaluation_results()],
        "generations": [s.to_dict() for s in optimizer.get_history()]
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    log(f"Results saved to {output_path}")

    if best:
        log("\n✅ Optimization complete!")
        log(f"Best configuration: {best}")
    else:
        log("\n⚠️ No valid configuration found")


if __name__ == "__main__":
    main()


