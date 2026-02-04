"""
Pipeline de avaliação de genomes.
"""
import time
from nsga.domain import Genome, EvaluationResult, EvaluationStatus
from nsga.objectives import calculate_objectives, penalty_objectives
from nsga.adapters.k8s_adapter import K8sAdapter
from nsga.adapters.prometheus_adapter import PrometheusAdapter


class EvaluatePipeline:
    """
    Pipeline para avaliar um genome aplicando no K8s e coletando métricas.
    
    Processo:
    1. Aplica config no K8s
    2. Aguarda rollout
    3. Coleta métricas do Prometheus
    4. Calcula objetivos
    5. Retorna resultado (OK/FAIL com penalidade se necessário)
    """
    
    def __init__(
        self,
        k8s_adapter: K8sAdapter,
        prometheus_adapter: PrometheusAdapter,
        deployment_name: str,
        rollout_timeout_s: int = 300,
        metrics_duration_s: int = 60,
        metrics_warmup_s: int = 10
    ):
        """
        Inicializa o pipeline de avaliação.
        
        Args:
            k8s_adapter: Adapter para Kubernetes
            prometheus_adapter: Adapter para Prometheus
            deployment_name: Nome do deployment a ser otimizado
            rollout_timeout_s: Timeout para rollout do K8s
            metrics_duration_s: Duração da janela de observação de métricas
            metrics_warmup_s: Tempo de warmup antes de coletar métricas
        """
        self.k8s = k8s_adapter
        self.prometheus = prometheus_adapter
        self.deployment_name = deployment_name
        self.rollout_timeout_s = rollout_timeout_s
        self.metrics_duration_s = metrics_duration_s
        self.metrics_warmup_s = metrics_warmup_s
    
    def evaluate(self, genome: Genome) -> EvaluationResult:
        """
        Avalia um genome completo.
        
        Args:
            genome: Configuração de recursos a ser avaliada
            
        Returns:
            EvaluationResult com status e objetivos
        """
        start_time = time.time()
        
        try:
            # 1. Aplicar config no K8s
            success = self.k8s.apply_config(genome, self.deployment_name)
            if not success:
                return self._failed_result(genome, time.time() - start_time)
            
            # 2. Aguardar rollout
            ready = self.k8s.wait_ready(self.deployment_name, self.rollout_timeout_s)
            if not ready:
                return self._timeout_result(genome, time.time() - start_time)
            
            # 3. Coletar métricas do Prometheus
            metrics = self.prometheus.collect_metrics(
                self.deployment_name,
                self.metrics_duration_s,
                self.metrics_warmup_s
            )
            
            # 4. Calcular objetivos
            objectives = calculate_objectives(genome, metrics)
            
            # 5. Retornar resultado OK
            eval_time = time.time() - start_time
            return EvaluationResult(
                genome=genome,
                status=EvaluationStatus.OK,
                raw_metrics=metrics,
                objectives=objectives,
                eval_time_s=eval_time
            )
            
        except Exception as e:
            # Em caso de exceção, retornar FAIL com penalidade
            print(f"Erro ao avaliar genome {genome}: {e}")
            return self._failed_result(genome, time.time() - start_time)
    
    def _failed_result(self, genome: Genome, eval_time_s: float) -> EvaluationResult:
        """
        Cria resultado com status FAIL e penalidade.
        
        Args:
            genome: Genome avaliado
            eval_time_s: Tempo de avaliação
            
        Returns:
            EvaluationResult com penalidade
        """
        objectives = penalty_objectives(genome)
        return EvaluationResult(
            genome=genome,
            status=EvaluationStatus.FAIL,
            raw_metrics=None,
            objectives=objectives,
            eval_time_s=eval_time_s
        )
    
    def _timeout_result(self, genome: Genome, eval_time_s: float) -> EvaluationResult:
        """
        Cria resultado com status TIMEOUT e penalidade.
        
        Args:
            genome: Genome avaliado
            eval_time_s: Tempo de avaliação
            
        Returns:
            EvaluationResult com penalidade
        """
        objectives = penalty_objectives(genome)
        return EvaluationResult(
            genome=genome,
            status=EvaluationStatus.TIMEOUT,
            raw_metrics=None,
            objectives=objectives,
            eval_time_s=eval_time_s
        )
    
    def cleanup(self) -> None:
        """Limpeza de recursos dos adapters."""
        self.k8s.cleanup()
        self.prometheus.cleanup()
