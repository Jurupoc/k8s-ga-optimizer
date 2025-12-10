# integrations/k8s_client.py
"""
Cliente robusto para integração com Kubernetes.
Inclui validação, rollback automático, dry-run e espera confiável de rollout.
"""
import os
import time
import copy
from typing import Dict, Optional, List
from kubernetes import client, config
from kubernetes.client.rest import ApiException

from ga.exceptions import KubernetesError, ConfigurationError
from ga.config import AppConfig
from ga.types import Individual
from ga.utils import log


class KubernetesClient:
    """
    Cliente Kubernetes com validação, rollback e operações seguras.
    """

    def __init__(self, app_config: Optional[AppConfig] = None):
        """
        Inicializa o cliente Kubernetes.

        Args:
            app_config: Configuração da aplicação (default: carrega de env)
        """
        self.config = app_config or AppConfig.from_env()
        self.dry_run = os.environ.get("GA_DRY_RUN", "false").lower() in ("1", "true", "yes")
        self.rollout_timeout = int(os.environ.get("K8S_ROLLOUT_TIMEOUT", "120"))
        self._api: Optional[client.AppsV1Api] = None
        self._last_config: Optional[Individual] = None  # Para rollback

    def _get_api(self) -> client.AppsV1Api:
        """Obtém ou cria a API do Kubernetes."""
        if self._api is None:
            try:
                config.load_kube_config()
                log("Loaded kubeconfig from local environment")
            except Exception:
                try:
                    config.load_incluster_config()
                    log("Loaded in-cluster kube config")
                except Exception as e:
                    log(f"Could not load kube config: {e}", level="error")
                    raise KubernetesError(f"Failed to load Kubernetes config: {e}") from e

            self._api = client.AppsV1Api()
        return self._api

    def _validate_individual(self, individual: Individual) -> None:
        """
        Valida um indivíduo antes de aplicar.

        Args:
            individual: Indivíduo a validar

        Raises:
            ConfigurationError: Se a configuração for inválida
        """
        if individual.replicas < 1 or individual.replicas > 100:
            raise ConfigurationError(f"Invalid replicas: {individual.replicas} (must be 1-100)")

        if individual.cpu_limit < 0.01 or individual.cpu_limit > 100:
            raise ConfigurationError(f"Invalid CPU limit: {individual.cpu_limit} (must be 0.01-100 cores)")

        if individual.memory_limit < 64 or individual.memory_limit > 100000:
            raise ConfigurationError(f"Invalid memory limit: {individual.memory_limit} (must be 64-100000 MB)")

    def _get_current_deployment(self) -> Optional[client.V1Deployment]:
        """Obtém o deployment atual."""
        try:
            api = self._get_api()
            return api.read_namespaced_deployment(
                name=self.config.deployment_name,
                namespace=self.config.namespace
            )
        except ApiException as e:
            log(f"Failed to get current deployment: {e}", level="warning")
            return None

    def _save_current_config(self) -> None:
        """Salva a configuração atual para possível rollback."""
        deployment = self._get_current_deployment()
        if deployment:
            spec = deployment.spec
            template = spec.template
            container = template.spec.containers[0] if template.spec.containers else None

            if container and container.resources:
                limits = container.resources.limits or {}
                cpu_str = limits.get("cpu", "0")
                mem_str = limits.get("memory", "0Mi")

                # Converte CPU (ex: "500m" -> 0.5)
                cpu_cores = float(cpu_str.rstrip("m")) / 1000 if cpu_str.endswith("m") else float(cpu_str)

                # Converte memória (ex: "256Mi" -> 256)
                mem_mb = int(mem_str.rstrip("Mi")) if mem_str.endswith("Mi") else int(mem_str.rstrip("M"))

                self._last_config = Individual(
                    replicas=spec.replicas or 1,
                    cpu_limit=cpu_cores,
                    memory_limit=mem_mb,
                    container_name=container.name
                )
                log(f"Saved current config for rollback: {self._last_config}")

    def scale_deployment(self, replicas: int) -> None:
        """
        Escala o deployment.

        Args:
            replicas: Número de réplicas desejadas

        Raises:
            KubernetesError: Se a operação falhar
        """
        replicas = int(replicas)
        log(f"Scaling deployment {self.config.deployment_name} to {replicas} replicas")

        if self.dry_run:
            log("(dry-run) scale skipped")
            return

        try:
            api = self._get_api()
            api.patch_namespaced_deployment_scale(
                name=self.config.deployment_name,
                namespace=self.config.namespace,
                body={"spec": {"replicas": replicas}}
            )
            log(f"✅ Deployment scaled to {replicas} replicas")
        except ApiException as e:
            raise KubernetesError(f"Failed to scale deployment: {e}") from e

    def patch_resources(self, individual: Individual) -> None:
        """
        Aplica patch de recursos (CPU e memória).

        Args:
            individual: Indivíduo com configuração de recursos

        Raises:
            KubernetesError: Se a operação falhar
        """
        cpu_m = f"{int(individual.cpu_limit * 1000)}m"
        mem = f"{int(individual.memory_limit)}Mi"
        container_name = individual.container_name or self.config.container_name

        patch = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": container_name,
                                "resources": {
                                    "requests": {"cpu": cpu_m, "memory": mem},
                                    "limits": {"cpu": cpu_m, "memory": mem}
                                }
                            }
                        ]
                    }
                }
            }
        }

        log(f"Patching resources for container {container_name}: CPU={cpu_m}, Memory={mem}")

        if self.dry_run:
            log("(dry-run) patch skipped")
            return

        try:
            api = self._get_api()
            api.patch_namespaced_deployment(
                name=self.config.deployment_name,
                namespace=self.config.namespace,
                body=patch
            )
            log(f"✅ Resources patched: CPU={cpu_m}, Memory={mem}")
        except ApiException as e:
            raise KubernetesError(f"Failed to patch resources: {e}") from e

    def apply_configuration(self, individual: Individual, save_for_rollback: bool = True) -> None:
        """
        Aplica configuração completa (réplicas + recursos).

        Args:
            individual: Indivíduo com configuração completa
            save_for_rollback: Se True, salva config atual para rollback

        Raises:
            ConfigurationError: Se a configuração for inválida
            KubernetesError: Se a operação falhar
        """
        self._validate_individual(individual)

        if save_for_rollback:
            self._save_current_config()

        try:
            # Aplica escala primeiro
            self.scale_deployment(individual.replicas)

            # Depois aplica recursos
            self.patch_resources(individual)

            log(f"✅ Applied configuration: {individual}")
        except Exception as e:
            log(f"Failed to apply configuration: {e}", level="error")
            raise

    def rollback(self) -> bool:
        """
        Faz rollback para a configuração anterior.

        Returns:
            True se rollback foi bem-sucedido, False caso contrário
        """
        if self._last_config is None:
            log("No previous configuration to rollback to", level="warning")
            return False

        try:
            log(f"Rolling back to previous configuration: {self._last_config}")
            self.apply_configuration(self._last_config, save_for_rollback=False)
            log("✅ Rollback successful")
            return True
        except Exception as e:
            log(f"Rollback failed: {e}", level="error")
            return False

    def wait_for_rollout(self, timeout: Optional[int] = None) -> bool:
        """
        Aguarda rollout completo do deployment.

        Args:
            timeout: Timeout em segundos (default: self.rollout_timeout)

        Returns:
            True se rollout completo, False se timeout
        """
        timeout = timeout or self.rollout_timeout
        api = self._get_api()
        start_time = time.time()
        check_interval = 5

        log(f"Waiting for rollout of {self.config.deployment_name}...")

        while time.time() - start_time < timeout:
            try:
                resp = api.read_namespaced_deployment_status(
                    self.config.deployment_name,
                    self.config.namespace
                )
                status = resp.status

                desired = status.replicas or 0
                updated = status.updated_replicas or 0
                available = status.available_replicas or 0
                ready = status.ready_replicas or 0

                if desired > 0 and desired == updated == available == ready:
                    log(f"✅ Rollout complete: {ready}/{desired} pods ready")
                    return True

                elapsed = int(time.time() - start_time)
                log(f"⏳ Waiting... ({ready}/{desired} ready, {available}/{desired} available) [{elapsed}s/{timeout}s]")

                if status.unavailable_replicas and status.unavailable_replicas > 0:
                    log(f"⚠️ {status.unavailable_replicas} pods unavailable", level="warning")

            except ApiException as e:
                log(f"Error checking deployment status: {e}", level="warning")

            time.sleep(check_interval)

        log(f"⚠️ Timeout: rollout did not complete in {timeout}s", level="warning")
        return False

    def get_deployment_status(self) -> Optional[Dict]:
        """
        Obtém status atual do deployment.

        Returns:
            Dicionário com status ou None em caso de erro
        """
        try:
            api = self._get_api()
            resp = api.read_namespaced_deployment_status(
                self.config.deployment_name,
                self.config.namespace
            )
            status = resp.status

            return {
                "replicas": status.replicas or 0,
                "updated_replicas": status.updated_replicas or 0,
                "available_replicas": status.available_replicas or 0,
                "ready_replicas": status.ready_replicas or 0,
                "unavailable_replicas": status.unavailable_replicas or 0
            }
        except Exception as e:
            log(f"Failed to get deployment status: {e}", level="error")
            return None


