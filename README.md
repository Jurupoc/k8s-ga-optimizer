# Evolutionary Resource Optimization in Kubernetes

This repository contains the full implementation and experimental setup for the undergraduate thesis:

**"Application of Genetic Algorithms for Resource Optimization in Kubernetes Environments"**

The project investigates evolutionary algorithms to automatically discover efficient Kubernetes cluster configurations — specifically **replica count, CPU limits, and memory limits** — for a given application workload.
Two algorithms coexist in the repository:

- **GA** (`ga/`) — original **single-objective** Genetic Algorithm that maximizes a weighted fitness score combining latency, resource efficiency, and reliability.
- **NSGA-II** (`nsga/`) — **multi-objective** evolution that optimizes saturation, provisioned resources, and throughput simultaneously, returning a Pareto front of non-dominated configurations.

Both share the same supporting infrastructure (Kubernetes adapter, Prometheus client, load tester) and run as Kubernetes Jobs against a real cluster.

---

## 📖 Overview

Kubernetes provides automated deployment and scaling mechanisms for containerized applications, but **resource configuration is still commonly performed manually or via static rules**. This can lead to inefficient resource usage, performance degradation, or saturation under varying workloads.

This project proposes an **evolutionary optimization loop** that:

1. **Applies** a candidate configuration to a running Kubernetes Deployment
2. **Executes** a controlled load test against the application (90s duration + 10s warm-up)
3. **Collects** performance and resource metrics from Prometheus (CPU, memory, throttling)
4. **Computes** an objective score (single fitness for GA, three objectives for NSGA-II)
5. **Evolves** the population toward improved configurations using tournament selection, crossover, and mutation

The final configuration (or Pareto front) discovered by the algorithm is then **compared against a baseline setup** to evaluate its impact on performance and resource utilization.

---

## 🧬 Single-Objective GA (`ga/`)

### Algorithm Configuration

- **Type:** Single-objective Genetic Algorithm  
- **Encoding:**  
  - Number of replicas (1-10)
  - CPU limit per pod (0.1-2.0 cores)
  - Memory limit per pod (128-512 MB)
- **Selection:** Tournament selection (configurable size)
- **Crossover:** Uniform crossover (50% probability per gene)
- **Mutation:** Bounded random mutation with configurable rate
- **Elitism:** Enabled (top individual preserved across generations)
- **Evaluation:** Real execution on Kubernetes (not simulation)

### Fitness Function

The fitness score combines multiple weighted metrics normalized to [0, 1]:

- **Latency** (average, P95, P99) - Lower is better, normalized against SLA (default: 2000ms)
- **Resource Efficiency** - Combines productivity (throughput per resource), utilization quality, and penalties for throttling and memory peaks
- **Reliability** (success rate, error rate) - Higher success rate is better, errors are penalized

**Formula:**
```
fitness = (w1 × latency_score) +
          (w2 × efficiency_score) +
          (w3 × reliability_score)

where:
  latency_score = 0.2 × avg_score + 0.4 × p95_score + 0.4 × p99_score

  efficiency_score = (0.55 × productivity + 0.45 × utilization) × throttling_penalty × mem_peak_penalty
    productivity = 0.7 × cpu_efficiency + 0.3 × mem_efficiency
    cpu_efficiency = throughput / cpu_usage (normalized)
    mem_efficiency = throughput / mem_usage (normalized)

  reliability_score = success_rate × error_penalty
    error_penalty = 1 / (1 + 20 × error_rate)
```

**Default Weights (normalized to sum = 1.0):**
- Latency: 0.35
- Resource Efficiency: 0.40
- Reliability: 0.25

Weights are defined in `ga/fitness.py` (`FitnessWeights` class) and automatically normalized.

---

## 🎯 Multi-Objective NSGA-II (`nsga/`)

### Algorithm Configuration

- **Type:** NSGA-II (Deb et al., 2002) — non-dominated sorting + crowding distance
- **Encoding:** integer-valued `Genome(cpu_m, mem_mib, replicas)` over a configurable `SearchSpace` with discrete steps
- **Selection:** Binary tournament based on rank (Pareto front) and crowding distance
- **Crossover:** Uniform crossover per gene (probability `pc`, default 0.9)
- **Mutation:** Per-gene bounded mutation (probability `pm` per gene, default 0.1) with `repair()` clamping back into the search space
- **Survival:** Elitist (P ∪ Q) → next generation by filling Pareto fronts in order, breaking ties on crowding distance
- **Evaluation:** Real execution on Kubernetes via the same adapters (or synthetic mocks for offline runs)

### Objectives (all minimized)

| | Description | Formula |
|---|---|---|
| `f1` | Saturation — how pressured the pod is | `0.5 × cpu_throttle_rate + 0.5 × mem_peak_ratio` |
| `f2` | Provisioned resource cost | `replicas × (w_cpu × cpu_cores + w_mem × mem_gib)` |
| `f3` | Negative throughput (so minimization → maximize rps) | `-throughput_rps` |

Weights for `f1` and `f2` are configurable via `SaturationWeights` and `ResourceWeights` in `nsga/objectives.py`. Defaults preserve a 1:1 trade-off and can be overridden when constructing the pipeline.

Failed/timed-out evaluations get penalty objectives (`f1 = 10.0`, `f3 = 0.0`) so they are dominated by any real measurement.

### Adapter Architecture

The NSGA-II pipeline is decoupled from Kubernetes/Prometheus/Load testing through three small interfaces (`nsga/adapters/`):

- `K8sAdapter` — applies a `Genome` to a Deployment and waits for rollout
- `PrometheusAdapter` — collects `cpu_throttle_rate` and `mem_peak_ratio` over a time window
- `LoadAdapter` — runs the load test, returns throughput, latency percentiles, and time bounds

Each interface has a `Real*` implementation that delegates to the existing `integrations/` clients, plus a `Mock*` implementation that generates deterministic synthetic results — useful for unit tests and `make run-nsga-local` smoke runs without a cluster.

### Output Format

The runner writes to `NSGA_OUTPUT_DIR` (default `/results/nsga/`):

```text
nsga/
├── manifest.json                # Experiment parameters (search space, pc, pm, load_params)
├── generation_000.csv           # Full population per generation (with rank, crowding distance)
├── generation_001.csv
├── ...
├── pareto_front_000.csv         # Rank-0 individuals only, per generation
├── ...
├── cache.jsonl                  # Persistent cache keyed by genome + load_profile + load_params
├── summary.json                 # Cache stats, total time, final Pareto size
├── evaluations.csv              # Long-format: one row per evaluation across all generations
└── env.json                     # Python/git/k8s/hostname metadata for reproducibility
```

The cache key includes `load_params` (duration, concurrency, endpoint, etc.), so changing any of them automatically invalidates stale measurements.

---

## 🏗️ Repository Structure

```text
.
├── app/                        # Application under test (FastAPI-based)
│   ├── main.py                 # FastAPI endpoints (/mixed, /health, /metrics)
│   ├── metrics.py              # Prometheus metrics instrumentation
│   └── __init__.py
├── ga/                         # Single-objective Genetic Algorithm
│   ├── optimizer.py            # Main GA orchestrator
│   ├── fitness.py              # Fitness evaluation logic
│   ├── population.py           # Population management (selection, crossover, mutation)
│   ├── cache.py                # Evaluation result caching (MD5-based)
│   ├── config.py               # Configuration dataclasses (GA, K8s, Prometheus, LoadTest)
│   ├── exceptions.py           # Custom exceptions
│   ├── types.py                # Core types (Individual, FitnessMetrics, EvaluationResult)
│   └── tests/
│       └── load_test.py        # Load test implementation for GA
├── nsga/                       # Multi-objective NSGA-II
│   ├── domain.py               # Genome, RawMetrics, Objectives, Individual
│   ├── search_space.py         # Discrete search space + repair()
│   ├── operators.py            # Uniform crossover + per-gene mutation
│   ├── nsga2.py                # Fast non-dominated sort + crowding distance + selection
│   ├── objectives.py           # f1/f2/f3 + ResourceWeights/SaturationWeights
│   ├── evaluate.py             # EvaluatePipeline (apply → wait → load → prom → objectives)
│   ├── cache.py                # JSONL cache keyed by genome + load_profile + load_params
│   ├── storage.py              # Per-generation CSVs + Pareto front + summary
│   ├── runner.py               # NSGA2Runner (generation loop, elitism)
│   └── adapters/               # Decoupled K8s / Prometheus / Load adapters
│       ├── k8s_adapter.py      # K8sAdapter + RealK8sAdapter
│       ├── prometheus_adapter.py  # PrometheusAdapter + RealPrometheusAdapter
│       ├── load_adapter.py     # LoadAdapter + Real/Mock implementations
│       └── mock_adapters.py    # Synthetic K8s/Prom adapters for offline runs
├── load/                       # Load testing module
│   ├── load_test.py            # LoadTester class with warm-up support
│   ├── workload_profiles.py    # Workload patterns (sustained, burst, ramp-up, etc.)
│   ├── config.py               # Load test configuration
│   ├── exceptions.py           # Load test exceptions
│   └── main.py                 # Standalone load test entry point
├── integrations/               # External service integrations
│   ├── k8s_client.py           # Kubernetes API client (apply, patch, scale, rollout)
│   └── prometheus_client.py    # Prometheus query client (query_instant, query_range, query_range_max)
├── shared/                     # Shared utilities
│   ├── types.py                # GenericIndividual (used by adapters)
│   └── utils.py                # Logging, parsing, validation helpers
├── manifests/                  # Kubernetes manifests
│   ├── deployment-app-ga.yaml  # Application deployment
│   ├── service-app-ga.yaml     # Application service
│   ├── service-monitoring-app-ga.yaml  # ServiceMonitor for Prometheus
│   ├── ga-job.yaml             # GA Job definition
│   ├── nsga-job.yaml           # NSGA-II Job definition
│   ├── job-loadtest.yaml       # Standalone load test job
│   ├── service-account.yaml    # RBAC for GA / NSGA Jobs
│   ├── persistent-volume.yaml  # PV for results
│   └── pvc-reader.yaml         # PVC reader pod
├── scripts/                    # Utility scripts
│   ├── run_ga.py               # Entry point for GA execution
│   ├── run_nsga.py             # Entry point for NSGA-II execution (supports --mock)
│   ├── export_metrics.py       # Export Prometheus metrics to JSON
│   ├── test_*.py               # Various test scripts
│   └── __init__.py
├── results/                    # GA execution results
│   ├── results.json            # Detailed results with all individuals
│   ├── analyze_ga_results.py   # Analysis script with plotting
│   └── *.txt                   # Execution logs
├── docs/                       # Documentation
│   ├── kubernetes_connection_issues.md
│   ├── results_json_structure.md
│   ├── prometheus_query_range_implementation.md
│   ├── matplotlib_backend_fix.md
│   └── *.md                    # Various technical docs
├── dockerfile                  # Application container image
├── dockerfile.ga               # GA optimizer container image
├── dockerfile.nsga             # NSGA-II optimizer container image
├── dockerfile.loadtest         # Load test container image
├── requirements.txt            # Runtime Python dependencies
├── requirements-dev.txt        # Dev dependencies (pytest, mypy, black, LSP)
├── Makefile                    # Build and deployment commands
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites

- **Kubernetes cluster** (Minikube, Kind, or cloud provider)
- **kubectl** configured
- **Docker** for building images
- **Prometheus** installed in cluster (for metrics collection)
- **Python 3.11+** (for local development)

### 1. Build Container Images

```bash
# Build application image
docker build -t app-ga:latest -f dockerfile .

# Build GA optimizer image
docker build -t ga-optimizer:latest -f dockerfile.ga .

# Build NSGA-II optimizer image
docker build -t nsga-optimizer:latest -f dockerfile.nsga .

# Build load test image
docker build -t loadtest:latest -f dockerfile.loadtest .
```

> Tip: when using Minikube, the Makefile already wraps these commands —
> `make build-api`, `make build-ga`, `make build-nsga`, etc.

### 2. Deploy Application

```bash
# Apply Kubernetes manifests
kubectl apply -f manifests/service-account.yaml
kubectl apply -f manifests/persistent-volume.yaml
kubectl apply -f manifests/deployment-app-ga.yaml
kubectl apply -f manifests/service-app-ga.yaml
kubectl apply -f manifests/service-monitoring-app-ga.yaml

# Verify deployment
kubectl get pods -l app=app-ga
kubectl get svc app-ga
```

### 3. Run an Optimizer

Pick the algorithm you want to evaluate; both reuse the same Service Account and PVC.

**Single-objective GA**:

```bash
make run-ga                 # or: kubectl apply -f manifests/ga-job.yaml
make logs-ga                # or: kubectl logs -f job/ga-optimizer
```

**Multi-objective NSGA-II**:

```bash
make run-nsga               # or: kubectl apply -f manifests/nsga-job.yaml
make logs-nsga              # or: kubectl logs -f job/nsga-optimizer
```

**NSGA-II locally (no cluster, mock adapters)** — useful for smoke tests:

```bash
make run-nsga-local
# equivalente a: python -u scripts/run_nsga.py --mock --output-dir nsga_results
```

### 4. Analyze Results

**GA**:

```bash
# Copy results from cluster
kubectl cp <pvc-reader-pod>:/results/results.json ./results/results.json

# Run analysis script
python results/analyze_ga_results.py results/results.json

# View generated plots
ls results/results_analysis/
```

**NSGA-II**:

```bash
# Copy the whole NSGA output directory
kubectl cp <pvc-reader-pod>:/results/nsga ./nsga_results

# Inspect the final Pareto front (last generation)
ls nsga_results/pareto_front_*.csv | tail -1 | xargs cat

# Aggregate stats
cat nsga_results/summary.json
```

---

## ⚙️ Configuration

### Environment Variables

The GA behavior is fully configurable via environment variables in `manifests/ga-job.yaml`:

#### Genetic Algorithm Parameters

| Variable | Default | Description |
|----------|---------|-------------|
| `GA_POPULATION` | `6` | Number of individuals per generation |
| `GA_GENERATIONS` | `5` | Number of generations to evolve |
| `GA_MUTATION_RATE` | `0.2` | Probability of mutation (0.0-1.0) |
| `GA_CROSSOVER_RATE` | `0.8` | Probability of crossover (0.0-1.0) |
| `GA_ELITISM_COUNT` | `1` | Number of top individuals to preserve |
| `GA_TOURNAMENT_SIZE` | `2` | Tournament selection size |
| `GA_EVALUATION_DELAY` | `2` | Delay between evaluations (seconds) |
| `GA_SLA_LATENCY_MS` | `2000.0` | SLA latency threshold (milliseconds) |
| `GA_REQUIRE_PROMETHEUS_METRICS` | `false` | Fail evaluation if metrics unavailable |

#### Resource Bounds

| Variable | Default | Description |
|----------|---------|-------------|
| `GA_REPLICAS_MIN` | `1` | Minimum number of replicas |
| `GA_REPLICAS_MAX` | `6` | Maximum number of replicas |
| `GA_CPU_MIN` | `0.1` | Minimum CPU limit (cores) |
| `GA_CPU_MAX` | `4.0` | Maximum CPU limit (cores) |
| `GA_MEMORY_MIN` | `128` | Minimum memory limit (MB) |
| `GA_MEMORY_MAX` | `6000` | Maximum memory limit (MB) |

#### Fitness Weights

**Note:** Fitness weights are hardcoded in `ga/fitness.py` (`FitnessWeights` class) and automatically normalized:

| Component | Default Weight | Description |
|-----------|----------------|-------------|
| Latency | `0.35` | Weight for latency score (avg, P95, P99) |
| Resource Efficiency | `0.40` | Weight for efficiency score (productivity + utilization) |
| Reliability | `0.25` | Weight for reliability score (success rate, error penalty) |

To modify weights, edit the `FitnessWeights` dataclass in `ga/fitness.py`.

#### Load Test Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LOAD_TEST_DURATION` | `90` | Main test duration (seconds) |
| `LOAD_TEST_CONCURRENCY` | `20` | Number of concurrent workers |
| `LOAD_TEST_TIMEOUT` | `5` | Request timeout (seconds) |
| `LOAD_TEST_WARMUP_DURATION` | `10` | Warm-up duration (seconds) |
| `LOAD_TEST_WARMUP_CONCURRENCY` | `2` | Warm-up concurrency |
| `LOAD_TEST_PROFILE` | `""` | Workload profile (sustained, burst, etc.) |

#### Kubernetes Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `K8S_NAMESPACE` | `default` | Target namespace |
| `K8S_DEPLOYMENT_NAME` | `app-ga` | Target deployment name |
| `K8S_CONTAINER_NAME` | `app-ga` | Target container name |
| `APP_LABEL` | `app-ga` | Pod label selector |
| `APP_URL` | `http://app-ga.default.svc.cluster.local:8080` | Application URL for load testing |
| `K8S_WARMUP_TIME` | `10` | Warm-up time after rollout (seconds) |

#### Prometheus Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PROMETHEUS_URL` | `http://prometheus-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090` | Prometheus server URL |
| `PROM_QUERY_TIMEOUT` | `10` | Query timeout (seconds) |
| `PROM_RETRY_ATTEMPTS` | `3` | Max query retry attempts |
| `PROM_RETRY_DELAY` | `1.0` | Retry delay (seconds) |

### NSGA-II Environment Variables

The NSGA-II Job is configured via `manifests/nsga-job.yaml` and reuses the same `K8S_*`, `LOAD_TEST_*` and `PROMETHEUS_*` variables described above.
Algorithm-specific variables (all prefixed with `NSGA_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `NSGA_POPULATION` | `6` | Population size |
| `NSGA_GENERATIONS` | `5` | Number of generations |
| `NSGA_CROSSOVER_RATE` | `0.9` | Probability of crossover (`pc`) |
| `NSGA_MUTATION_RATE` | `0.1` | Per-gene mutation probability (`pm`) |
| `NSGA_SEED` | `42` | RNG seed (reproducibility) |
| `NSGA_STABILIZATION_S` | `5` | Seconds to wait after rollout before load test |
| `NSGA_OUTPUT_DIR` | `/results/nsga` | Output directory for CSVs and cache |
| `NSGA_MOCK` | `false` | If `true`, uses synthetic adapters (no cluster needed) |

Search space (CPU in millicores, memory in MiB):

| Variable | Default | Description |
|----------|---------|-------------|
| `NSGA_CPU_MIN` / `NSGA_CPU_MAX` / `NSGA_CPU_STEP` | `100` / `1800` / `100` | CPU bounds and discretization step |
| `NSGA_MEM_MIN` / `NSGA_MEM_MAX` / `NSGA_MEM_STEP` | `128` / `1024` / `128` | Memory bounds and step |
| `NSGA_REP_MIN` / `NSGA_REP_MAX` | `1` / `4` | Replica bounds |

> Defaults differ slightly between manifests/files vs. `scripts/run_nsga.py` (the script defaults are wider). The Job manifest applies the conservative bounds; for ad-hoc local runs you can override anything via env vars or `--mock`.

---

## 📊 Results Format

This section describes the **GA** (single-objective) result format. For NSGA-II, see the [Output Format](#output-format) under *Multi-Objective NSGA-II* — it produces per-generation CSVs and a Pareto front per generation rather than a single fitness leader.

The GA execution generates a comprehensive JSON file with:

### Top-Level Structure

```json
{
  "timestamp": "2026-02-01T03:37:47.116294",
  "execution_time_seconds": 4602.84,
  "status": "success",
  "config": { ... },
  "best_individual_overall": { ... },
  "generations": [ ... ],
  "summary": { ... }
}
```

### Generation Details

Each generation includes:
- **Statistics:** avg/max/min fitness, diversity, convergence
- **Best individual:** Configuration and fitness
- **All individuals:** Complete details for every individual evaluated

### Individual Details

For each individual:
```json
{
  "individual": {
    "replicas": 2,
    "cpu_limit": 1.7,
    "memory_limit": 239
  },
  "fitness": 0.85,
  "evaluation_time_seconds": 153.42,
  "error": null,
  "metrics": {
    "throughput": 125.3,
    "avg_latency": 0.15,
    "p50_latency": 0.12,
    "p95_latency": 0.28,
    "p99_latency": 0.45,
    "success_rate": 0.998,
    "error_rate": 0.002,
    "cpu_usage": 0.65,
    "memory_usage": 180,
    "cpu_throttling": 0.02
  }
}
```

See `docs/results_json_structure.md` for complete documentation.

---

## 📈 Analysis Tools

### Automated Analysis Script

```bash
python results/analyze_ga_results.py results/results.json
```

**Generates:**
- Summary statistics (console output)
- Evolution analysis (fitness trends, diversity)
- Best individuals per generation
- Most efficient configurations
- Performance plots (PNG files)

**Output plots:**
- `fitness_over_generations.png` - Fitness evolution
- `diversity_over_generations.png` - Population diversity
- `convergence_over_generations.png` - Convergence rate
- `latency_comparison.png` - Latency metrics (avg, P95, P99)
- `resource_usage.png` - CPU and memory usage

### Manual Analysis

```python
import json

with open("results/results.json") as f:
    data = json.load(f)

# Best configuration
best = data["best_individual_overall"]
print(f"Replicas: {best['replicas']}")
print(f"CPU: {best['cpu_limit']} cores")
print(f"Memory: {best['memory_limit']} MB")

# Evolution history
for gen in data["generations"]:
    print(f"Gen {gen['generation']}: fitness={gen['statistics']['max_fitness']:.3f}")
```

---

## 🧪 Testing

### Unit Tests

```bash
# Run all tests
python -m pytest

# Run specific test
python scripts/test_prometheus_client.py
python scripts/test_k8s_timeout.py
python scripts/test_mutation_simple.py
```

### Load Test Standalone

```bash
# Run load test independently
python load/main.py --url http://app-ga:8000/mixed --duration 60 --concurrency 10

# Or via Kubernetes Job
kubectl apply -f manifests/job-loadtest.yaml
kubectl logs -f job/loadtest-job
```

### Prometheus Query Test

```bash
# Test Prometheus connectivity and queries
python scripts/test_prometheus_client.py
```

---

## 🛠️ Development

### Local Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate  # Windows

# Runtime dependencies only
pip install -r requirements.txt

# Or runtime + dev tools (pytest, mypy, black, LSP)
pip install -r requirements-dev.txt

# Run application locally
uvicorn app.main:app --reload --port 8000

# Smoke test of NSGA-II without a cluster
python -u scripts/run_nsga.py --mock --output-dir nsga_results
```

### Code Structure

#### GA core modules

- **`ga/optimizer.py`**: Main GA orchestrator
  - Initializes population
  - Manages evolution loop
  - Handles checkpointing and recovery
  - Saves results

- **`ga/fitness.py`**: Fitness evaluation
  - Applies configuration to K8s
  - Runs load test
  - Collects Prometheus metrics
  - Calculates fitness score

- **`ga/population.py`**: Population management
  - Tournament selection
  - Uniform crossover
  - Bounded mutation
  - Diversity calculation

#### NSGA-II core modules

- **`nsga/runner.py`**: Generation loop, elitism `P ∪ Q`, persistence per generation
- **`nsga/nsga2.py`**: Fast non-dominated sort (O(M·N²)) + crowding distance + binary tournament
- **`nsga/objectives.py`**: `f1`/`f2`/`f3` with configurable `SaturationWeights` / `ResourceWeights`
- **`nsga/evaluate.py`**: `apply → wait → load → prom → objectives` pipeline with timeout/error handling
- **`nsga/cache.py`**: JSONL cache keyed by genome + load profile + serialized load params
- **`nsga/adapters/`**: Decoupling layer (Real* delegates to `integrations/`, Mock* for offline runs)

#### Shared infrastructure

- **`integrations/k8s_client.py`**: Kubernetes API
  - Apply/patch deployments
  - Scale replicas
  - Wait for rollout
  - Cleanup pending pods

- **`integrations/prometheus_client.py`**: Prometheus API
  - `query_instant`, `query_range`, `query_range_max` (used for memory peak)
  - Retry logic and caching

- **`load/load_test.py`**: Load testing
  - Concurrent request execution
  - Warm-up phase support
  - Latency percentile calculation
  - Thread-safe result aggregation

### Adding New Features

#### Custom Fitness Metric

1. Add metric collection in `ga/fitness.py`:
```python
new_metric = self.prometheus.get_custom_metric(...)
```

2. Add to `FitnessMetrics` dataclass in `ga/types.py`:
```python
@dataclass
class FitnessMetrics:
    # ... existing fields ...
    new_metric: float = 0.0
```

3. Update fitness calculation in `ga/fitness.py`:
```python
fitness_score += self.config.weight_new_metric * new_metric_score
```

#### Custom Workload Profile

1. Add profile in `load/workload_profiles.py`:
```python
def custom_pattern(t: float, duration: float) -> float:
    # Return concurrency multiplier (0.0-1.0) at time t
    return ...

PROFILES["custom"] = WorkloadProfile(
    name="custom",
    pattern_func=custom_pattern,
    max_concurrency=50
)
```

2. Use via environment variable:
```yaml
env:
  - name: LOAD_TEST_PROFILE
    value: "custom"
```

---

## 📚 Documentation

Detailed documentation available in `docs/`:

- **`results_json_structure.md`** - Complete results JSON schema
- **`prometheus_query_range_implementation.md`** - Prometheus integration details
- **`kubernetes_connection_issues.md`** - Troubleshooting K8s connectivity
- **`matplotlib_backend_fix.md`** - Fix for plotting issues
- **`env_vars_audit.md`** - Environment variable reference
- **`tournament_size_usage.md`** - Selection mechanism details

---

## 🐛 Troubleshooting

### GA Job Fails to Start

```bash
# Check job status
kubectl describe job ga-job

# Check pod logs
kubectl logs -f $(kubectl get pods -l job-name=ga-job -o name)

# Common issues:
# - Image pull errors: Verify image exists and is accessible
# - RBAC errors: Ensure service account has correct permissions
# - Config errors: Check environment variables in ga-job.yaml
```

### Prometheus Queries Return Empty

```bash
# Test Prometheus connectivity
kubectl exec -it <ga-pod> -- curl http://prometheus-k8s.monitoring.svc:9090/-/healthy

# Verify metrics exist
kubectl exec -it <ga-pod> -- curl 'http://prometheus-k8s.monitoring.svc:9090/api/v1/query?query=up{job="app-ga"}'

# Check ServiceMonitor
kubectl get servicemonitor -n default

# Common issues:
# - ServiceMonitor not created: Apply service-monitoring-app-ga.yaml
# - Wrong label selector: Verify labels match in deployment and servicemonitor
# - Prometheus not scraping: Check Prometheus targets UI
```

### Load Test Timeouts

```bash
# Increase timeout in ga-job.yaml
env:
  - name: LOAD_TEST_TIMEOUT
    value: "10"  # Increase from 5 to 10 seconds

# Verify application is responding
kubectl port-forward svc/app-ga 8000:8000
curl http://localhost:8000/health

# Common issues:
# - Application not ready: Increase K8S_ROLLOUT_TIMEOUT
# - Network issues: Check service and pod connectivity
# - Resource limits too low: Increase CPU/memory limits
```

### Analysis Script Errors

```bash
# Matplotlib backend error (Tkinter)
# Solution: Already fixed with matplotlib.use('Agg')

# Missing dependencies
pip install -r requirements.txt

# Invalid JSON
# Verify results.json is valid:
python -c "import json; json.load(open('results/results.json'))"
```

---

## 📄 License

This project is part of an undergraduate thesis and is provided for educational and research purposes.

---

## 👥 Authors

- **Student:** João Victor de Oliveira Silva
- **Advisor:** Lidiano A. N. Oliveira
- **Institution:** Universidade Federal Rural de Pernambuco
- **Year:** 2025

---

## 📖 Citation

If you use this work in your research, please cite:

```bibtex
@thesis{joao.oliveirasilva2025ga,
  title={Application of Genetic Algorithms for Resource Optimization in Kubernetes Environments},
  author={João Victor de Oliveira Silva},
  year={2025},
  school={Universidade Federal Rural de Pernambuco},
  type={Bachelor's Thesis}
}
```

---

## 🔗 Related Work

- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Genetic Algorithms - Introduction](https://en.wikipedia.org/wiki/Genetic_algorithm)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

---

## 📞 Contact

For questions or issues, please open an issue on the repository or contact [joao.oliveirasilva@ufrpe.br].
