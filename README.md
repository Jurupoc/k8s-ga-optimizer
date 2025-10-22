# Kubernetes GA Optimizer

Este projeto demonstra a utilização de **algoritmo genético (GA) para otimização de clusters Kubernetes**. Ele inclui uma API, scripts de teste de carga, coleta de métricas via Prometheus e manifests Kubernetes para deploy.

## Objetivo

O objetivo é criar um pipeline que:

1. Coleta métricas do cluster e da aplicação.
2. Executa algoritmos genéticos para explorar diferentes configurações de recursos (replicas, limites de CPU/memória, afinidade de pods, etc.).
3. Avalia cada configuração com base em métricas de desempenho.
4. Aplica a configuração otimizada para o cluster.

---

## API

A API oferece endpoints que simulam carga computacional e expõem métricas:

- **`GET /sort?size=<n>`**
  Executa algoritmo de ordenação de vetor de tamanho `<n>`.

- **`GET /search?size=<n>`**
  Executa algoritmo de busca.

- **`GET /prime?size=<n>`**
  Gera números primos até `<n>`.

- **`GET /metrics`**
  Exposição de métricas Prometheus.

- **`GET /status`**
  Status do nó onde a API roda:
  ```json
  {
    "node": "<hostname>",
    "cpu_percent": <percent>,
    "memory_percent": <percent>
  }
