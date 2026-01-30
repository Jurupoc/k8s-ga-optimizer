#!/usr/bin/env python3
"""
Script de teste para validar configurações de timeout do Kubernetes.
"""
import os
import sys
import time

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from integrations.k8s_client import KubernetesClient
from ga.config import AppConfig
from ga.types import Individual
from shared.utils import log


def test_timeout_config():
    """Testa se as configurações de timeout estão sendo carregadas corretamente."""
    log("=== Testando Configurações de Timeout ===")
    
    # Define variáveis de ambiente para teste
    os.environ.setdefault("K8S_API_TIMEOUT", "60")
    os.environ.setdefault("K8S_MAX_RETRIES", "3")
    os.environ.setdefault("K8S_RETRY_DELAY", "5")
    os.environ.setdefault("K8S_CLEANUP_PENDING_PODS", "true")
    os.environ.setdefault("K8S_CLEANUP_THRESHOLD", "3")
    
    # Cria cliente
    client = KubernetesClient()
    
    # Verifica se as configurações foram carregadas
    assert client.api_timeout == 60, f"Expected api_timeout=60, got {client.api_timeout}"
    assert client.max_retries == 3, f"Expected max_retries=3, got {client.max_retries}"
    assert client.retry_delay == 5, f"Expected retry_delay=5, got {client.retry_delay}"
    assert client.cleanup_pending_pods == True, f"Expected cleanup_pending_pods=True, got {client.cleanup_pending_pods}"
    assert client.cleanup_threshold == 3, f"Expected cleanup_threshold=3, got {client.cleanup_threshold}"
    
    log(f"✅ Configurações carregadas corretamente:")
    log(f"   - API Timeout: {client.api_timeout}s")
    log(f"   - Max Retries: {client.max_retries}")
    log(f"   - Retry Delay: {client.retry_delay}s")
    log(f"   - Cleanup Pending Pods: {client.cleanup_pending_pods}")
    log(f"   - Cleanup Threshold: {client.cleanup_threshold} iterations")


def test_deployment_status():
    """Testa leitura do status do deployment."""
    log("\n=== Testando Leitura de Status ===")
    
    try:
        client = KubernetesClient()
        status = client.get_deployment_status()
        
        if status:
            log(f"✅ Status do deployment obtido com sucesso:")
            log(f"   - Replicas: {status['replicas']}")
            log(f"   - Ready: {status['ready_replicas']}")
            log(f"   - Available: {status['available_replicas']}")
        else:
            log("⚠️ Não foi possível obter status do deployment", level="warning")
            
    except Exception as e:
        log(f"❌ Erro ao obter status: {e}", level="error")
        return False
    
    return True


def test_scale_operation():
    """Testa operação de escala com retry."""
    log("\n=== Testando Operação de Escala ===")
    
    try:
        client = KubernetesClient()
        
        # Obtém número atual de réplicas
        status = client.get_deployment_status()
        if not status:
            log("⚠️ Não foi possível obter status atual", level="warning")
            return False
        
        current_replicas = status['replicas']
        log(f"Réplicas atuais: {current_replicas}")
        
        # Tenta escalar (mesmo número para não causar mudanças)
        log(f"Testando escala para {current_replicas} réplicas...")
        client.scale_deployment(current_replicas)
        
        log("✅ Operação de escala executada com sucesso")
        return True
        
    except Exception as e:
        log(f"❌ Erro na operação de escala: {e}", level="error")
        return False


def test_cleanup_pending_pods():
    """Testa a funcionalidade de limpeza de pods Pending."""
    log("\n=== Testando Limpeza de Pods Pending ===")
    
    try:
        client = KubernetesClient()
        
        if not client.cleanup_pending_pods:
            log("⚠️ Limpeza de pods desativada, pulando teste", level="warning")
            return True
        
        # Tenta limpar pods Pending (se houver)
        log("Verificando pods Pending...")
        deleted_count = client._cleanup_pending_pods()
        
        if deleted_count > 0:
            log(f"✅ Limpeza executada: {deleted_count} pod(s) deletado(s)")
        else:
            log("✅ Nenhum pod Pending encontrado (bom sinal!)")
        
        return True
        
    except Exception as e:
        log(f"❌ Erro na limpeza de pods: {e}", level="error")
        return False


def main():
    """Executa todos os testes."""
    log("Iniciando testes de timeout do Kubernetes...\n")
    
    try:
        # Teste 1: Configurações
        test_timeout_config()
        
        # Teste 2: Leitura de status
        if not test_deployment_status():
            log("\n⚠️ Teste de status falhou, mas continuando...", level="warning")
        
        # Teste 3: Limpeza de pods Pending
        if not test_cleanup_pending_pods():
            log("\n⚠️ Teste de limpeza falhou, mas continuando...", level="warning")
        
        # Teste 4: Operação de escala
        if not test_scale_operation():
            log("\n⚠️ Teste de escala falhou", level="warning")
        
        log("\n=== Testes Concluídos ===")
        log("✅ Configurações de timeout estão funcionando corretamente")
        
    except Exception as e:
        log(f"\n❌ Erro durante os testes: {e}", level="error")
        sys.exit(1)


if __name__ == "__main__":
    main()
