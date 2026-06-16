"""
Persistência de resultados do GA em formato uniforme com o NSGA-II.

Layout do diretório de saída (espelha ``nsga/storage.py``):

- ``manifest.json``         — parâmetros do experimento (seed, bounds,
                              load_params, etc.)
- ``summary.json``          — estatísticas agregadas (cache, tempos,
                              pareto size, sucesso/falha)
- ``generation_NNN.csv``    — população + objetivos por geração
- ``pareto_front_NNN.csv``  — frente de Pareto 3D implícita da geração
                              (calculada com f1/f2/f3 derivados das métricas).
                              Nome alinhado ao NSGA-II para que
                              ``scripts/compare_algorithms.py`` funcione
                              sem alteração.
- ``evaluations.csv``       — long-format: 1 linha por avaliação
                              (gen, idx, genome, objectives, métricas
                              brutas, fitness, status, tempo)
- ``best.json``             — melhor indivíduo escolhido pela fitness escalar
- ``results.json``          — snapshot completo (retrocompat com o formato
                              monolítico anterior do GA)
- ``cache.jsonl``           — append-only de avaliações brutas (já mantido
                              por ``ga/cache.py``)

Os objetivos (f1, f2, f3) usam exatamente as mesmas fórmulas de
``nsga/objectives.py``:

.. code-block:: text

    f1 = 0.5 * cpu_throttling + 0.5 * (mem_peak_usage_bytes / (mem_limit_mib * 1024**2))
    f2 = replicas * (cpu_cores + mem_gib)
    f3 = -throughput_rps

Isso permite comparar diretamente as duas trajetórias com
``scripts/compare_algorithms.py``, que espera ``pareto_front_*.csv`` em
formato idêntico (cpu_m, mem_mib, replicas, f1, f2, f3, ...).
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from ga.types import EvaluationResult, EvaluationStatus, Individual


# ---------------------------------------------------------------------------
# Cálculo de objetivos (espelha nsga/objectives.py)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Objectives3D:
    """Objetivos NSGA-style derivados de uma avaliação do GA."""

    f1: float  # saturação
    f2: float  # custo provisionado
    f3: float  # -throughput


def compute_objectives(result: EvaluationResult) -> Objectives3D:
    """
    Calcula (f1, f2, f3) a partir de um ``EvaluationResult`` do GA.

    Para avaliações que falharam ou não têm métricas, retorna penalidades
    análogas a ``nsga.objectives.penalty_objectives`` (f1=10.0, f3=0.0,
    f2 calculado a partir do genome).
    """
    ind = result.individual
    cpu_cores = float(ind.cpu_limit)
    mem_gib = ind.memory_limit / 1024.0
    f2 = ind.replicas * (cpu_cores + mem_gib)

    if result.metrics is None or result.status != EvaluationStatus.OK:
        return Objectives3D(f1=10.0, f2=f2, f3=0.0)

    m = result.metrics
    cpu_throttle = max(min(m.cpu_throttling or 0.0, 1.0), 0.0)
    mem_limit_bytes = ind.memory_limit * 1024 * 1024
    mem_peak_ratio = (
        (m.memory_peak_usage or 0.0) / mem_limit_bytes
        if mem_limit_bytes > 0
        else 0.0
    )
    mem_peak_ratio = max(min(mem_peak_ratio, 1.0), 0.0)
    f1 = 0.5 * cpu_throttle + 0.5 * mem_peak_ratio
    f3 = -float(m.throughput)

    return Objectives3D(f1=f1, f2=f2, f3=f3)


# ---------------------------------------------------------------------------
# Pareto 3D filter (minimização)
# ---------------------------------------------------------------------------

def _dominates(a: Objectives3D, b: Objectives3D) -> bool:
    """True se `a` domina `b` (≤ em todos, < em algum)."""
    le = (a.f1 <= b.f1) and (a.f2 <= b.f2) and (a.f3 <= b.f3)
    lt = (a.f1 < b.f1) or (a.f2 < b.f2) or (a.f3 < b.f3)
    return le and lt


def filter_non_dominated(
    results: list[EvaluationResult],
    objectives: list[Objectives3D],
) -> list[int]:
    """
    Retorna os índices dos pontos não-dominados em ``objectives``.

    Args:
        results: lista de ``EvaluationResult`` (usada só para preservar
            mesma ordem que ``objectives``).
        objectives: lista de ``Objectives3D``, alinhada índice-a-índice.

    Returns:
        Lista de índices dos pontos não-dominados.
    """
    n = len(objectives)
    keep: list[int] = []
    for i in range(n):
        dominated = False
        for j in range(n):
            if i == j:
                continue
            if _dominates(objectives[j], objectives[i]):
                dominated = True
                break
        if not dominated:
            keep.append(i)
    return keep


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

class GAExperimentStorage:
    """
    Persiste resultados do GA no mesmo layout do NSGA-II.

    Uso típico (incremental, ao longo da run):

    .. code-block:: python

        storage = GAExperimentStorage(output_dir)
        storage.save_manifest(...)               # uma vez no início
        for gen in range(num_generations):
            ...
            storage.save_generation(gen, results)    # ao final de cada geração
            storage.save_pareto(gen, results)
        storage.save_summary(summary)                # ao fim do experimento
        storage.save_evaluations(all_results)        # ao fim do experimento
        storage.save_best(best_result)               # ao fim do experimento
    """

    # Cabeçalhos compatíveis com nsga/storage.py para que
    # scripts/compare_algorithms.py funcione sem alteração.
    GENERATION_HEADER = [
        "cpu_m",
        "mem_mib",
        "replicas",
        "f1",
        "f2",
        "f3",
        "rank",
        "crowding_distance",
        "status",
        "eval_time_s",
        "fitness",
    ]
    # Idêntico ao NSGA (nsga/storage.py linhas 120-125) para compat com
    # scripts/compare_algorithms.py — o GA não tem crowding_distance real
    # (fica 0.0) nem fitness escalar no schema, mas a coluna ``fitness``
    # extra é apêndice opcional para análise GA-específica.
    PARETO_HEADER = [
        "cpu_m",
        "mem_mib",
        "replicas",
        "f1",
        "f2",
        "f3",
        "crowding_distance",
        "status",
        "eval_time_s",
        "fitness",
    ]
    EVALUATIONS_HEADER = [
        "generation",
        "idx",
        "cpu_m",
        "mem_mib",
        "replicas",
        "fitness",
        "f1",
        "f2",
        "f3",
        "throughput",
        "p95_latency_s",
        "p99_latency_s",
        "avg_latency_s",
        "success_rate",
        "total_requests",
        "failed_requests",
        "cpu_usage_cores",
        "memory_usage_bytes",
        "cpu_utilization",
        "memory_utilization",
        "cpu_throttling",
        "memory_peak_usage_bytes",
        "status",
        "error",
        "eval_time_s",
    ]

    def __init__(self, output_dir: Path):
        """
        Args:
            output_dir: Diretório de saída. Criado se não existir.
        """
        self.output_dir: Path = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ----- manifest / summary --------------------------------------------

    def save_manifest(
        self,
        *,
        pop_size: int,
        num_generations: int,
        seed: int,
        load_profile: str,
        bounds: dict[str, Any],
        pc: float,
        pm: float,
        elitism_count: int,
        tournament_size: int,
        **kwargs: Any,
    ) -> None:
        """
        Salva ``manifest.json``. ``kwargs`` permite estender com campos
        adicionais (load_params, deployment_name, app_url, etc.) sem
        modificar a assinatura.
        """
        manifest: dict[str, Any] = {
            "algorithm": "ga",
            "pop_size": pop_size,
            "num_generations": num_generations,
            "seed": seed,
            "load_profile": load_profile,
            "bounds": bounds,
            "pc": pc,
            "pm": pm,
            "elitism_count": elitism_count,
            "tournament_size": tournament_size,
            **kwargs,
        }
        path = self.output_dir / "manifest.json"
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def save_summary(self, summary: dict[str, Any]) -> None:
        """Salva ``summary.json`` (mesmo schema do NSGA — total_evaluations,
        cache_hits, cache_misses, cache_hit_rate, total_time_s, etc.)."""
        path = self.output_dir / "summary.json"
        path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    # ----- per-generation CSVs -------------------------------------------

    def save_generation(
        self,
        generation: int,
        results: list[EvaluationResult],
    ) -> None:
        """
        Salva ``generation_NNN.csv`` com todos os indivíduos avaliados na
        geração. Inclui objetivos NSGA-style + fitness escalar do GA.

        O ``rank`` é deixado como -1 (o GA não tem ranking de Pareto na
        população, só fitness escalar) — preservado por compat de schema.
        """
        path = self.output_dir / f"generation_{generation:03d}.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(self.GENERATION_HEADER)
            for r in results:
                obj = compute_objectives(r)
                writer.writerow(self._row_generation(r, obj, rank=-1))

    def save_pareto(
        self,
        generation: int,
        results: list[EvaluationResult],
    ) -> None:
        """
        Calcula a frente de Pareto implícita (3D) dos resultados e a
        persiste em ``pareto_NNN.csv``.

        Só inclui avaliações com status=OK (falhas não devem aparecer na
        Pareto, mesmo que a penalidade as torne dominadas — é mais robusto
        filtrar explicitamente).
        """
        ok = [r for r in results if r.status == EvaluationStatus.OK]
        objectives = [compute_objectives(r) for r in ok]
        keep = filter_non_dominated(ok, objectives)

        # Nome alinhado ao NSGA (pareto_front_NNN.csv) para que o script
        # scripts/compare_algorithms.py achar via glob("pareto_front_*.csv").
        path = self.output_dir / f"pareto_front_{generation:03d}.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(self.PARETO_HEADER)
            for idx in keep:
                r = ok[idx]
                obj = objectives[idx]
                writer.writerow(self._row_pareto(r, obj))

    # ----- long-format evaluations ---------------------------------------

    def save_evaluations(self, results: list[EvaluationResult]) -> None:
        """
        Salva ``evaluations.csv`` com 1 linha por avaliação, em formato
        long. Habilita análise estatística direta com pandas/R sem
        precisar desaninhar JSON.
        """
        path = self.output_dir / "evaluations.csv"
        # Agrupa por geração para indexar dentro da geração (idx)
        per_gen_idx: dict[int, int] = {}
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(self.EVALUATIONS_HEADER)
            for r in results:
                gen = r.generation if r.generation is not None else -1
                idx = per_gen_idx.get(gen, 0)
                per_gen_idx[gen] = idx + 1
                obj = compute_objectives(r)
                writer.writerow(self._row_evaluation(r, obj, gen, idx))

    # ----- best / arbitrary blob -----------------------------------------

    def save_best(self, best: Optional[EvaluationResult]) -> None:
        """
        Salva ``best.json`` com a configuração escolhida + métricas + objetivos.
        Se ``best`` for ``None`` (run sem nenhuma avaliação válida), salva
        um JSON com ``null``.
        """
        path = self.output_dir / "best.json"
        if best is None:
            path.write_text("null", encoding="utf-8")
            return
        obj = compute_objectives(best)
        payload = {
            "individual": best.individual.to_dict(),
            "fitness": best.fitness,
            "objectives": {"f1": obj.f1, "f2": obj.f2, "f3": obj.f3},
            "metrics": best.metrics.to_dict() if best.metrics else None,
            "status": best.status.value if best.status else None,
            "generation": best.generation,
            "evaluation_time": best.evaluation_time,
        }
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    def save_results_json(self, payload: dict[str, Any]) -> None:
        """
        Salva o snapshot detalhado (``results.json``) que o ``run_ga.py``
        produzia historicamente. Mantido para retrocompat e para preservar
        toda informação estruturada por geração em um único arquivo.
        """
        path = self.output_dir / "results.json"
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    # ----- helpers -------------------------------------------------------

    @staticmethod
    def _row_generation(
        r: EvaluationResult,
        obj: Objectives3D,
        rank: int,
    ) -> list[Any]:
        ind = r.individual
        return [
            int(round(ind.cpu_limit * 1000)),
            int(ind.memory_limit),
            int(ind.replicas),
            obj.f1,
            obj.f2,
            obj.f3,
            rank,
            0.0,  # crowding_distance — não computada no GA
            r.status.value if r.status else EvaluationStatus.OK.value,
            r.evaluation_time,
            r.fitness,
        ]

    @staticmethod
    def _row_pareto(r: EvaluationResult, obj: Objectives3D) -> list[Any]:
        ind = r.individual
        return [
            int(round(ind.cpu_limit * 1000)),
            int(ind.memory_limit),
            int(ind.replicas),
            obj.f1,
            obj.f2,
            obj.f3,
            0.0,  # crowding_distance
            r.status.value if r.status else EvaluationStatus.OK.value,
            r.evaluation_time,
            r.fitness,
        ]

    @staticmethod
    def _row_evaluation(
        r: EvaluationResult,
        obj: Objectives3D,
        generation: int,
        idx: int,
    ) -> list[Any]:
        ind = r.individual
        m = r.metrics
        return [
            generation,
            idx,
            int(round(ind.cpu_limit * 1000)),
            int(ind.memory_limit),
            int(ind.replicas),
            r.fitness,
            obj.f1,
            obj.f2,
            obj.f3,
            m.throughput if m else 0.0,
            m.p95_latency if m else 0.0,
            m.p99_latency if m else 0.0,
            m.avg_latency if m else 0.0,
            m.success_rate if m else 0.0,
            m.total_requests if m else 0,
            m.failed_requests if m else 0,
            m.cpu_usage if m else 0.0,
            m.memory_usage if m else 0.0,
            m.cpu_utilization if m else 0.0,
            m.memory_utilization if m else 0.0,
            m.cpu_throttling if m else 0.0,
            m.memory_peak_usage if m else 0.0,
            r.status.value if r.status else EvaluationStatus.OK.value,
            r.error or "",
            r.evaluation_time,
        ]
