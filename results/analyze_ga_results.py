import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

# Configure matplotlib to use non-interactive backend (must be before importing pyplot)
import matplotlib
matplotlib.use('Agg')  # Use Agg backend for non-interactive plotting
import matplotlib.pyplot as plt


def _avg(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _flatten_evaluations(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Flatten generations[*].all_individuals[*] into a list of rows
    with merged fields: generation, individual params, fitness, metrics.
    """
    rows: List[Dict[str, Any]] = []
    for g in data.get("generations", []):
        gen = g.get("generation")
        for entry in g.get("all_individuals", []) or []:
            ind = entry.get("individual", {}) or {}
            metrics = entry.get("metrics", {}) or {}
            row = {
                "generation": gen,
                "fitness": _safe_float(entry.get("fitness")),
                "evaluation_time_seconds": _safe_float(entry.get("evaluation_time_seconds")),
                "error": entry.get("error"),
                "replicas": ind.get("replicas"),
                "cpu_limit": _safe_float(ind.get("cpu_limit")),
                "memory_limit": _safe_float(ind.get("memory_limit")),
                # Load-test metrics
                "throughput": _safe_float(metrics.get("throughput")),
                "avg_latency": _safe_float(metrics.get("avg_latency")),
                "p95_latency": _safe_float(metrics.get("p95_latency")),
                "p99_latency": _safe_float(metrics.get("p99_latency")),
                "success_rate": _safe_float(metrics.get("success_rate")),
                "error_rate": _safe_float(metrics.get("error_rate")),
                "total_requests": _safe_float(metrics.get("total_requests")),
                "failed_requests": _safe_float(metrics.get("failed_requests")),
                # Prometheus/system metrics
                "cpu_usage": _safe_float(metrics.get("cpu_usage")),
                "memory_usage_bytes": _safe_float(metrics.get("memory_usage")),
                "cpu_utilization": _safe_float(metrics.get("cpu_utilization")),
                "memory_utilization": _safe_float(metrics.get("memory_utilization")),
                "cpu_throttling": _safe_float(metrics.get("cpu_throttling")),
                "memory_peak_usage_bytes": _safe_float(metrics.get("memory_peak_usage")),
                "evaluated_at": metrics.get("evaluated_at"),
            }
            rows.append(row)
    return rows


def _write_csv(rows: List[Dict[str, Any]], out_path: Path) -> None:
    if not rows:
        return
    # stable columns (ordered)
    cols = list(rows[0].keys())
    with out_path.open("w", encoding="utf-8") as f:
        f.write(",".join(cols) + "\n")
        for r in rows:
            vals = []
            for c in cols:
                v = r.get(c)
                if v is None:
                    vals.append("")
                else:
                    s = str(v)
                    # basic CSV safety
                    if "," in s or "\n" in s:
                        s = '"' + s.replace('"', '""') + '"'
                    vals.append(s)
            f.write(",".join(vals) + "\n")


def _plot_series(out_path: Path, x: List[Any], ys: List[Tuple[str, List[float]]], title: str, xlabel: str, ylabel: str) -> None:
    plt.figure()
    for label, series in ys:
        plt.plot(x, series, label=label)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close()


def _plot_scatter(out_path: Path, x: List[float], y: List[float], title: str, xlabel: str, ylabel: str) -> None:
    plt.figure()
    plt.scatter(x, y, s=18)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.grid(True, alpha=0.3)
    plt.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="Analyze GA results JSON (v2 format) and generate plots/CSV.")
    parser.add_argument("--input", required=True, help="Path to ga_results.json")
    parser.add_argument("--outdir", default="out", help="Directory to write plots and CSV")
    args = parser.parse_args()

    in_path = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    with in_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    generations = data.get("generations", [])
    summary = data.get("summary", {}) or data.get("statistics", {}) or {}

    print("\n=== GA Run Summary ===")
    print(f"Input: {in_path}")
    print(f"Timestamp: {data.get('timestamp')}")
    print(f"Execution time (s): {data.get('execution_time_seconds')}")
    print(f"Status: {data.get('status')}")
    print(f"Population size: {data.get('config', {}).get('ga', {}).get('population_size')}")
    print(f"Generations: {data.get('config', {}).get('ga', {}).get('generations')}")
    print(f"Total evaluations: {summary.get('total_evaluations', 'N/A')}")
    print(f"Failed evaluations: {summary.get('failed_evaluations', 'N/A')}")
    print(f"Cache size: {summary.get('cache_size', 'N/A')}")
    print(f"Best overall: {data.get('best_individual_overall')}")

    if not generations:
        print("\nNo generations data found. Exiting.")
        return

    # ---- Generation-level plots ----
    gen_ids = [g.get("generation", i) for i, g in enumerate(generations)]
    avg_fit = []
    max_fit = []
    min_fit = []
    diversity = []
    convergence = []
    best_rep = []
    best_cpu = []
    best_mem = []

    for g in generations:
        stats = g.get("statistics", {}) or {}
        avg_fit.append(_safe_float(stats.get("avg_fitness")))
        max_fit.append(_safe_float(stats.get("max_fitness")))
        min_fit.append(_safe_float(stats.get("min_fitness")))
        diversity.append(_safe_float(stats.get("diversity")))
        convergence.append(_safe_float(stats.get("convergence")))

        bi = g.get("best_individual", {}) or {}
        best_rep.append(_safe_float(bi.get("replicas")))
        best_cpu.append(_safe_float(bi.get("cpu_limit")))
        best_mem.append(_safe_float(bi.get("memory_limit")))

    _plot_series(
        outdir / "fitness_over_generations.png",
        gen_ids,
        [("avg_fitness", avg_fit), ("max_fitness", max_fit), ("min_fitness", min_fit)],
        "GA Fitness Over Generations",
        "Generation",
        "Fitness",
    )
    print(f"Saved: {outdir / 'fitness_over_generations.png'}")

    _plot_series(
        outdir / "diversity_convergence.png",
        gen_ids,
        [("diversity", diversity), ("convergence", convergence)],
        "Population Diversity and Convergence",
        "Generation",
        "Value",
    )
    print(f"Saved: {outdir / 'diversity_convergence.png'}")

    _plot_series(
        outdir / "best_params_over_generations.png",
        gen_ids,
        [("best.replicas", best_rep), ("best.cpu_limit", best_cpu), ("best.memory_limit", best_mem)],
        "Best Individual Parameters Over Generations",
        "Generation",
        "Value",
    )
    print(f"Saved: {outdir / 'best_params_over_generations.png'}")

    # ---- Flatten all individuals and write CSV ----
    rows = _flatten_evaluations(data)
    csv_path = outdir / "evaluations.csv"
    _write_csv(rows, csv_path)
    print(f"Saved: {csv_path}")

    # ---- Quick diagnostics: CPU=0.0 occurrences ----
    cpu_zeros = sum(1 for r in rows if abs(_safe_float(r.get("cpu_usage")) - 0.0) < 1e-12)
    print(f"\nCPU usage == 0.0 count: {cpu_zeros} / {len(rows)}")
    if cpu_zeros:
        print("Note: CPU=0.0 suggests missing samples/window issues. Your new query_range+90s changes should reduce this.")

    # ---- Trade-off plots (scatter) ----
    # Only use rows with meaningful numbers
    thr = []
    p95 = []
    cpu = []
    cpu_u = []
    mem_u = []
    thrott = []
    fit = []
    for r in rows:
        t = _safe_float(r.get("throughput"))
        l95 = _safe_float(r.get("p95_latency"))
        c = _safe_float(r.get("cpu_usage"))
        cu = _safe_float(r.get("cpu_utilization"))
        mu = _safe_float(r.get("memory_utilization"))
        th = _safe_float(r.get("cpu_throttling"))
        fval = _safe_float(r.get("fitness"))

        # filter out empty lines
        if t <= 0 or l95 <= 0:
            continue

        thr.append(t)
        p95.append(l95)
        cpu.append(c)
        cpu_u.append(cu)
        mem_u.append(mu)
        thrott.append(th)
        fit.append(fval)

    if thr:
        _plot_scatter(
            outdir / "throughput_vs_p95.png",
            thr, p95,
            "Throughput vs P95 Latency",
            "Throughput (req/s)",
            "P95 latency (s)",
        )
        print(f"Saved: {outdir / 'throughput_vs_p95.png'}")

    if thr and cpu:
        _plot_scatter(
            outdir / "throughput_vs_cpu_usage.png",
            thr, cpu,
            "Throughput vs CPU Usage",
            "Throughput (req/s)",
            "CPU usage (cores)",
        )
        print(f"Saved: {outdir / 'throughput_vs_cpu_usage.png'}")

    if thr and cpu_u:
        _plot_scatter(
            outdir / "throughput_vs_cpu_utilization.png",
            thr, cpu_u,
            "Throughput vs CPU Utilization",
            "Throughput (req/s)",
            "CPU utilization (usage/limit)",
        )
        print(f"Saved: {outdir / 'throughput_vs_cpu_utilization.png'}")

    if thr and mem_u:
        _plot_scatter(
            outdir / "throughput_vs_memory_utilization.png",
            thr, mem_u,
            "Throughput vs Memory Utilization",
            "Throughput (req/s)",
            "Memory utilization (usage/limit)",
        )
        print(f"Saved: {outdir / 'throughput_vs_memory_utilization.png'}")

    if thrott and p95:
        _plot_scatter(
            outdir / "throttling_vs_p95.png",
            thrott, p95,
            "CPU Throttling vs P95 Latency",
            "CPU throttling (throttled seconds/s)",
            "P95 latency (s)",
        )
        print(f"Saved: {outdir / 'throttling_vs_p95.png'}")

    if fit and thr:
        _plot_scatter(
            outdir / "fitness_vs_throughput.png",
            fit, thr,
            "Fitness vs Throughput",
            "Fitness",
            "Throughput (req/s)",
        )
        print(f"Saved: {outdir / 'fitness_vs_throughput.png'}")

    print("\nDone.")


if __name__ == "__main__":
    main()
