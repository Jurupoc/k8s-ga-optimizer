"""
Mock adapters para testes sem cluster real.
"""
import time
import random
import math
from nsga.domain import Genome, RawMetrics
from nsga.adapters.k8s_adapter import K8sAdapter
from nsga.adapters.prometheus_adapter import PrometheusAdapter


class MockK8sAdapter(K8sAdapter):
    """
    Mock do adapter K8s para testes.
    Simula aplicação de config e rollout sem cluster real.
    """
    
    def __init__(self, namespace: str = "default", apply_delay_s: float = 2.0):
        """
        Inicializa o mock adapter.
        
        Args:
            namespace: Namespace simulado
            apply_delay_s: Delay simulado para aplicação de config
        """
        self.namespace = namespace
        self.apply_delay_s = apply_delay_s
        self.current_config = None
    
    def apply_config(self, genome: Genome, deployment_name: str) -> bool:
        """
        Simula aplicação de configuração no K8s.
        
        Args:
            genome: Configuração de recursos
            deployment_name: Nome do deployment
            
        Returns:
            True (sempre sucesso no mock)
        """
        time.sleep(self.apply_delay_s)
        self.current_config = genome
        return True
    
    def wait_ready(self, deployment_name: str, timeout_s: int = 300) -> bool:
        """
        Simula espera por rollout.
        
        Args:
            deployment_name: Nome do deployment
            timeout_s: Timeout em segundos
            
        Returns:
            True (sempre pronto no mock)
        """
        # Simular tempo de rollout proporcional ao número de réplicas
        if self.current_config:
            rollout_time = min(5.0 + self.current_config.replicas * 0.5, timeout_s)
            time.sleep(rollout_time)
        return True
    
    def cleanup(self) -> None:
        """Limpeza (nada a fazer no mock)."""
        pass


class MockPrometheusAdapter(PrometheusAdapter):
    """
    Mock do adapter Prometheus para testes.
    Gera métricas sintéticas baseadas no genome com comportamento realista.
    """
    
    def __init__(self, seed: int = 42):
        """
        Inicializa o mock adapter.
        
        Args:
            seed: Seed para geração de métricas determinísticas
        """
        self.rng = random.Random(seed)
    
    def collect_metrics(
        self,
        deployment_name: str,
        duration_s: int = 60,
        wait_before_s: int = 10
    ) -> RawMetrics:
        """
        Gera métricas sintéticas baseadas na configuração atual.
        
        Comportamento simulado:
        - Throughput aumenta com replicas e recursos, mas satura
        - CPU throttle aumenta se CPU for baixo
        - Mem peak aumenta se memória for baixa
        - Ruído leve para evitar empates
        
        Args:
            deployment_name: Nome do deployment (não usado no mock)
            duration_s: Duração da observação (não usado no mock)
            wait_before_s: Tempo de warmup (simulado)
            
        Returns:
            RawMetrics sintéticas
        """
        # Simular warmup
        time.sleep(min(wait_before_s * 0.1, 1.0))  # 10% do tempo real
        
        # Obter configuração do deployment_name (assumir que está no formato "dep-cpu-mem-rep")
        # Para o mock, vamos usar valores padrão e adicionar variação
        # Na prática, o evaluate.py passa o genome, então usamos heurísticas
        
        # Valores base (assumir configuração média)
        base_cpu_m = 500
        base_mem_mib = 512
        base_replicas = 3
        
        # Tentar extrair do nome do deployment (formato: "app-{cpu}-{mem}-{rep}")
        try:
            parts = deployment_name.split('-')
            if len(parts) >= 4:
                base_cpu_m = int(parts[1])
                base_mem_mib = int(parts[2])
                base_replicas = int(parts[3])
        except:
            pass
        
        # Calcular métricas sintéticas
        throughput_rps = self._calculate_throughput(base_cpu_m, base_mem_mib, base_replicas)
        cpu_throttle_rate = self._calculate_cpu_throttle(base_cpu_m, base_replicas)
        mem_peak_ratio = self._calculate_mem_peak(base_mem_mib)
        
        return RawMetrics(
            throughput_rps=throughput_rps,
            cpu_throttle_rate=cpu_throttle_rate,
            mem_peak_ratio=mem_peak_ratio
        )
    
    def _calculate_throughput(self, cpu_m: int, mem_mib: int, replicas: int) -> float:
        """
        Calcula throughput sintético.
        
        Modelo:
        - Aumenta com replicas (linear até um ponto)
        - Aumenta com CPU e memória (com saturação)
        - Ruído leve
        """
        # Capacidade por réplica (satura em ~1000 millicores e ~1024 MiB)
        cpu_factor = min(cpu_m / 1000.0, 1.0)
        mem_factor = min(mem_mib / 1024.0, 1.0)
        capacity_per_replica = 100.0 * cpu_factor * mem_factor
        
        # Throughput total com saturação em ~8 réplicas
        replica_factor = replicas * (1.0 - 0.05 * max(0, replicas - 8))
        base_throughput = capacity_per_replica * replica_factor
        
        # Adicionar ruído (±5%)
        noise = self.rng.uniform(0.95, 1.05)
        
        return max(10.0, base_throughput * noise)
    
    def _calculate_cpu_throttle(self, cpu_m: int, replicas: int) -> float:
        """
        Calcula taxa de throttling de CPU.
        
        Modelo:
        - Aumenta se CPU for baixo
        - Diminui com mais CPU
        - Ruído leve
        """
        # Throttle é alto se CPU < 500m, baixo se CPU > 1000m
        if cpu_m < 500:
            base_throttle = 0.3 + (500 - cpu_m) / 500.0 * 0.4
        elif cpu_m < 1000:
            base_throttle = 0.1 + (1000 - cpu_m) / 500.0 * 0.2
        else:
            base_throttle = 0.05
        
        # Adicionar ruído (±10%)
        noise = self.rng.uniform(0.9, 1.1)
        
        return max(0.0, min(1.0, base_throttle * noise))
    
    def _calculate_mem_peak(self, mem_mib: int) -> float:
        """
        Calcula razão de pico de memória.
        
        Modelo:
        - Aumenta se memória for baixa
        - Diminui com mais memória
        - Ruído leve
        """
        # Peak ratio é alto se mem < 512 MiB, baixo se mem > 1024 MiB
        if mem_mib < 512:
            base_peak = 0.7 + (512 - mem_mib) / 512.0 * 0.25
        elif mem_mib < 1024:
            base_peak = 0.5 + (1024 - mem_mib) / 512.0 * 0.2
        else:
            base_peak = 0.4
        
        # Adicionar ruído (±10%)
        noise = self.rng.uniform(0.9, 1.1)
        
        return max(0.0, min(1.0, base_peak * noise))
    
    def cleanup(self) -> None:
        """Limpeza (nada a fazer no mock)."""
        pass


def create_mock_adapters(seed: int = 42) -> tuple[MockK8sAdapter, MockPrometheusAdapter]:
    """
    Cria adapters mock para testes.
    
    Args:
        seed: Seed para geração determinística
        
    Returns:
        Tupla (k8s_adapter, prometheus_adapter)
    """
    k8s = MockK8sAdapter()
    prom = MockPrometheusAdapter(seed=seed)
    return k8s, prom
