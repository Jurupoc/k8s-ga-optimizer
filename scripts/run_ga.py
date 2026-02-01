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
                 best: Optional[any], execution_time: float, error: Optional[str] = None):
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
        # Organiza avaliações por geração
        evaluations_by_generation = {}
        evaluation_results = optimizer.get_evaluation_results()

        # Agrupa avaliações por geração
        # Assumindo que as avaliações estão em ordem e cada geração tem population_size avaliações
        for idx, eval_result in enumerate(evaluation_results):
            generation = idx // params.population_size
            if generation not in evaluations_by_generation:
                evaluations_by_generation[generation] = []
            evaluations_by_generation[generation].append(eval_result)

        # Cria estrutura detalhada de gerações
        generations_detailed = []
        for gen_stats in optimizer.get_history():
            generation_num = gen_stats.generation

            # Pega avaliações desta geração
            gen_evaluations = evaluations_by_generation.get(generation_num, [])

            # Cria lista de indivíduos com todas as informações
            individuals_detail = []
            for eval_result in gen_evaluations:
                individual_info = {
                    "individual": eval_result.individual.to_dict(),
                    "fitness": eval_result.fitness,
                    "evaluation_time_seconds": round(eval_result.evaluation_time, 2),
                    "error": eval_result.error,
                    "metrics": eval_result.metrics.to_dict() if eval_result.metrics else None,
                }
                individuals_detail.append(individual_info)

            # Adiciona informações da geração
            generation_info = {
                "generation": generation_num,
                "statistics": {
                    "population_size": gen_stats.population_size,
                    "avg_fitness": round(gen_stats.avg_fitness, 4),
                    "max_fitness": round(gen_stats.max_fitness, 4),
                    "min_fitness": round(gen_stats.min_fitness, 4),
                    "diversity": round(gen_stats.diversity, 4),
                    "convergence": round(gen_stats.convergence, 4),
                },
                "best_individual": gen_stats.best_individual.to_dict(),
                "all_individuals": individuals_detail,
            }
            generations_detailed.append(generation_info)

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
                    "evaluation_delay": params.evaluation_delay,
                    "sla_latency_ms": params.sla_latency_ms,
                    "require_prometheus_metrics": params.require_prometheus_metrics,
                },
                "bounds": {
                    "replicas": params.replicas_bounds,
                    "cpu_limit": params.cpu_limit_bounds,
                    "memory_limit": params.memory_limit_bounds,
                },
                "load_test": {
                    "duration": optimizer.load_tester.config.duration,
                    "concurrency": optimizer.load_tester.config.concurrency,
                    "timeout": optimizer.load_tester.config.timeout,
                    "profile": optimizer.load_tester.config.profile,
                    "warmup_duration": optimizer.load_tester.config.warmup_duration,
                }
            },
            "best_individual_overall": best.to_dict() if best else None,
            "generations": generations_detailed,
            "summary": {
                "total_evaluations": len(evaluation_results),
                "completed_generations": len(optimizer.get_history()),
                "cache_size": optimizer.cache.size(),
                "failed_evaluations": sum(1 for r in evaluation_results if r.error),
                "successful_evaluations": sum(1 for r in evaluation_results if not r.error),
                "total_evaluation_time_seconds": round(sum(r.evaluation_time for r in evaluation_results), 2),
                "avg_evaluation_time_seconds": round(
                    sum(r.evaluation_time for r in evaluation_results) / len(evaluation_results), 2
                ) if evaluation_results else 0,
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
