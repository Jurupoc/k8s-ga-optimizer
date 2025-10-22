import requests
import threading
import time
import random

# ==========================
# CONFIGURAÇÕES DO TESTE
# ==========================

API_BASE_URL = "http://app-ga.default.svc.cluster.local:8000"  # Endereço interno do serviço
ENDPOINTS = ["/sort", "/search", "/prime"]  # Endpoints a testar
CONCURRENT_THREADS = 20      # Quantidade de threads simultâneas
TEST_DURATION = 60           # Duração do teste em segundos
REQUEST_DELAY = 0.05         # Atraso entre requisições (segundos)

# ==========================
# VARIÁVEIS DE MONITORAMENTO
# ==========================

total_requests = 0
success_requests = 0
failed_requests = 0
latencies = []

# ==========================
# FUNÇÃO DE TESTE
# ==========================

def send_requests():
    global total_requests, success_requests, failed_requests

    end_time = time.time() + TEST_DURATION
    while time.time() < end_time:
        endpoint = random.choice(ENDPOINTS)
        url = API_BASE_URL + endpoint

        start = time.time()
        try:
            response = requests.get(url, timeout=5)
            latency = time.time() - start
            latencies.append(latency)

            total_requests += 1
            if response.status_code == 200:
                success_requests += 1
            else:
                failed_requests += 1

        except Exception:
            failed_requests += 1
        time.sleep(REQUEST_DELAY)

# ==========================
# EXECUÇÃO DO TESTE
# ==========================

if __name__ == "__main__":
    print(f"Iniciando teste de carga contra {API_BASE_URL} por {TEST_DURATION}s com {CONCURRENT_THREADS} threads...\n")

    threads = [threading.Thread(target=send_requests) for _ in range(CONCURRENT_THREADS)]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print("\n--- RESULTADOS ---")
    print(f"Total de requisições: {total_requests}")
    print(f"Sucesso: {success_requests}")
    print(f"Falhas: {failed_requests}")

    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        p95_latency = sorted(latencies)[int(0.95 * len(latencies)) - 1]
        print(f"Latência média: {avg_latency:.3f}s")
        print(f"Latência P95: {p95_latency:.3f}s")
