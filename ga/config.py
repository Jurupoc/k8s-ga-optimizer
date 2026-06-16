# ga/config.py
"""
Configurações centralizadas do GA.
"""

import os
from typing import Tuple
from dataclasses import dataclass


@dataclass
class GAParameters:
    """Parâmetros do algoritmo genético."""

    population_size: int = 6
    generations: int = 5
    mutation_rate: float = 0.3  # Aumentado de 0.2 para 0.3 (30% de chance)
    crossover_rate: float = 0.8
    elitism_count: int = 1
    tournament_size: int = 2
    seed: int = 42  # Seed do RNG para reprodutibilidade
    
    # Configurações de avaliação
    evaluation_delay: int = 2  # Delay entre avaliações (segundos)
    sla_latency_ms: float = 2000.0  # SLA de latência em milissegundos
    require_prometheus_metrics: bool = False  # Se True, falha avaliação se métricas não disponíveis

    # Limites dos parâmetros
    replicas_bounds: Tuple[int, int] = (1, 6)
    cpu_limit_bounds: Tuple[float, float] = (0.1, 2.0)
    memory_limit_bounds: Tuple[int, int] = (128, 1024)

    # Steps discretos do espaço de busca (alinha com NSGA-II quando definidos).
    # Quando ``> 0``, init/mutação/crossover são "snappados" ao grid:
    #   cpu_limit ∈ {cpu_min, cpu_min + cpu_step, ..., cpu_max}
    #   memory_limit ∈ {mem_min, mem_min + mem_step, ..., mem_max}
    # Use ``cpu_step=0.05`` e ``mem_step=128`` para combinar com o
    # ``cpu_step=50`` (millicores) e ``mem_step=128`` do NSGA-II — isso
    # garante a MESMA grade de configurações possíveis e habilita
    # comparação justa entre os dois algoritmos.
    # Default 0.0/0 mantém retrocompat com runs antigas (contínuo).
    cpu_step: float = 0.0
    mem_step: int = 0

    # Parâmetros do load test (relevantes p/ chave do cache; sem default)
    # Quando definidos, entram na chave do EvaluationCache para invalidar
    # automaticamente medições antigas se a carga mudar — alinhado com
    # ``nsga/cache.py``.
    load_profile: str = "default"
    load_duration: int = 60
    load_concurrency: int = 20
    load_timeout: int = 10
    load_warmup_duration: int = 10
    load_warmup_concurrency: int = 2
    load_endpoint: str = "/mixed"

    @classmethod
    def from_env(cls) -> "GAParameters":
        """Carrega configuração de variáveis de ambiente com validação."""
        # Carrega valores
        population_size = int(os.environ.get("GA_POPULATION", "6"))
        generations = int(os.environ.get("GA_GENERATIONS", "5"))
        mutation_rate = float(os.environ.get("GA_MUTATION_RATE", "0.2"))
        crossover_rate = float(os.environ.get("GA_CROSSOVER_RATE", "0.8"))
        elitism_count = int(os.environ.get("GA_ELITISM_COUNT", "1"))
        tournament_size = int(os.environ.get("GA_TOURNAMENT_SIZE", "2"))
        seed = int(os.environ.get("GA_SEED", "42"))
        evaluation_delay = int(os.environ.get("GA_EVALUATION_DELAY", "2"))
        sla_latency_ms = float(os.environ.get("GA_SLA_LATENCY_MS", "2000.0"))
        require_prometheus_metrics = os.environ.get("GA_REQUIRE_PROMETHEUS_METRICS", "false").lower() in ("1", "true", "yes")
        
        replicas_min = int(os.environ.get("GA_REPLICAS_MIN", "1"))
        replicas_max = int(os.environ.get("GA_REPLICAS_MAX", "6"))
        cpu_min = float(os.environ.get("GA_CPU_MIN", "0.1"))
        cpu_max = float(os.environ.get("GA_CPU_MAX", "4.0"))
        mem_min = int(os.environ.get("GA_MEMORY_MIN", "128"))
        mem_max = int(os.environ.get("GA_MEMORY_MAX", "6000"))

        # Steps do grid (0 = contínuo, retrocompat). Para alinhar com NSGA-II:
        # GA_CPU_STEP=0.05 (cores) ≡ NSGA_CPU_STEP=50 (millicores).
        cpu_step = float(os.environ.get("GA_CPU_STEP", "0.0"))
        mem_step = int(os.environ.get("GA_MEMORY_STEP", "0"))

        # Load params — entram na chave do cache (alinhamento com NSGA).
        # Defaults batem com run_ga.py + LoadConfig.from_env() para quem
        # não setar explicitamente.
        load_profile = os.environ.get("LOAD_TEST_PROFILE", "default") or "default"
        load_duration = int(os.environ.get("LOAD_TEST_DURATION", "60"))
        load_concurrency = int(os.environ.get("LOAD_TEST_CONCURRENCY", "20"))
        load_timeout = int(os.environ.get("LOAD_TEST_TIMEOUT", "10"))
        load_warmup_duration = int(os.environ.get("LOAD_TEST_WARMUP_DURATION", "10"))
        load_warmup_concurrency = int(os.environ.get("LOAD_TEST_WARMUP_CONCURRENCY", "2"))
        load_endpoint = os.environ.get("LOAD_TEST_ENDPOINT", "/mixed") or "/mixed"
        
        # Validações
        if population_size < 2:
            raise ValueError(f"GA_POPULATION deve ser >= 2, recebido: {population_size}")
        if generations < 1:
            raise ValueError(f"GA_GENERATIONS deve ser >= 1, recebido: {generations}")
        if not 0.0 <= mutation_rate <= 1.0:
            raise ValueError(f"GA_MUTATION_RATE deve estar entre 0.0 e 1.0, recebido: {mutation_rate}")
        if not 0.0 <= crossover_rate <= 1.0:
            raise ValueError(f"GA_CROSSOVER_RATE deve estar entre 0.0 e 1.0, recebido: {crossover_rate}")
        if elitism_count < 0 or elitism_count >= population_size:
            raise ValueError(f"GA_ELITISM_COUNT deve estar entre 0 e {population_size-1}, recebido: {elitism_count}")
        if tournament_size < 1 or tournament_size > population_size:
            raise ValueError(f"GA_TOURNAMENT_SIZE deve estar entre 1 e {population_size}, recebido: {tournament_size}")
        
        # Validações de bounds
        if replicas_min < 1 or replicas_max > 100 or replicas_min >= replicas_max:
            raise ValueError(f"Replicas bounds inválidos: min={replicas_min}, max={replicas_max}")
        if cpu_min < 0.01 or cpu_max > 100 or cpu_min >= cpu_max:
            raise ValueError(f"CPU bounds inválidos: min={cpu_min}, max={cpu_max}")
        if mem_min < 64 or mem_max > 100000 or mem_min >= mem_max:
            raise ValueError(f"Memory bounds inválidos: min={mem_min}, max={mem_max}")
        if cpu_step < 0.0 or cpu_step > (cpu_max - cpu_min):
            raise ValueError(
                f"GA_CPU_STEP invalido: {cpu_step} (deve estar em [0, {cpu_max - cpu_min}])"
            )
        if mem_step < 0 or mem_step > (mem_max - mem_min):
            raise ValueError(
                f"GA_MEMORY_STEP invalido: {mem_step} (deve estar em [0, {mem_max - mem_min}])"
            )
        
        # Validações de configurações de avaliação
        if evaluation_delay < 0:
            raise ValueError(f"GA_EVALUATION_DELAY deve ser >= 0, recebido: {evaluation_delay}")
        if sla_latency_ms <= 0:
            raise ValueError(f"GA_SLA_LATENCY_MS deve ser > 0, recebido: {sla_latency_ms}")
        
        return cls(
            population_size=population_size,
            generations=generations,
            mutation_rate=mutation_rate,
            crossover_rate=crossover_rate,
            elitism_count=elitism_count,
            tournament_size=tournament_size,
            seed=seed,
            evaluation_delay=evaluation_delay,
            sla_latency_ms=sla_latency_ms,
            require_prometheus_metrics=require_prometheus_metrics,
            replicas_bounds=(replicas_min, replicas_max),
            cpu_limit_bounds=(cpu_min, cpu_max),
            memory_limit_bounds=(mem_min, mem_max),
            cpu_step=cpu_step,
            mem_step=mem_step,
            load_profile=load_profile,
            load_duration=load_duration,
            load_concurrency=load_concurrency,
            load_timeout=load_timeout,
            load_warmup_duration=load_warmup_duration,
            load_warmup_concurrency=load_warmup_concurrency,
            load_endpoint=load_endpoint,
        )

    def cache_load_params(self) -> dict:
        """Parâmetros do load test que entram na chave do cache.

        IMPORTANTE: o set/ordem deve bater com ``NSGAConfig.load_params()``
        para permitir reuso cruzado de cache entre algoritmos quando o
        formato de chave for unificado (futuro), e para manter consistência
        documentacional.
        """
        return {
            "duration": self.load_duration,
            "concurrency": self.load_concurrency,
            "timeout": self.load_timeout,
            "warmup_duration": self.load_warmup_duration,
            "warmup_concurrency": self.load_warmup_concurrency,
            "endpoint": self.load_endpoint,
        }


@dataclass
class AppConfig:
    """Configuração da aplicação."""

    url: str = "http://app-ga.default.svc.cluster.local:8080"
    label: str = "app-ga"
    deployment_name: str = "app-ga"
    namespace: str = "default"
    container_name: str = "app-ga"
    warmup_time: int = 10  # Tempo de warm-up após rollout (segundos)

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Carrega configuração de variáveis de ambiente."""
        warmup_time = int(os.environ.get("K8S_WARMUP_TIME", "10"))
        
        # Validação
        if warmup_time < 0:
            raise ValueError(f"K8S_WARMUP_TIME deve ser >= 0, recebido: {warmup_time}")
        
        return cls(
            url=os.environ.get(
                "APP_URL", "http://app-ga.default.svc.cluster.local:8080"
            ),
            label=os.environ.get("APP_LABEL", "app-ga"),
            deployment_name=os.environ.get("K8S_DEPLOYMENT_NAME", "app-ga"),
            namespace=os.environ.get("K8S_NAMESPACE", "default"),
            container_name=os.environ.get("K8S_CONTAINER_NAME", "app-ga"),
            warmup_time=warmup_time,
        )


@dataclass
class PrometheusConfig:
    """Configuração do Prometheus."""

    url: str = (
        "http://prometheus-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090"
    )
    query_timeout: int = 10
    retry_attempts: int = 3
    retry_delay: float = 1.0

    @classmethod
    def from_env(cls) -> "PrometheusConfig":
        """Carrega configuração de variáveis de ambiente."""
        return cls(
            url=os.environ.get(
                "PROMETHEUS_URL",
                "http://prometheus-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090",
            ),
            query_timeout=int(os.environ.get("PROM_QUERY_TIMEOUT", "10")),
            retry_attempts=int(os.environ.get("PROM_RETRY_ATTEMPTS", "3")),
            retry_delay=float(os.environ.get("PROM_RETRY_DELAY", "1.0")),
        )
