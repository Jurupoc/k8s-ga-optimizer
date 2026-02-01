# integrations/k8s_client.py
"""
Cliente robusto para integração com Kubernetes.
Inclui validação, rollback automático, dry-run e espera confiável de rollout.
"""

import os
import time
from functools import wraps
from typing import Dict, Optional
from kubernetes import client, config
from kubernetes.client.rest import ApiException

from ga.exceptions import KubernetesError, ConfigurationError
from ga.config import AppConfig
from ga.types import Individual
from shared.utils import log


def retry_on_timeout(max_retries: int = 3, delay: int = 5, cleanup_pods: bool = True):
    """
    Decorator para retry automático em caso de timeout ou erro 500.

    Args:
        max_retries: Número máximo de tentativas
        delay: Delay base entre tentativas (segundos)
        cleanup_pods: Se True, remove pods Pending antes de retentar
    """

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(self, *args, **kwargs)
                except ApiException as e:
                    last_exception = e
                    # Retry em erros de timeout (500), rate limiting (429), ou service unavailable (503)
                    if e.status in (500, 429, 503):
                        if attempt < max_retries - 1:
                            wait_time = delay * (2**attempt)  # Backoff exponencial
                            log(
                                f"⚠️ API error {e.status}, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})",
                                level="warning",
                            )

                            # Limpa pods Pending antes de retentar
                            if cleanup_pods and hasattr(self, "_cleanup_pending_pods"):
                                try:
                                    self._cleanup_pending_pods()
                                except Exception as cleanup_error:
                                    log(
                                        f"Cleanup error (non-fatal): {cleanup_error}",
                                        level="warning",
                                    )

                            time.sleep(wait_time)
                            continue
                    # Para outros erros, não tenta novamente
                    raise
                except (ConnectionError, TimeoutError, OSError) as e:
                    # Erros de conexão também devem ser retentados
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = delay * (2**attempt)
                        log(
                            f"⚠️ Connection error: {type(e).__name__}, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})",
                            level="warning",
                        )
                        time.sleep(wait_time)
                        continue
                    raise
                except Exception as e:
                    # Outros erros não devem ser retentados
                    raise
            # Se todas as tentativas falharam
            raise last_exception

        return wrapper

    return decorator


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
        self.rollout_timeout = int(os.environ.get("K8S_ROLLOUT_TIMEOUT", "120"))
        self.api_timeout = int(
            os.environ.get("K8S_API_TIMEOUT", "120")
        )  # Timeout para operações da API
        self.max_retries = int(
            os.environ.get("K8S_MAX_RETRIES", "3")
        )  # Número de tentativas
        self.retry_delay = int(
            os.environ.get("K8S_RETRY_DELAY", "5")
        )  # Delay entre tentativas (segundos)
        self.cleanup_pending_pods = os.environ.get(
            "K8S_CLEANUP_PENDING_PODS", "true"
        ).lower() in ("1", "true", "yes")
        self.cleanup_threshold = int(
            os.environ.get("K8S_CLEANUP_THRESHOLD", "10")
        )  # Iterações sem progresso antes de limpar
        self._api: Optional[client.AppsV1Api] = None
        self._core_api: Optional[client.CoreV1Api] = None  # Cache da Core API
        self._api_client: Optional[client.ApiClient] = None  # Cliente compartilhado
        self._last_config: Optional[Individual] = None  # Para rollback
        self._consecutive_failures = 0  # Contador de falhas consecutivas
        self._max_consecutive_failures = 5  # Máximo antes de circuit breaker

    def _get_api_client(self) -> client.ApiClient:
        """Obtém ou cria o ApiClient compartilhado (reutiliza conexões)."""
        if self._api_client is None:
            try:
                config.load_kube_config()
                log("Loaded kubeconfig from local environment")
            except Exception:
                try:
                    config.load_incluster_config()
                    log("Loaded in-cluster kube config")
                except Exception as e:
                    log(f"Could not load kube config: {e}", level="error")
                    raise KubernetesError(
                        f"Failed to load Kubernetes config: {e}"
                    ) from e

            # Cria ApiClient compartilhado com timeout configurado
            self._api_client = client.ApiClient()
            self._api_client.rest_client.pool_manager.connection_pool_kw["timeout"] = (
                self.api_timeout
            )
            # Aumenta o pool de conexões para evitar esgotamento
            self._api_client.rest_client.pool_manager.connection_pool_kw["maxsize"] = 10
            log(f"Kubernetes API client configured with timeout={self.api_timeout}s, maxsize=10")

        return self._api_client

    def _get_api(self) -> client.AppsV1Api:
        """Obtém ou cria a API do Kubernetes (reutiliza ApiClient)."""
        if self._api is None:
            api_client = self._get_api_client()
            self._api = client.AppsV1Api(api_client)
        return self._api

    def _get_core_api(self) -> client.CoreV1Api:
        """Obtém API Core V1 para operações com pods (reutiliza ApiClient)."""
        if self._core_api is None:
            api_client = self._get_api_client()
            self._core_api = client.CoreV1Api(api_client)
        return self._core_api

    def _check_circuit_breaker(self):
        """
        Verifica se o circuit breaker deve ser ativado.

        Raises:
            KubernetesError: Se muitas falhas consecutivas ocorreram
        """
        if self._consecutive_failures >= self._max_consecutive_failures:
            raise KubernetesError(
                f"Circuit breaker activated: {self._consecutive_failures} consecutive failures. "
                "Kubernetes API may be unavailable."
            )

    def _record_success(self):
        """Registra operação bem-sucedida (reseta contador de falhas)."""
        if self._consecutive_failures > 0:
            log(f"API recovered after {self._consecutive_failures} failures", level="info")
        self._consecutive_failures = 0

    def _record_failure(self):
        """Registra falha de operação."""
        self._consecutive_failures += 1
        log(
            f"API failure recorded ({self._consecutive_failures}/{self._max_consecutive_failures})",
            level="warning"
        )

    def _cleanup_pending_pods(self) -> int:
        """
        Remove pods em estado Pending que podem estar travados.

        Returns:
            Número de pods deletados
        """
        try:
            core_api = self._get_core_api()

            # Lista pods do deployment
            label_selector = f"app={self.config.deployment_name}"
            pods = core_api.list_namespaced_pod(
                namespace=self.config.namespace,
                label_selector=label_selector,
                _request_timeout=self.api_timeout,
            )

            deleted_count = 0
            for pod in pods.items:
                # Verifica se o pod está em Pending por muito tempo
                if pod.status.phase == "Pending":
                    pod_name = pod.metadata.name

                    # Verifica há quanto tempo está Pending
                    creation_time = pod.metadata.creation_timestamp
                    age_seconds = (
                        (time.time() - creation_time.timestamp())
                        if creation_time
                        else 0
                    )

                    # Deleta pods Pending por mais de 30 segundos
                    if age_seconds > 30:
                        log(
                            f"🗑️ Deleting stuck Pending pod: {pod_name} (age: {int(age_seconds)}s)"
                        )
                        try:
                            core_api.delete_namespaced_pod(
                                name=pod_name,
                                namespace=self.config.namespace,
                                grace_period_seconds=0,  # Força deleção imediata
                                _request_timeout=self.api_timeout,
                            )
                            deleted_count += 1
                        except ApiException as e:
                            log(
                                f"Failed to delete pod {pod_name}: {e}", level="warning"
                            )

            if deleted_count > 0:
                log(f"✅ Cleaned up {deleted_count} pending pod(s)")

            return deleted_count

        except Exception as e:
            log(f"Failed to cleanup pending pods: {e}", level="warning")
            return 0

    def _validate_individual(self, individual: Individual) -> None:
        """
        Valida um indivíduo antes de aplicar.

        Args:
            individual: Indivíduo a validar

        Raises:
            ConfigurationError: Se a configuração for inválida
        """
        if individual.replicas < 1 or individual.replicas > 100:
            raise ConfigurationError(
                f"Invalid replicas: {individual.replicas} (must be 1-100)"
            )

        if individual.cpu_limit < 0.01 or individual.cpu_limit > 100:
            raise ConfigurationError(
                f"Invalid CPU limit: {individual.cpu_limit} (must be 0.01-100 cores)"
            )

        if individual.memory_limit < 64 or individual.memory_limit > 100000:
            raise ConfigurationError(
                f"Invalid memory limit: {individual.memory_limit} (must be 64-100000 MB)"
            )

    def _get_current_deployment(self) -> Optional[client.V1Deployment]:
        """Obtém o deployment atual com timeout."""
        try:
            api = self._get_api()
            return api.read_namespaced_deployment(
                name=self.config.deployment_name,
                namespace=self.config.namespace,
                _request_timeout=self.api_timeout,
            )
        except ApiException as e:
            log(f"Failed to get current deployment: {e}", level="warning")
            return None

    def _parse_memory_to_mb(self, mem_str: str) -> int:
        """
        Converte string de memória Kubernetes para MB.

        Suporta: Mi, M, Gi, G, Ki, K
        Exemplos: "256Mi" -> 256, "1Gi" -> 1024, "512M" -> 512

        Args:
            mem_str: String de memória (ex: "256Mi", "1Gi")

        Returns:
            Memória em MB
        """
        mem_str = mem_str.strip()

        # Mapeamento de unidades para MB
        if mem_str.endswith("Gi"):
            return int(float(mem_str.rstrip("Gi")) * 1024)
        elif mem_str.endswith("G"):
            return int(float(mem_str.rstrip("G")) * 1000)
        elif mem_str.endswith("Mi"):
            return int(mem_str.rstrip("Mi"))
        elif mem_str.endswith("M"):
            return int(mem_str.rstrip("M"))
        elif mem_str.endswith("Ki"):
            return int(float(mem_str.rstrip("Ki")) / 1024)
        elif mem_str.endswith("K"):
            return int(float(mem_str.rstrip("K")) / 1000)
        else:
            # Assume bytes, converte para MB
            return int(float(mem_str) / (1024 * 1024))

    def _parse_cpu_to_cores(self, cpu_str: str) -> float:
        """
        Converte string de CPU Kubernetes para cores.

        Exemplos: "500m" -> 0.5, "1" -> 1.0, "1.5" -> 1.5

        Args:
            cpu_str: String de CPU (ex: "500m", "1")

        Returns:
            CPU em cores
        """
        cpu_str = cpu_str.strip()

        if cpu_str.endswith("m"):
            return float(cpu_str.rstrip("m")) / 1000
        else:
            return float(cpu_str)

    def _save_current_config(self) -> None:
        """Salva a configuração atual para possível rollback."""
        deployment = self._get_current_deployment()
        if deployment:
            spec = deployment.spec
            template = spec.template
            container = (
                template.spec.containers[0] if template.spec.containers else None
            )

            if container and container.resources:
                limits = container.resources.limits or {}
                cpu_str = limits.get("cpu", "0")
                mem_str = limits.get("memory", "0Mi")

                try:
                    cpu_cores = self._parse_cpu_to_cores(cpu_str)
                    mem_mb = self._parse_memory_to_mb(mem_str)

                    self._last_config = Individual(
                        replicas=spec.replicas or 1,
                        cpu_limit=cpu_cores,
                        memory_limit=mem_mb,
                    )
                    log(f"Saved config for rollback")
                except Exception as e:
                    log(
                        f"Failed to parse current config (cpu={cpu_str}, mem={mem_str}): {e}",
                        level="error",
                    )

    @retry_on_timeout(max_retries=3, delay=5, cleanup_pods=True)
    def scale_deployment(self, replicas: int) -> None:
        """
        Escala o deployment com retry automático.

        Args:
            replicas: Número de réplicas desejadas

        Raises:
            KubernetesError: Se a operação falhar após todas as tentativas
        """
        self._check_circuit_breaker()

        replicas = int(replicas)
        log(f"Scaling deployment {self.config.deployment_name} to {replicas} replicas")

        try:
            api = self._get_api()
            api.patch_namespaced_deployment_scale(
                name=self.config.deployment_name,
                namespace=self.config.namespace,
                body={"spec": {"replicas": replicas}},
                _request_timeout=self.api_timeout,
            )
            log(f"✅ Deployment scaled to {replicas} replicas")
            self._record_success()
        except ApiException as e:
            self._record_failure()
            raise KubernetesError(f"Failed to scale deployment: {e}") from e

    @retry_on_timeout(max_retries=3, delay=5, cleanup_pods=True)
    def patch_resources(self, individual: Individual) -> None:
        """
        Aplica patch de recursos (CPU e memória) com retry automático.

        Args:
            individual: Indivíduo com configuração de recursos

        Raises:
            KubernetesError: Se a operação falhar após todas as tentativas
        """
        self._check_circuit_breaker()

        cpu_m = f"{int(individual.cpu_limit * 1000)}m"
        mem = f"{int(individual.memory_limit)}Mi"
        container_name = self.config.container_name

        patch = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": container_name,
                                "resources": {
                                    "requests": {"cpu": cpu_m, "memory": mem},
                                    "limits": {"cpu": cpu_m, "memory": mem},
                                },
                            }
                        ]
                    }
                }
            }
        }

        log(
            f"Patching resources for container {container_name}: CPU={cpu_m}, Memory={mem}"
        )

        try:
            api = self._get_api()
            api.patch_namespaced_deployment(
                name=self.config.deployment_name,
                namespace=self.config.namespace,
                body=patch,
                _request_timeout=self.api_timeout,
            )
            self._record_success()
        except ApiException as e:
            self._record_failure()
            raise KubernetesError(f"Failed to patch resources: {e}") from e

    def apply_configuration(
        self, individual: Individual, save_for_rollback: bool = True
    ) -> None:
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
            log(f"📝 Applying configuration: {individual}")
            # Aplica escala primeiro
            log(f"  → Scaling to {individual.replicas} replicas...", level="debug")
            self.scale_deployment(individual.replicas)

            # Depois aplica recursos (isso força um novo rollout!)
            log(
                f"  → Patching resources (CPU={individual.cpu_limit}, MEM={individual.memory_limit})...",
                level="debug",
            )
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

        Remove automaticamente pods em Pending se não houver progresso.

        Args:
            timeout: Timeout em segundos (default: self.rollout_timeout)

        Returns:
            True se rollout completo, False se timeout
        """
        timeout = timeout or self.rollout_timeout
        api = self._get_api()
        start_time = time.time()
        check_interval = 5

        # Controle de progresso para detectar pods travados
        last_ready_count = -1
        no_progress_iterations = 0
        cleanup_threshold = (
            self.cleanup_threshold
        )  # Iterações sem progresso antes de limpar

        # Flag para garantir que vimos o rollout em progresso antes de considerar completo
        saw_rollout_in_progress = False

        # Obtém a generation atual do deployment para verificar se mudanças foram aplicadas
        initial_deployment = api.read_namespaced_deployment(
            self.config.deployment_name,
            self.config.namespace,
            _request_timeout=self.api_timeout,
        )
        expected_generation = initial_deployment.metadata.generation
        log(f"Expected deployment generation: {expected_generation}", level="debug")

        log(f"Waiting for rollout of {self.config.deployment_name}...")

        while time.time() - start_time < timeout:
            try:
                resp = api.read_namespaced_deployment_status(
                    self.config.deployment_name,
                    self.config.namespace,
                    _request_timeout=self.api_timeout,
                )
                status = resp.status

                desired = status.replicas or 0
                updated = status.updated_replicas or 0
                available = status.available_replicas or 0
                ready = status.ready_replicas or 0

                if desired > 0 and desired == updated == available == ready:
                    log(f"✅ Rollout complete: {ready}/{desired} pods ready")
                    if self.config.warmup_time > 0:
                        log(f"Waiting {self.config.warmup_time}s for warm up...")
                        time.sleep(self.config.warmup_time)
                    return True

                elapsed = int(time.time() - start_time)
                log(
                    f"⏳ Waiting... ({ready}/{desired} ready, {available}/{desired} available, {updated}/{desired} updated) [{elapsed}s/{timeout}s]"
                )

                # Detecta falta de progresso
                if ready == last_ready_count:
                    no_progress_iterations += 1
                    log(
                        f"No progress detected ({no_progress_iterations}/{cleanup_threshold} checks)",
                        level="debug",
                    )
                else:
                    no_progress_iterations = 0  # Reset se houve progresso

                last_ready_count = ready

                # Limpa pods Pending se não houver progresso e cleanup estiver ativado
                if (
                    no_progress_iterations >= cleanup_threshold
                    and self.cleanup_pending_pods
                    and status.unavailable_replicas
                    and status.unavailable_replicas > 0
                ):

                    log(
                        f"⚠️ No progress after {no_progress_iterations * check_interval}s, cleaning up pending pods...",
                        level="warning",
                    )
                    deleted_count = self._cleanup_pending_pods()

                    if deleted_count > 0:
                        # Reset contador após limpeza bem-sucedida
                        no_progress_iterations = 0
                        # Aguarda um pouco para Kubernetes recriar pods
                        log("Waiting for Kubernetes to recreate pods...")
                        time.sleep(check_interval)
                        continue

                if status.unavailable_replicas and status.unavailable_replicas > 0:
                    log(
                        f"⚠️ {status.unavailable_replicas} pods unavailable",
                        level="debug",
                    )

            except ApiException as e:
                log(f"Error checking deployment status: {e}", level="warning")

            time.sleep(check_interval)

        log(f"⚠️ Timeout: rollout did not complete in {timeout}s", level="warning")

        # Última tentativa de limpeza antes de desistir
        if self.cleanup_pending_pods:
            log("Final cleanup attempt before timeout...", level="warning")
            self._cleanup_pending_pods()

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
                self.config.namespace,
                _request_timeout=self.api_timeout,
            )
            status = resp.status

            return {
                "replicas": status.replicas or 0,
                "updated_replicas": status.updated_replicas or 0,
                "available_replicas": status.available_replicas or 0,
                "ready_replicas": status.ready_replicas or 0,
                "unavailable_replicas": status.unavailable_replicas or 0,
            }
        except Exception as e:
            log(f"Failed to get deployment status: {e}", level="error")
            return None
