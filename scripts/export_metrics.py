# scripts/export_metrics.py
"""
Script para exportar resultados do GA em CSV/Parquet.
"""
import sys
from pathlib import Path

# Adiciona o diretório raiz do projeto ao PYTHONPATH
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

import argparse
import json
import pandas as pd
from typing import List, Dict, Any

from ga.types import EvaluationResult, GenerationStats
from shared.utils import log


def export_to_csv(
    results: List[EvaluationResult],
    output_path: str,
    include_metrics: bool = True
) -> None:
    """
    Exporta resultados para CSV.

    Args:
        results: Lista de resultados
        output_path: Caminho do arquivo de saída
        include_metrics: Se True, inclui métricas detalhadas
    """
    rows = []
    for result in results:
        row = {
            "replicas": result.individual.replicas,
            "cpu_limit": result.individual.cpu_limit,
            "memory_limit": result.individual.memory_limit,
            "fitness": result.fitness,
            "evaluation_time": result.evaluation_time,
            "error": result.error or ""
        }

        if include_metrics and result.metrics:
            metrics = result.metrics.to_dict()
            # Adiciona prefixo para evitar conflitos
            for key, value in metrics.items():
                row[f"metric_{key}"] = value

        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)
    log(f"Exported {len(results)} results to {output_path}")


def export_to_parquet(
    results: List[EvaluationResult],
    output_path: str,
    include_metrics: bool = True
) -> None:
    """
    Exporta resultados para Parquet.

    Args:
        results: Lista de resultados
        output_path: Caminho do arquivo de saída
        include_metrics: Se True, inclui métricas detalhadas
    """
    rows = []
    for result in results:
        row = {
            "replicas": result.individual.replicas,
            "cpu_limit": result.individual.cpu_limit,
            "memory_limit": result.individual.memory_limit,
            "fitness": result.fitness,
            "evaluation_time": result.evaluation_time,
            "error": result.error or ""
        }

        if include_metrics and result.metrics:
            metrics = result.metrics.to_dict()
            for key, value in metrics.items():
                row[f"metric_{key}"] = value

        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_parquet(output_path, index=False)
    log(f"Exported {len(results)} results to {output_path}")


def export_generations_to_csv(
    stats: List[GenerationStats],
    output_path: str
) -> None:
    """
    Exporta estatísticas de gerações para CSV.

    Args:
        stats: Lista de estatísticas
        output_path: Caminho do arquivo de saída
    """
    rows = []
    for stat in stats:
        row = stat.to_dict()
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)
    log(f"Exported {len(stats)} generation stats to {output_path}")


def export_to_json(
    results: List[EvaluationResult],
    stats: List[GenerationStats],
    output_path: str
) -> None:
    """
    Exporta tudo para JSON.

    Args:
        results: Lista de resultados
        stats: Lista de estatísticas
        output_path: Caminho do arquivo de saída
    """
    data = {
        "evaluations": [r.to_dict() for r in results],
        "generations": [s.to_dict() for s in stats],
        "summary": {
            "total_evaluations": len(results),
            "total_generations": len(stats),
            "best_fitness": max((r.fitness for r in results), default=0.0)
        }
    }

    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2, default=str)

    log(f"Exported data to {output_path}")


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(description="Export GA results")
    parser.add_argument("--input", required=True, help="Input JSON file with results")
    parser.add_argument("--output", required=True, help="Output file path")
    parser.add_argument("--format", choices=["csv", "parquet", "json"], default="csv")
    parser.add_argument("--no-metrics", action="store_true", help="Exclude detailed metrics")

    args = parser.parse_args()

    # Carrega dados
    with open(args.input, 'r') as f:
        data = json.load(f)

    results = [EvaluationResult(**r) for r in data.get("evaluations", [])]
    stats = [GenerationStats(**s) for s in data.get("generations", [])]

    # Exporta
    if args.format == "csv":
        export_to_csv(results, args.output, include_metrics=not args.no_metrics)
    elif args.format == "parquet":
        export_to_parquet(results, args.output, include_metrics=not args.no_metrics)
    else:
        export_to_json(results, stats, args.output)


if __name__ == "__main__":
    main()


