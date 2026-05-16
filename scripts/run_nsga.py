"""
Entrypoint do NSGA-II: monta o pipeline completo a partir de variáveis de
ambiente e executa o experimento, salvando resultados por geração.

Variáveis de ambiente (todas opcionais, com defaults sensatos):

NSGA (algoritmo):
  NSGA_POPULATION         (default: 6)
  NSGA_GENERATIONS        (default: 5)
  NSGA_CROSSOVER_RATE     (default: 0.9)    — pc
  NSGA_MUTATION_RATE      (default: 0.1)    — pm por gene
  NSGA_SEED               (default: 42)
  NSGA_OUTPUT_DIR         (default: /results/nsga)
  NSGA_STABILIZATION_S    (default: 5)
  NSGA_MOCK               (default: false)  — usa mock adapters (offline)

Search space (CPU em millicores, MEM em MiB):
  NSGA_CPU_MIN/MAX/STEP   (defaults: 100/2000/100)
  NSGA_MEM_MIN/MAX/STEP   (defaults: 128/2048/128)
  NSGA_REP_MIN/MAX        (defaults: 1/6)

Kubernetes / aplicação:
  K8S_DEPLOYMENT_NAME     (default: app-ga)
  K8S_NAMESPACE           (default: default)
  K8S_ROLLOUT_TIMEOUT     (default: 300)
  APP_URL                 (default: http://app-ga.default.svc.cluster.local:8080)
  APP_LABEL               (default: app-ga)

Load test:
  LOAD_TEST_DURATION              (default: 60)
  LOAD_TEST_CONCURRENCY           (default: 20)
  LOAD_TEST_TIMEOUT               (default: 10)
  LOAD_TEST_WARMUP_DURATION       (default: 10)
  LOAD_TEST_WARMUP_CONCURRENCY    (default: 2)
  LOAD_TEST_PROFILE               (default: "default")
  LOAD_TEST_ENDPOINT              (default: /mixed)

Prometheus:
  PROMETHEUS_URL                  (default: http://monitoring-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

# Garante que o diretório do projeto está no PYTHONPATH quando o script é
# executado diretamente (ex.: `python scripts/run_nsga.py`).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from nsga.adapters.k8s_adapter import K8sAdapter, RealK8sAdapter
from nsga.adapters.load_adapter import LoadAdapter, RealLoadAdapter
from nsga.adapters.mock_adapters import create_mock_adapters
from nsga.adapters.prometheus_adapter import PrometheusAdapter, RealPrometheusAdapter
from nsga.cache import EvaluationCache
from nsga.evaluate import EvaluatePipeline
from nsga.runner import NSGA2Runner
from nsga.search_space import SearchSpace
from nsga.storage import ExperimentStorage
from shared.utils import log


# ---------------------------------------------------------------------------
# Helpers de leitura de envvars
# ---------------------------------------------------------------------------

def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return float(raw)


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    return raw if raw is not None and raw != "" else default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

@dataclass
class NSGAConfig:
    """Configuração consolidada do experimento NSGA-II."""

    # Algoritmo
    pop_size: int = 6
    num_generations: int = 5
    pc: float = 0.9
    pm: float = 0.1
    seed: int = 42
    stabilization_s: int = 5
    output_dir: Path = field(default_factory=lambda: Path("/results/nsga"))
    mock: bool = False

    # Search space
    cpu_min: int = 100
    cpu_max: int = 2000
    cpu_step: int = 100
    mem_min: int = 128
    mem_max: int = 2048
    mem_step: int = 128
    rep_min: int = 1
    rep_max: int = 6

    # Kubernetes / app
    deployment_name: str = "app-ga"
    namespace: str = "default"
    rollout_timeout_s: int = 300
    app_url: str = "http://app-ga.default.svc.cluster.local:8080"
    app_label: str = "app-ga"

    # Load test
    load_duration: int = 60
    load_concurrency: int = 20
    load_timeout: int = 10
    load_warmup_duration: int = 10
    load_warmup_concurrency: int = 2
    load_profile: str = "default"
    load_endpoint: str = "/mixed"

    # Prometheus
    prometheus_url: str = (
        "http://monitoring-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090"
    )

    @classmethod
    def from_env(cls) -> "NSGAConfig":
        """Constrói a configuração lendo as variáveis de ambiente."""
        return cls(
            pop_size=_env_int("NSGA_POPULATION", 6),
            num_generations=_env_int("NSGA_GENERATIONS", 5),
            pc=_env_float("NSGA_CROSSOVER_RATE", 0.9),
            pm=_env_float("NSGA_MUTATION_RATE", 0.1),
            seed=_env_int("NSGA_SEED", 42),
            stabilization_s=_env_int("NSGA_STABILIZATION_S", 5),
            output_dir=Path(_env_str("NSGA_OUTPUT_DIR", "/results/nsga")),
            mock=_env_bool("NSGA_MOCK", False),
            cpu_min=_env_int("NSGA_CPU_MIN", 100),
            cpu_max=_env_int("NSGA_CPU_MAX", 2000),
            cpu_step=_env_int("NSGA_CPU_STEP", 100),
            mem_min=_env_int("NSGA_MEM_MIN", 128),
            mem_max=_env_int("NSGA_MEM_MAX", 2048),
            mem_step=_env_int("NSGA_MEM_STEP", 128),
            rep_min=_env_int("NSGA_REP_MIN", 1),
            rep_max=_env_int("NSGA_REP_MAX", 6),
            deployment_name=_env_str("K8S_DEPLOYMENT_NAME", "app-ga"),
            namespace=_env_str("K8S_NAMESPACE", "default"),
            rollout_timeout_s=_env_int("K8S_ROLLOUT_TIMEOUT", 300),
            app_url=_env_str("APP_URL", "http://app-ga.default.svc.cluster.local:8080"),
            app_label=_env_str("APP_LABEL", "app-ga"),
            load_duration=_env_int("LOAD_TEST_DURATION", 60),
            load_concurrency=_env_int("LOAD_TEST_CONCURRENCY", 20),
            load_timeout=_env_int("LOAD_TEST_TIMEOUT", 10),
            load_warmup_duration=_env_int("LOAD_TEST_WARMUP_DURATION", 10),
            load_warmup_concurrency=_env_int("LOAD_TEST_WARMUP_CONCURRENCY", 2),
            load_profile=_env_str("LOAD_TEST_PROFILE", "default"),
            load_endpoint=_env_str("LOAD_TEST_ENDPOINT", "/mixed"),
            prometheus_url=_env_str(
                "PROMETHEUS_URL",
                "http://monitoring-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["output_dir"] = str(self.output_dir)
        return d

    def search_space(self) -> SearchSpace:
        return SearchSpace(
            cpu_min=self.cpu_min,
            cpu_max=self.cpu_max,
            cpu_step=self.cpu_step,
            mem_min=self.mem_min,
            mem_max=self.mem_max,
            mem_step=self.mem_step,
            rep_min=self.rep_min,
            rep_max=self.rep_max,
        )

    def load_params(self) -> dict[str, Any]:
        """Parâmetros do load test que entram na chave do cache."""
        return {
            "duration": self.load_duration,
            "concurrency": self.load_concurrency,
            "timeout": self.load_timeout,
            "warmup_duration": self.load_warmup_duration,
            "warmup_concurrency": self.load_warmup_concurrency,
            "endpoint": self.load_endpoint,
        }


# ---------------------------------------------------------------------------
# Construção do pipeline
# ---------------------------------------------------------------------------

def build_adapters(
    cfg: NSGAConfig,
) -> tuple[K8sAdapter, PrometheusAdapter, LoadAdapter]:
    """Cria os adapters reais (ou mocks, se cfg.mock=True)."""
    if cfg.mock:
        log("⚠️  NSGA_MOCK=true — usando adapters sintéticos (sem cluster real)")
        k8s, prom, load = create_mock_adapters(seed=cfg.seed)
        return k8s, prom, load

    k8s = RealK8sAdapter(namespace=cfg.namespace)
    prom = RealPrometheusAdapter(prometheus_url=cfg.prometheus_url, app_label=cfg.app_label)
    load = RealLoadAdapter(
        duration=cfg.load_duration,
        concurrency=cfg.load_concurrency,
        timeout=cfg.load_timeout,
        warmup_duration=cfg.load_warmup_duration,
        warmup_concurrency=cfg.load_warmup_concurrency,
        endpoint=cfg.load_endpoint,
    )
    return k8s, prom, load


def build_runner(cfg: NSGAConfig) -> tuple[NSGA2Runner, ExperimentStorage, EvaluatePipeline]:
    """Monta o NSGA2Runner e seus colaboradores a partir do config."""
    search_space = cfg.search_space()

    k8s_adapter, prom_adapter, load_adapter = build_adapters(cfg)

    evaluator = EvaluatePipeline(
        k8s_adapter=k8s_adapter,
        prometheus_adapter=prom_adapter,
        load_adapter=load_adapter,
        deployment_name=cfg.deployment_name,
        app_url=cfg.app_url,
        rollout_timeout_s=cfg.rollout_timeout_s,
        stabilization_s=cfg.stabilization_s,
    )

    cache = EvaluationCache(
        cache_file=cfg.output_dir / "cache.jsonl",
        load_profile=cfg.load_profile,
        load_params=cfg.load_params(),
    )

    storage = ExperimentStorage(output_dir=cfg.output_dir)
    storage.save_manifest(
        pop_size=cfg.pop_size,
        num_generations=cfg.num_generations,
        seed=cfg.seed,
        load_profile=cfg.load_profile,
        search_space=search_space,
        pc=cfg.pc,
        pm=cfg.pm,
        load_params=cfg.load_params(),
        deployment_name=cfg.deployment_name,
        app_url=cfg.app_url,
        mock=cfg.mock,
    )

    runner = NSGA2Runner(
        search_space=search_space,
        evaluator=evaluator,
        cache=cache,
        storage=storage,
        pop_size=cfg.pop_size,
        num_generations=cfg.num_generations,
        pc=cfg.pc,
        pm=cfg.pm,
        seed=cfg.seed,
        verbose=True,
    )
    return runner, storage, evaluator


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Run NSGA-II resource optimizer")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Usa adapters sintéticos (offline). Equivalente a NSGA_MOCK=true.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Diretório de saída (sobrescreve NSGA_OUTPUT_DIR).",
    )
    args = parser.parse_args()

    cfg = NSGAConfig.from_env()
    if args.mock:
        cfg.mock = True
    if args.output_dir:
        cfg.output_dir = Path(args.output_dir)

    log("=" * 80)
    log("NSGA-II — otimização multiobjetivo de recursos no Kubernetes")
    log("=" * 80)
    log(f"output_dir         = {cfg.output_dir}")
    log(f"pop / gen          = {cfg.pop_size} / {cfg.num_generations}")
    log(f"pc / pm / seed     = {cfg.pc} / {cfg.pm} / {cfg.seed}")
    log(f"deployment / label = {cfg.deployment_name} / {cfg.app_label}")
    log(f"load profile       = {cfg.load_profile} ({cfg.load_endpoint})")
    log(f"mock               = {cfg.mock}")

    start_time = time.time()
    exit_code = 0
    runner: NSGA2Runner | None = None
    evaluator: EvaluatePipeline | None = None

    try:
        runner, _storage, evaluator = build_runner(cfg)
        runner.run()
    except KeyboardInterrupt:
        log("⚠️  Interrompido pelo usuário", level="warning")
        exit_code = 130
    except Exception as e:
        log(f"❌ Erro fatal: {e}", level="error")
        import traceback
        log(traceback.format_exc(), level="debug")
        exit_code = 1
    finally:
        if evaluator is not None:
            try:
                evaluator.cleanup()
            except Exception as e:
                log(f"Aviso: falha no cleanup: {e}", level="warning")

    elapsed = time.time() - start_time
    log(f"⏱️  Tempo total: {elapsed:.2f}s — exit={exit_code}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
