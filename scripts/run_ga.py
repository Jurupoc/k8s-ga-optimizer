# scripts/run_ga.py
"""
Script principal para executar o algoritmo genético.
"""
import sys
from pathlib import Path

import argparse
import json
from datetime import datetime

from ga.optimizer import GeneticOptimizer
from ga.config import GAParameters, AppConfig, PrometheusConfig
from integrations.prometheus_client import PrometheusClient
from shared.utils import log


def check_prometheus_connection() -> bool:
    """
    Verifica se é possível conectar ao Prometheus.
    
    Returns:
        True se conectou com sucesso, False caso contrário
    """
    try:
        log("Checking Prometheus connection...")
        config = PrometheusConfig.from_env()
        client = PrometheusClient(config)
        # Tenta obter o cliente (isso força a conexão)
        client._get_client()
        log("✅ Prometheus connection successful")
        return True
    except Exception as e:
        log(f"❌ Failed to connect to Prometheus: {e}", level="error")
        log("Exiting early - Prometheus connection is required for GA optimization", level="error")
        return False


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(description="Run Genetic Algorithm Optimizer")
    parser.add_argument("--output", default="results/ga_results.json", help="Output file for results")

    args = parser.parse_args()

    # Verifica conexão com Prometheus antes de continuar
    if not check_prometheus_connection():
        sys.exit(1)

    # Carrega configuração
    params = GAParameters.from_env()
    app_config = AppConfig.from_env()

    # Cria otimizador
    optimizer = GeneticOptimizer(
        params=params,
        app_config=app_config
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
