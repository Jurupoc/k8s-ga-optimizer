"""
Adapter para Kubernetes (stub para integração com código existente).
"""
from abc import ABC, abstractmethod
from nsga.domain import Genome
from integrations import KubernetesClient  
from shared.types import GenericIndividual


class K8sAdapter(ABC):
    """
    Interface para aplicar configurações no Kubernetes e aguardar rollout.
    
    STUB: Implemente esta interface com seu código existente de K8s.
    """
    
    @abstractmethod
    def apply_config(self, genome: Genome, deployment_name: str) -> bool:
        """
        Aplica a configuração de recursos no deployment do Kubernetes.
        
        Args:
            genome: Configuração de recursos (cpu_m, mem_mib, replicas)
            deployment_name: Nome do deployment a ser atualizado
            
        Returns:
            True se aplicado com sucesso, False caso contrário
            
        Raises:
            Exception: Em caso de erro na comunicação com K8s
        """
        pass
    
    @abstractmethod
    def wait_ready(self, deployment_name: str, timeout_s: int = 300) -> bool:
        """
        Aguarda até que o deployment esteja pronto (rollout completo).
        
        Args:
            deployment_name: Nome do deployment
            timeout_s: Timeout em segundos
            
        Returns:
            True se ficou pronto, False se timeout
            
        Raises:
            Exception: Em caso de erro na comunicação com K8s
        """
        pass
    
    @abstractmethod
    def cleanup(self) -> None:
        """
        Limpeza de recursos, se necessário.
        """
        pass


class RealK8sAdapter(K8sAdapter):
    """
    Implementação real do adapter K8s (STUB para seu código).
    
    INSTRUÇÕES:
    1. Importe suas classes/funções existentes de integração com K8s
    2. Implemente apply_config() para atualizar o deployment com os recursos do genome
    3. Implemente wait_ready() para aguardar o rollout
    4. Use seu código existente de kubernetes.client ou kubectl
    
    Exemplo de implementação:
    
    ```python
    from integrations.k8s_manager import K8sManager  # seu código
    
    def __init__(self, namespace: str = "default"):
        self.k8s = K8sManager()
        self.namespace = namespace
    
    def apply_config(self, genome: Genome, deployment_name: str) -> bool:
        # Atualizar deployment com genome.cpu_m, genome.mem_mib, genome.replicas
        return self.k8s.update_deployment(
            name=deployment_name,
            namespace=self.namespace,
            cpu_millicores=genome.cpu_m,
            memory_mib=genome.mem_mib,
            replicas=genome.replicas
        )
    
    def wait_ready(self, deployment_name: str, timeout_s: int = 300) -> bool:
        return self.k8s.wait_for_rollout(deployment_name, self.namespace, timeout_s)
    ```
    """
    
    def __init__(self, namespace: str = "default"):
        """
        Inicializa o adapter com namespace do K8s.
        
        Args:
            namespace: Namespace do Kubernetes
        """
        self.namespace = namespace
        self.k8s = KubernetesClient()
    
    def apply_config(self, genome: Genome, deployment_name: str) -> bool:
        """Aplica configuração no K8s."""
        self.k8s.apply_configuration(self._convert_to_individual(genome), False)
        return True
    
    def wait_ready(self, deployment_name: str, timeout_s: int = 300) -> bool:
        """Aguarda rollout (STUB)."""
        return self.k8s.wait_for_rollout(timeout_s)
    
    def cleanup(self) -> None:
        """Limpeza (STUB)."""
        pass
        
    def _convert_to_individual(self, genome: Genome) -> GenericIndividual:
        """Converte deployment em GenericIndividual."""
        return GenericIndividual(
            cpu_limit=genome.cpu_m/1000,
            memory_limit=genome.mem_mib,
            replicas=genome.replicas
        )