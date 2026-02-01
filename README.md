# Genetic Algorithm–Based Resource Optimization in Kubernetes

This repository contains the full implementation and experimental setup for the undergraduate thesis:

**"Application of Genetic Algorithms for Resource Optimization in Kubernetes Environments"**

The project investigates the use of a **single-objective Genetic Algorithm (GA)** to automatically discover efficient Kubernetes cluster configurations—specifically **replica count, CPU limits, and memory limits**—for a given application workload.  
The approach combines **load testing**, **Prometheus-based metrics**, and **direct interaction with the Kubernetes API** to evaluate and evolve configurations under realistic execution conditions.

---

## 📖 Overview

Kubernetes provides automated deployment and scaling mechanisms for containerized applications, but **resource configuration is still commonly performed manually or via static rules**. This can lead to inefficient resource usage, performance degradation, or saturation under varying workloads.

This project proposes a **Genetic Algorithm–driven optimization loop** that:

1. **Applies** a candidate configuration to a running Kubernetes Deployment
2. **Executes** a controlled load test against the application (90s duration + 10s warm-up)
3. **Collects** performance and resource metrics from Prometheus (CPU, memory, throttling)
4. **Computes** a fitness score based on throughput, latency, efficiency, and reliability
5. **Evolves** the population toward improved configurations using tournament selection, crossover, and mutation

The final configuration discovered by the GA is then **compared against a baseline setup** to evaluate its impact on performance and resource utilization.

---

## 🧬 Genetic Algorithm Summary

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

The fitness score combines multiple weighted metrics:

- **Throughput** (requests/second)
- **Latency** (average, P50, P95, P99)
- **Resource Efficiency** (CPU and memory utilization vs. throughput)
- **Reliability** (success rate, error rate)
- **CPU Throttling** (penalty for resource contention)

**Formula:**
```
fitness = (w1 × throughput_score) +
          (w2 × latency_score) +
          (w3 × efficiency_score) +
          (w4 × reliability_score) -
          (w5 × throttling_penalty)
```

All weights are configurable via environment variables.

---

## 🏗️ Repository Structure

```text
.
├── app/                        # Application under test (FastAPI-based)
│   ├── main.py                 # FastAPI endpoints (/mixed, /health, /metrics)
│   ├── metrics.py              # Prometheus metrics instrumentation
│   └── __init__.py
├── ga/                         # Genetic Algorithm implementation
│   ├── optimizer.py            # Main GA orchestrator
│   ├── fitness.py              # Fitness evaluation logic
│   ├── population.py           # Population management (selection, crossover, mutation)
│   ├── cache.py                # Evaluation result caching (MD5-based)
│   ├── config.py               # Configuration dataclasses (GA, K8s, Prometheus, LoadTest)
│   ├── exceptions.py           # Custom exceptions
│   ├── types.py                # Core types (Individual, FitnessMetrics, EvaluationResult)
│   └── tests/
│       └── load_test.py        # Load test implementation for GA
├── load/                       # Load testing module
│   ├── load_test.py            # LoadTester class with warm-up support
│   ├── workload_profiles.py    # Workload patterns (sustained, burst, ramp-up, etc.)
│   ├── config.py               # Load test configuration
│   ├── exceptions.py           # Load test exceptions
│   └── main.py                 # Standalone load test entry point
├── integrations/               # External service integrations
│   ├── k8s_client.py           # Kubernetes API client (apply, patch, scale, rollout)
│   └── prometheus_client.py    # Prometheus query client (query_instant, query_range)
├── shared/                     # Shared utilities
│   └── utils.py                # Logging, parsing, validation helpers
├── manifests/                  # Kubernetes manifests
│   ├── deployment-app-ga.yaml  # Application deployment
│   ├── service-app-ga.yaml     # Application service
│   ├── service-monitoring-app-ga.yaml  # ServiceMonitor for Prometheus
│   ├── ga-job.yaml             # GA Job definition
│   ├── job-loadtest.yaml       # Standalone load test job
│   ├── service-account.yaml    # RBAC for GA Job
│   ├── persistent-volume.yaml  # PV for results
│   └── pvc-reader.yaml         # PVC reader pod
├── scripts/                    # Utility scripts
│   ├── run_ga.py               # Main entry point for GA execution
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
├── dockerfile.loadtest         # Load test container image
├── requirements.txt            # Python dependencies
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

# Build load test image
docker build -t loadtest:latest -f dockerfile.loadtest .
```

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

### 3. Run Genetic Algorithm

```bash
# Apply GA Job
kubectl apply -f manifests/ga-job.yaml

# Monitor execution
kubectl logs -f job/ga-job

# Check results
kubectl exec -it <pvc-reader-pod> -- cat /results/results.json
```

### 4. Analyze Results

```bash
# Copy results from cluster
kubectl cp <pvc-reader-pod>:/results/results.json ./results/results.json

# Run analysis script
python results/analyze_ga_results.py results/results.json

# View generated plots
ls results/results_analysis/
```

---

## ⚙️ Configuration

### Environment Variables

The GA behavior is fully configurable via environment variables in `manifests/ga-job.yaml`:

#### Genetic Algorithm Parameters

| Variable | Default | Description |
|----------|---------|-------------|
| `GA_POPULATION_SIZE` | `6` | Number of individuals per generation |
| `GA_GENERATIONS` | `5` | Number of generations to evolve |
| `GA_MUTATION_RATE` | `0.2` | Probability of mutation (0.0-1.0) |
| `GA_CROSSOVER_RATE` | `0.8` | Probability of crossover (0.0-1.0) |
| `GA_ELITISM_COUNT` | `1` | Number of top individuals to preserve |
| `GA_TOURNAMENT_SIZE` | `3` | Tournament selection size |

#### Resource Bounds

| Variable | Default | Description |
|----------|---------|-------------|
| `GA_MIN_REPLICAS` | `1` | Minimum number of replicas |
| `GA_MAX_REPLICAS` | `10` | Maximum number of replicas |
| `GA_MIN_CPU` | `0.1` | Minimum CPU limit (cores) |
| `GA_MAX_CPU` | `2.0` | Maximum CPU limit (cores) |
| `GA_MIN_MEMORY` | `128` | Minimum memory limit (MB) |
| `GA_MAX_MEMORY` | `512` | Maximum memory limit (MB) |

#### Fitness Weights

| Variable | Default | Description |
|----------|---------|-------------|
| `GA_WEIGHT_THROUGHPUT` | `1.0` | Weight for throughput score |
| `GA_WEIGHT_LATENCY` | `1.0` | Weight for latency score |
| `GA_WEIGHT_EFFICIENCY` | `0.5` | Weight for efficiency score |
| `GA_WEIGHT_RELIABILITY` | `1.0` | Weight for reliability score |
| `GA_WEIGHT_THROTTLING` | `0.3` | Weight for throttling penalty |

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
| `K8S_LABEL_SELECTOR` | `app=app-ga` | Pod label selector |
| `K8S_ROLLOUT_TIMEOUT` | `300` | Rollout timeout (seconds) |
| `K8S_API_TIMEOUT` | `60` | API request timeout (seconds) |
| `K8S_MAX_RETRIES` | `3` | Max API retry attempts |

#### Prometheus Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PROMETHEUS_URL` | `http://prometheus-k8s.monitoring.svc:9090` | Prometheus server URL |
| `PROMETHEUS_TIMEOUT` | `30` | Query timeout (seconds) |
| `PROMETHEUS_MAX_RETRIES` | `3` | Max query retry attempts |
| `PROMETHEUS_RETRY_DELAY` | `2` | Retry delay (seconds) |
| `PROMETHEUS_CACHE_TTL` | `300` | Cache TTL (seconds) |

---

## 📊 Results Format

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

# Install dependencies
pip install -r requirements.txt

# Run application locally
uvicorn app.main:app --reload --port 8000
```

### Code Structure

#### Core Modules

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

- **`integrations/k8s_client.py`**: Kubernetes API
  - Apply/patch deployments
  - Scale replicas
  - Wait for rollout
  - Cleanup pending pods

- **`integrations/prometheus_client.py`**: Prometheus API
  - Query instant metrics
  - Query range metrics
  - Retry logic
  - Result caching

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

- **Student:** [Your Name]
- **Advisor:** [Advisor Name]
- **Institution:** [University Name]
- **Year:** 2025

---

## 📖 Citation

If you use this work in your research, please cite:

```bibtex
@thesis{yourname2025ga,
  title={Application of Genetic Algorithms for Resource Optimization in Kubernetes Environments},
  author={Your Name},
  year={2025},
  school={University Name},
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

For questions or issues, please open an issue on the repository or contact [your.email@university.edu].
