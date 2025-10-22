# Kubernetes GA Optimizer

Este projeto demonstra a utilização de **algoritmo genético (GA) para otimização de clusters Kubernetes**. Ele inclui uma API, scripts de teste de carga, coleta de métricas via Prometheus e manifests Kubernetes para deploy. O objetivo principal é criar uma infraestrutura automatizada capaz de testar diferentes configurações do cluster e sugerir ajustes para melhorar desempenho e utilização de recursos.

## Objetivo

O objetivo do projeto é criar um pipeline que:

1. Coleta métricas do cluster e da aplicação.
2. Executa algoritmos genéticos para explorar diferentes configurações de recursos do Kubernetes, como:
   - Número de réplicas do deployment
   - Limites e requests de CPU e memória
   - Afinidade e anti-afinidade de pods
   - Estratégias de escalonamento
3. Avalia cada configuração usando métricas de desempenho e eficiência (latência, throughput, uso de CPU/memória).
4. Sugere ou aplica automaticamente a configuração otimizada para o cluster.

O uso de algoritmos genéticos permite explorar grandes combinações de parâmetros de forma eficiente, mantendo as melhores soluções e gerando novas configurações que podem levar a uma melhora contínua do desempenho do cluster.

---

## API

A API oferece endpoints que simulam carga computacional, expõem métricas para o Prometheus e retornam informações sobre o estado do nó:

- **`GET /sort?size=<n>`**
  Executa um algoritmo de ordenação de vetor de tamanho `<n>`.

- **`GET /search?size=<n>`**
  Executa um algoritmo de busca.

- **`GET /prime?size=<n>`**
  Gera números primos até `<n>`.

- **`GET /metrics`**
  Exposição de métricas Prometheus, incluindo:
  - Número de requisições totais (`app_requests_total`)
  - Latência de requisições (`app_request_latency_seconds`)
  - Métricas do Python (GC, memória, CPU)

- **`GET /status`**
  Status do nó onde a API está rodando, retornando:

  ```json
  {
    "node": "<hostname>",
    "cpu_percent": <percent>,
    "memory_percent": <percent>
  }

## Estrutura de Arquivos

k8s-ga-optimizer/
│
├── app/                     # Código-fonte da API
│   ├── main.py              # Entrypoint FastAPI
│   └── ...                  # Módulos auxiliares (algoritmos / métricas)
│
├── tests/                   # Scripts de load test
│   ├── load_test.py         # Script de execução do load test
│   └── Dockerfile           # Dockerfile para rodar o load test
│
├── ga/                      # Código do Algoritmo Genético
│   ├── optimizer.py         # Implementação do GA
│   ├── evaluator.py         # Avaliação de métricas / fitness
│   └── utils.py             # Funções auxiliares
│
├── manifests/               # Arquivos Kubernetes
│   ├── deployment.yaml      # Deployment da API
│   ├── service.yaml         # Service da API
│   └── service-monitor.yaml # ServiceMonitor para Prometheus
│
├── Dockerfile               # Dockerfile da API
├── requirements.txt         # Dependências Python
├── Makefile                 # Comandos para build, deploy e teste
└── README.md                # Documentação do projeto

## Makefile

O projeto inclui um Makefile completo que facilita todo o fluxo de desenvolvimento e testes, evitando a necessidade de digitar longos comandos kubectl ou docker. Ele centraliza operações de:

1. Build da API

2. Deploy da API no cluster

3. Execução do load test

4. Execução do algoritmo genético

5. Monitoramento de logs e port forwarding

6. Limpeza de imagens e pods temporários
