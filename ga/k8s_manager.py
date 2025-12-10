# ga/k8s_manager.py
"""
Gerenciamento do Kubernetes usando client-python.
Aplica replicas e resources (requests/limits) ao Deployment.
Configurações via env:
- K8S_DEPLOYMENT_NAME (default: app-ga)
- K8S_NAMESPACE (default: default)
- K8S_CONTAINER_NAME (default: mesmo que DEPLOYMENT_NAME)
- GA_DRY_RUN (se "1" ou "true" -> não aplica mudanças)
- K8S_ROLLOUT_TIMEOUT (default: 120 segundos)
"""

import os
import time
from typing import Dict, Optional
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from .utils import log


DEPLOYMENT_NAME = os.environ.get("K8S_DEPLOYMENT_NAME", "app-ga")
NAMESPACE = os.environ.get("K8S_NAMESPACE", "default")
CONTAINER_NAME = os.environ.get("K8S_CONTAINER_NAME", DEPLOYMENT_NAME)
DRY_RUN = os.environ.get("GA_DRY_RUN", "false").lower() in ("1", "true", "yes")
ROLLOUT_TIMEOUT = int(os.environ.get("K8S_ROLLOUT_TIMEOUT", "120"))

# Cache da API para evitar recarregar configuração repetidamente
_api_instance: Optional[client.AppsV1Api] = None


def k8s_api() -> client.AppsV1Api:
    """
    Retorna uma instância da API do Kubernetes.
    Tenta carregar kubeconfig local primeiro, depois in-cluster.
    Usa cache para evitar recarregar configuração repetidamente.
    """
    global _api_instance

    if _api_instance is not None:
        return _api_instance

    # Tenta kubeconfig local primeiro
    try:
        config.load_kube_config()
        log("Loaded kubeconfig from local environment")
    except Exception:
        # Se falhar, tenta in-cluster
        try:
            config.load_incluster_config()
            log("Loaded in-cluster kube config")
        except Exception as e:
            log(f"Could not load kube config: {e}", level="error")
            raise

    _api_instance = client.AppsV1Api()
    return _api_instance


def validate_configuration(individual: Dict) -> bool:
    """
    Valida se a configuração está dentro de limites razoáveis.

    Args:
        individual: Dicionário com configuração

    Returns:
        True se válido, False caso contrário
    """
    replicas = individual.get("replicas", 1)
    cpu = individual.get("cpu_limit", 0.5)
    mem = individual.get("memory_limit", 256)

    if replicas < 1 or replicas > 100:
        log(f"Invalid replicas: {replicas} (must be 1-100)", level="warning")
        return False

    if cpu < 0.01 or cpu > 100:
        log(f"Invalid CPU limit: {cpu} (must be 0.01-100 cores)", level="warning")
        return False

    if mem < 64 or mem > 100000:
        log(f"Invalid memory limit: {mem} (must be 64-100000 MB)", level="warning")
        return False

    return True


def scale_deployment(api: client.AppsV1Api, replicas: int) -> None:
    """
    Escala o deployment para o número de réplicas especificado.

    Args:
        api: Instância da API do Kubernetes
        replicas: Número de réplicas desejadas
    """
    replicas = int(replicas)
    log(f"Scaling deployment {DEPLOYMENT_NAME} to {replicas} replicas")

    if DRY_RUN:
        log("(dry-run) scale skipped")
        return

    try:
        api.patch_namespaced_deployment_scale(
            name=DEPLOYMENT_NAME,
            namespace=NAMESPACE,
            body={"spec": {"replicas": replicas}}
        )
        log(f"✅ Deployment scaled to {replicas} replicas")
    except ApiException as e:
        log(f"Failed to scale deployment: {e}", level="error")
        raise


def patch_resources(
    api: client.AppsV1Api,
    cpu_cores: float,
    mem_mb: int,
    container_name: Optional[str] = None
) -> None:
    """
    Aplica patch de recursos (CPU e memória) no deployment.

    Args:
        api: Instância da API do Kubernetes
        cpu_cores: Limite de CPU em cores (ex: 0.5 -> 500m)
        mem_mb: Limite de memória em MB (ex: 256 -> 256Mi)
        container_name: Nome do container (default: CONTAINER_NAME)
    """
    cpu_m = f"{int(cpu_cores * 1000)}m"
    mem = f"{int(mem_mb)}Mi"
    container_name = container_name or CONTAINER_NAME

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

    if DRY_RUN:
        log("(dry-run) patch skipped")
        return

    try:
        api.patch_namespaced_deployment(
            name=DEPLOYMENT_NAME,
            namespace=NAMESPACE,
            body=patch
        )
        log(f"✅ Resources patched: CPU={cpu_m}, Memory={mem}")
    except ApiException as e:
        log(f"Failed to patch resources: {e}", level="error")
        raise


def apply_k8s_configuration(individual: Dict) -> None:
    """
    Aplica configuração completa (réplicas e recursos) no deployment.

    Ordem de aplicação:
    1. Escala o deployment (réplicas)
    2. Aplica patch de recursos (CPU/memória)

    Args:
        individual: Dicionário com configuração (replicas, cpu_limit, memory_limit)

    Raises:
        ValueError: Se a configuração for inválida
        ApiException: Se houver erro na API do Kubernetes
    """
    if not validate_configuration(individual):
        raise ValueError(f"Invalid configuration: {individual}")

    api = k8s_api()
    replicas = int(individual.get("replicas", 1))
    cpu = float(individual.get("cpu_limit", 0.5))
    mem = int(individual.get("memory_limit", 256))
    container_name = individual.get("container_name")

    try:
        # Aplica escala primeiro
        scale_deployment(api, replicas)

        # Depois aplica recursos
        patch_resources(api, cpu, mem, container_name=container_name)

        log(f"✅ Applied configuration: replicas={replicas}, cpu={cpu} cores, mem={mem} MB")
    except Exception as e:
        log(f"Failed to apply k8s configuration: {e}", level="error")
        raise


def wait_for_rollout(
    deployment_name: Optional[str] = None,
    namespace: Optional[str] = None,
    timeout: Optional[int] = None
) -> bool:
    """
    Aguarda o rollout completo de um Deployment no Kubernetes.

    Args:
        deployment_name: Nome do deployment (default: DEPLOYMENT_NAME)
        namespace: Namespace (default: NAMESPACE)
        timeout: Timeout em segundos (default: ROLLOUT_TIMEOUT)

    Returns:
        True se o rollout foi bem-sucedido, False se atingiu o timeout
    """
    deployment_name = deployment_name or DEPLOYMENT_NAME
    namespace = namespace or NAMESPACE
    timeout = timeout or ROLLOUT_TIMEOUT

    # Carrega configuração se necessário
    try:
        config.load_kube_config()
    except Exception:
        try:
            config.load_incluster_config()
        except Exception as e:
            log(f"Could not load kube config for rollout check: {e}", level="error")
            return False

    apps_v1 = client.AppsV1Api()
    start_time = time.time()
    check_interval = 5  # segundos

    log(f"Waiting for rollout of {deployment_name} in namespace {namespace}...")

    while time.time() - start_time < timeout:
        try:
            resp = apps_v1.read_namespaced_deployment_status(deployment_name, namespace)
            status = resp.status

            desired = status.replicas or 0
            updated = status.updated_replicas or 0
            available = status.available_replicas or 0
            ready = status.ready_replicas or 0

            # Verifica condições de rollout completo
            if desired > 0 and desired == updated == available == ready:
                log(f"✅ Rollout completo para {deployment_name} "
                    f"({available}/{desired} pods disponíveis e prontos)")
                return True

            # Verifica se há problemas
            if status.unavailable_replicas and status.unavailable_replicas > 0:
                log(f"⚠️ {status.unavailable_replicas} pods indisponíveis", level="warning")

            elapsed = int(time.time() - start_time)
            log(f"⏳ Aguardando rollout... "
                f"({ready}/{desired} prontos, {available}/{desired} disponíveis, "
                f"{updated}/{desired} atualizados) [{elapsed}s/{timeout}s]")

        except ApiException as e:
            log(f"Error checking deployment status: {e}", level="warning")

        time.sleep(check_interval)

    log(f"⚠️ Timeout: rollout de {deployment_name} não completou em {timeout}s", level="warning")
    return False


def get_deployment_status(deployment_name: Optional[str] = None, namespace: Optional[str] = None) -> Optional[Dict]:
    """
    Obtém o status atual do deployment.

    Args:
        deployment_name: Nome do deployment (default: DEPLOYMENT_NAME)
        namespace: Namespace (default: NAMESPACE)

    Returns:
        Dicionário com status ou None em caso de erro
    """
    deployment_name = deployment_name or DEPLOYMENT_NAME
    namespace = namespace or NAMESPACE

    try:
        api = k8s_api()
        resp = api.read_namespaced_deployment_status(deployment_name, namespace)
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
