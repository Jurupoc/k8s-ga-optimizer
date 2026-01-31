# scripts/run_ga.py
"""
Script principal para executar o algoritmo genético.
"""

import sys
from pathlib import Path

import argparse
import json
import time
from datetime import datetime
from typing import Optional

from ga.optimizer import GeneticOptimizer
from ga.config import GAParameters, AppConfig, PrometheusConfig
from integrations.prometheus_client import PrometheusClient
from integrations.k8s_client import KubernetesClient
from shared.utils import log


def validate_environment(app_config: AppConfig) -> bool:
    """
    Valida se o ambiente está pronto para executar o GA.

    Args:
        app_config: Configuração da aplicação

    Returns:
        True se ambiente está OK, False caso contrário
    """
    log("Validating environment...")

    # Valida Prometheus
    try:
        prom = PrometheusClient()
        if not prom.is_healthy():
            log("❌ Prometheus is not healthy", level="error")
            return False
        log("✅ Prometheus is healthy")
    except Exception as e:
        log(f"❌ Failed to connect to Prometheus: {e}", level="error")
        return False

    # Valida Kubernetes
    try:
        k8s = KubernetesClient(app_config)
        status = k8s.get_deployment_status()
        if not status:
            log("❌ Failed to get deployment status", level="error")
            return False
        log(f"✅ Kubernetes deployment found: {status['replicas']} replicas")
    except Exception as e:
        log(f"❌ Failed to connect to Kubernetes: {e}", level="error")
        return False

    return True


def save_results(output_path: Path, optimizer: GeneticOptimizer, params: GAParameters,
                 best: Optional[Any], execution_time: float, error: Optional[str] = None):
    """
    Salva resultados do GA (mesmo em caso de erro parcial).

    Args:
        output_path: Caminho do arquivo de saída
        optimizer: Otimizador genético
        params: Parâmetros do GA
        best: Melhor indivíduo encontrado
        execution_time: Tempo total de execução
        error: Mensagem de erro (se houver)
    """
    try:
        results = {
            "timestamp": datetime.now().isoformat(),
            "execution_time_seconds": round(execution_time, 2),
            "status": "error" if error else "success",
            "error": error,
            "config": {
                "ga": {
                    "population_size": params.population_size,
                    "generations": params.generations,
                    "mutation_rate": params.mutation_rate,
                    "crossover_rate": params.crossover_rate,
                    "elitism_count": params.elitism_count,
                    "tournament_size": params.tournament_size,
                },
                "bounds": {
                    "replicas": params.replicas_bounds,
                    "cpu_limit": params.cpu_limit_bounds,
                    "memory_limit": params.memory_limit_bounds,
                }
            },
            "best_individual": best.to_dict() if best else None,
            "evaluations": [r.to_dict() for r in optimizer.get_evaluation_results()],
            "generations": [s.to_dict() for s in optimizer.get_history()],
            "statistics": {
                "total_evaluations": len(optimizer.get_evaluation_results()),
                "completed_generations": len(optimizer.get_history()),
                "cache_size": optimizer.cache.size(),
                "failed_evaluations": sum(1 for r in optimizer.get_evaluation_results() if r.error),
            }
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(results, f, indent=2, default=str)

        log(f"Results saved to {output_path}")

    except Exception as e:
        log(f"❌ Failed to save results: {e}", level="error")


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(description="Run Genetic Algorithm Optimizer")
    parser.add_argument(
        "--output",
        default="/results/ga_optimization_results.json",
        help="Output file for results"
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip environment validation"
    )

    args = parser.parse_args()
    output_path = Path(args.output)

    start_time = time.time()
    best = None
    error_msg = None

    try:
        # Carrega configuração
        log("Loading configuration...")
        params = GAParameters.from_env()
        app_config = AppConfig.from_env()

        log(f"GA Parameters: population={params.population_size}, generations={params.generations}")
        log(f"Target: {app_config.deployment_name} in {app_config.namespace}")

        # Valida ambiente (opcional)
        if not args.skip_validation:
            if not validate_environment(app_config):
                log("❌ Environment validation failed. Use --skip-validation to bypass.", level="error")
                sys.exit(1)
        else:
            log("⚠️ Skipping environment validation", level="warning")

        # Cria otimizador (com checkpoint incremental)
        log("Creating optimizer...")
        checkpoint_file = output_path.parent / "checkpoint.json"
        optimizer = GeneticOptimizer(
            params=params,
            app_config=app_config,
            checkpoint_file=str(checkpoint_file)
        )

        # Executa
        log("=" * 80)
        log("Starting GA optimization...")
        log("=" * 80)
        best = optimizer.run()

        execution_time = time.time() - start_time

        # Salva resultados
        save_results(output_path, optimizer, params, best, execution_time)

        # Log final
        if best:
            log("\n" + "=" * 80)
            log("✅ Optimization complete!")
            log(f"⏱️  Total time: {execution_time:.2f}s")
            log(f"🏆 Best configuration: {best}")
            log(f"📊 Completed {len(optimizer.get_history())} generations")
            log(f"📈 Total evaluations: {len(optimizer.get_evaluation_results())}")
            log("=" * 80)
        else:
            log("\n⚠️ No valid configuration found")
            sys.exit(1)

    except KeyboardInterrupt:
        log("\n⚠️ Interrupted by user", level="warning")
        error_msg = "Interrupted by user"
        execution_time = time.time() - start_time

        # Salva resultados parciais
        if 'optimizer' in locals():
            save_results(output_path, optimizer, params, best, execution_time, error_msg)

        sys.exit(130)

    except Exception as e:
        log(f"\n❌ Fatal error: {e}", level="error")
        error_msg = str(e)
        execution_time = time.time() - start_time

        # Salva resultados parciais
        if 'optimizer' in locals():
            save_results(output_path, optimizer, params, best, execution_time, error_msg)

        sys.exit(1)


if __name__ == "__main__":
    main()
