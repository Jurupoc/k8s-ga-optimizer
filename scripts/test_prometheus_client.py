#!/usr/bin/env python3
"""
Script de teste para validar o PrometheusClient.
"""
import os
import sys

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from integrations.prometheus_client import PrometheusClient
from ga.config import PrometheusConfig
from shared.utils import log


def test_prometheus_connection():
    """Testa conexão com o Prometheus."""
    log("=== Testando Conexão com Prometheus ===")
    
    try:
        # Cria cliente
        client = PrometheusClient()
        
        log(f"✅ PrometheusClient criado com sucesso")
        log(f"   - URL: {client.config.url}")
        log(f"   - Timeout: {client.config.timeout}s")
        log(f"   - Retry attempts: {client.config.retry_attempts}")
        
        # Testa conexão (lazy initialization)
        log("\nTestando conexão...")
        prom_client = client._get_client()
        
        log("✅ Conexão com Prometheus estabelecida")
        return True
        
    except Exception as e:
        log(f"❌ Erro ao conectar com Prometheus: {e}", level="error")
        return False


def test_simple_query():
    """Testa query simples."""
    log("\n=== Testando Query Simples ===")
    
    try:
        client = PrometheusClient()
        
        # Query simples: verifica se o Prometheus está up
        query = 'up'
        log(f"Executando query: {query}")
        
        result = client.query_instant(query, default=0.0)
        
        log(f"✅ Query executada com sucesso")
        log(f"   - Resultado: {result}")
        
        return True
        
    except Exception as e:
        log(f"❌ Erro na query: {e}", level="error")
        return False


def test_cpu_usage_query():
    """Testa query de uso de CPU."""
    log("\n=== Testando Query de CPU ===")
    
    try:
        client = PrometheusClient()
        
        # Query de CPU
        app_label = os.environ.get("APP_LABEL", "app-ga")
        log(f"Consultando uso de CPU para app: {app_label}")
        
        cpu_usage = client.get_cpu_usage(app_label, minutes=1)
        
        log(f"✅ Query de CPU executada")
        log(f"   - CPU Usage: {cpu_usage:.4f} cores")
        
        return True
        
    except Exception as e:
        log(f"❌ Erro na query de CPU: {e}", level="error")
        return False


def test_memory_usage_query():
    """Testa query de uso de memória."""
    log("\n=== Testando Query de Memória ===")
    
    try:
        client = PrometheusClient()
        
        # Query de memória
        app_label = os.environ.get("APP_LABEL", "app-ga")
        log(f"Consultando uso de memória para app: {app_label}")
        
        memory_usage = client.get_memory_usage(app_label)
        memory_mb = memory_usage / (1024 * 1024)
        
        log(f"✅ Query de memória executada")
        log(f"   - Memory Usage: {memory_usage:.0f} bytes ({memory_mb:.2f} MB)")
        
        return True
        
    except Exception as e:
        log(f"❌ Erro na query de memória: {e}", level="error")
        return False


def test_cache():
    """Testa funcionalidade de cache."""
    log("\n=== Testando Cache ===")
    
    try:
        client = PrometheusClient()
        
        query = 'up'
        
        # Primeira query (sem cache)
        log("Primeira query (sem cache)...")
        import time
        start = time.time()
        result1 = client._query_with_cache(query, use_cache=True)
        time1 = time.time() - start
        
        # Segunda query (com cache)
        log("Segunda query (com cache)...")
        start = time.time()
        result2 = client._query_with_cache(query, use_cache=True)
        time2 = time.time() - start
        
        log(f"✅ Cache funcionando")
        log(f"   - Tempo sem cache: {time1*1000:.2f}ms")
        log(f"   - Tempo com cache: {time2*1000:.2f}ms")
        log(f"   - Speedup: {time1/time2:.1f}x")
        
        # Limpa cache
        client.clear_cache()
        log("✅ Cache limpo")
        
        return True
        
    except Exception as e:
        log(f"❌ Erro no teste de cache: {e}", level="error")
        return False


def main():
    """Executa todos os testes."""
    log("Iniciando testes do PrometheusClient...\n")
    
    tests = [
        ("Conexão", test_prometheus_connection),
        ("Query Simples", test_simple_query),
        ("Query CPU", test_cpu_usage_query),
        ("Query Memória", test_memory_usage_query),
        ("Cache", test_cache),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            log(f"\n❌ Teste '{test_name}' falhou com exceção: {e}", level="error")
            results[test_name] = False
    
    # Resumo
    log("\n" + "=" * 80)
    log("RESUMO DOS TESTES")
    log("=" * 80)
    
    passed = sum(1 for r in results.values() if r)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSOU" if result else "❌ FALHOU"
        log(f"{test_name:20s} {status}")
    
    log(f"\nTotal: {passed}/{total} testes passaram")
    
    if passed == total:
        log("\n🎉 Todos os testes passaram!")
        sys.exit(0)
    else:
        log(f"\n⚠️ {total - passed} teste(s) falharam")
        sys.exit(1)


if __name__ == "__main__":
    main()
