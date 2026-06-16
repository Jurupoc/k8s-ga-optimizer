"""
Adapter para Kubernetes — interface abstrata e implementação real.
"""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from typing_extensions import override

from nsga.domain import Genome

if TYPE_CHECKING:
    from integrations.k8s_client import KubernetesClient


class K8sAdapter(ABC):
    """Interface para aplicar configurações no Kubernetes e aguardar rollout."""

    @abstractmethod
    def apply_config(self, genome: Genome, deployment_name: str) -> bool:
        """
        Aplica a configuração de recursos no deployment do Kubernetes.

        Args:
            genome: Configuração de recursos (cpu_m, mem_mib, replicas)
            deployment_name: Nome do deployment a ser atualizado

        Returns:
            True se aplicado com sucesso, False caso contrário
        """
        ...

    @abstractmethod
    def wait_ready(self, deployment_name: str, timeout_s: int = 300) -> bool:
        """
        Aguarda até que o deployment esteja pronto (rollout completo).

        Args:
            deployment_name: Nome do deployment
            timeout_s: Timeout em segundos

        Returns:
            True se ficou pronto, False se timeout
        """
        ...

    @abstractmethod
    def cleanup(self) -> None:
        """Limpeza de recursos, se necessário."""
        ...


class RealK8sAdapter(K8sAdapter):
    """
    Implementação real que delega para o KubernetesClient existente.
    """

    def __init__(self, namespace: str = "default"):
        self.namespace: str = namespace
        self._k8s: "KubernetesClient | None" = None

    @property
    def k8s(self) -> "KubernetesClient":
        if self._k8s is None:
            from integrations import KubernetesClient
            self._k8s = KubernetesClient()
        return self._k8s

    @override
    def apply_config(self, genome: Genome, deployment_name: str) -> bool:
        """Aplica configuração no K8s."""
        from ga.types import Individual

        individual = Individual(
            replicas=genome.replicas,
            cpu_limit=genome.cpu_m / 1000,
            memory_limit=genome.mem_mib,
        )
        self.k8s.apply_configuration(individual, False)
        return True

    @override
    def wait_ready(self, deployment_name: str, timeout_s: int = 300) -> bool:
        """Aguarda rollout."""
        return self.k8s.wait_for_rollout(timeout_s)

    @override
    def cleanup(self) -> None:
        pass
