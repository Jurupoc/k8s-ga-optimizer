"""
Adapter para Prometheus (stub para integração com código existente).
"""
from abc import ABC, abstractmethod
from nsga.domain import RawMetrics


class PrometheusAdapter(ABC):
    """
    Interface para coletar métricas do Prometheus.
    
    STUB: Implemente esta interface com seu código existente de Prometheus.
    """
    
    @abstractmethod
    def collect_metrics(
        self,
        deployment_name: str,
        duration_s: int = 60,
        wait_before_s: int = 10
    ) -> RawMetrics:
        """
        Coleta métricas do Prometheus após um período de observação.
        
        Args:
            deployment_name: Nome do deployment a ser monitorado
            duration_s: Duração da janela de observação em segundos
            wait_before_s: Tempo de espera antes de começar a coletar (warmup)
            
        Returns:
            RawMetrics com throughput_rps, cpu_throttle_rate, mem_peak_ratio
            
        Raises:
            Exception: Em caso de erro na consulta ao Prometheus
        """
        pass
    
    @abstractmethod
    def cleanup(self) -> None:
        """
        Limpeza de recursos, se necessário.
        """
        pass


class RealPrometheusAdapter(PrometheusAdapter):
    """
    Implementação real do adapter Prometheus (STUB para seu código).
    
    INSTRUÇÕES:
    1. Importe suas classes/funções existentes de integração com Prometheus
    2. Implemente collect_metrics() para consultar as métricas necessárias
    3. Calcule throughput_rps, cpu_throttle_rate, mem_peak_ratio
    4. Use seu código existente de prometheus_client ou requests
    
    Exemplo de implementação:
    
    ```python
    from integrations.prometheus_utils import PrometheusClient  # seu código
    
    def __init__(self, prometheus_url: str):
        self.client = PrometheusClient(prometheus_url)
    
    def collect_metrics(
        self,
        deployment_name: str,
        duration_s: int = 60,
        wait_before_s: int = 10
    ) -> RawMetrics:
        import time
        
        # Aguardar warmup
        time.sleep(wait_before_s)
        
        # Coletar métricas
        throughput = self.client.query_rate(
            f'http_requests_total{{deployment="{deployment_name}"}}',
            duration_s
        )
        
        cpu_throttle = self.client.query_avg(
            f'container_cpu_cfs_throttled_seconds_total{{pod=~"{deployment_name}.*"}}',
            duration_s
        )
        
        mem_peak_ratio = self.client.query_max(
            f'container_memory_working_set_bytes{{pod=~"{deployment_name}.*"}}',
            duration_s
        ) / self.client.query_limit(f'pod=~"{deployment_name}.*"')
        
        return RawMetrics(
            throughput_rps=throughput,
            cpu_throttle_rate=cpu_throttle,
            mem_peak_ratio=mem_peak_ratio
        )
    ```
    """
    
    def __init__(self, prometheus_url: str):
        """
        Inicializa o adapter com URL do Prometheus.
        
        Args:
            prometheus_url: URL do servidor Prometheus
        """
        self.prometheus_url = prometheus_url
        # TODO: Inicializar seu cliente Prometheus aqui
        raise NotImplementedError(
            "RealPrometheusAdapter é um stub. Implemente com seu código existente de Prometheus."
        )
    
    def collect_metrics(
        self,
        deployment_name: str,
        duration_s: int = 60,
        wait_before_s: int = 10
    ) -> RawMetrics:
        """Coleta métricas do Prometheus (STUB)."""
        raise NotImplementedError("Implemente com seu código Prometheus existente")
    
    def cleanup(self) -> None:
        """Limpeza (STUB)."""
        pass
