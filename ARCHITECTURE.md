# Arquitetura do Sistema - Kubernetes Resource Optimizer

## 📐 Visão Geral

Sistema de otimização automática de recursos Kubernetes baseado em algoritmos evolutivos. O repositório hospeda **dois algoritmos coexistentes** que compartilham infraestrutura (cliente K8s, cliente Prometheus, load tester):

- **GA mono-objetivo** (`ga/`) — fitness escalar (latência + eficiência + confiabilidade).
- **NSGA-II multi-objetivo** (`nsga/`) — três objetivos minimizados (saturação, recurso provisionado, throughput negativo) com não-dominância e crowding distance.

Ambos podem ser executados como `Job` Kubernetes via Makefile (`make ga` / `make nsga`). O caminho de longo prazo do projeto ainda inclui evoluir para autoscaling preditivo baseado em ML.

## 🏗️ Estrutura Modular

```
/k8s-ga-optimizer
│
├── ga/                          # Algoritmo Genético mono-objetivo
│   ├── optimizer.py             # Executor principal do GA
│   ├── population.py            # Gerenciamento de população
│   ├── fitness.py               # Cálculo de fitness multicritério
│   ├── cache.py                 # Cache de resultados
│   ├── types.py                 # Tipos de dados (dataclasses)
│   ├── config.py                # Configurações centralizadas
│   ├── exceptions.py            # Exceções customizadas
│   └── utils.py                 # Utilitários
│
├── nsga/                        # NSGA-II multi-objetivo
│   ├── domain.py                # Genome, RawMetrics, Objectives, Individual
│   ├── search_space.py          # Espaço de busca discreto + repair()
│   ├── operators.py             # Crossover uniforme + mutação por gene
│   ├── nsga2.py                 # Fast non-dominated sort + crowding distance
│   ├── objectives.py            # f1/f2/f3 + ResourceWeights/SaturationWeights
│   ├── evaluate.py              # Pipeline de avaliação (apply→wait→load→prom)
│   ├── cache.py                 # Cache JSONL com chave por genome+load_params
│   ├── storage.py               # CSVs por geração + Pareto front + summary
│   ├── runner.py                # NSGA2Runner (loop geracional, elitismo P∪Q)
│   └── adapters/                # Interfaces desacopladas
│       ├── k8s_adapter.py       # K8sAdapter + RealK8sAdapter
│       ├── prometheus_adapter.py# PrometheusAdapter + RealPrometheusAdapter
│       ├── load_adapter.py      # LoadAdapter + Real/Mock
│       └── mock_adapters.py     # K8s/Prom mocks para testes offline
│
├── integrations/                # Integrações com sistemas externos
│   ├── prometheus_client.py     # Cliente Prometheus (query/range/range_max)
│   └── k8s_client.py            # Cliente Kubernetes com rollback
│
├── load/                        # Testes de carga
│   ├── load_test.py             # Executor de load tests
│   └── workload_profiles.py     # Perfis de carga (burst, sustained, etc)
│
├── app/                         # Aplicação de teste (FastAPI)
│   ├── main.py                  # API FastAPI
│   ├── db.py                    # SQLite para DB-bound workloads
│   ├── compute/                 # Operações CPU-bound
│   └── metrics.py               # Métricas Prometheus
│
├── shared/                      # Utilitários compartilhados
│   ├── types.py                 # GenericIndividual usado pelos adapters
│   └── utils.py                 # Logging, parsing
│
├── scripts/                     # Entrypoints
│   ├── run_ga.py                # GA → Kubernetes Job (manifests/ga-job.yaml)
│   ├── run_nsga.py              # NSGA-II Job (manifests/nsga-job.yaml) + --mock
│   └── export_metrics.py        # Exportação CSV/Parquet/JSON
│
└── manifests/                   # Kubernetes manifests
    ├── deployment-app-ga.yaml
    ├── ga-job.yaml
    ├── nsga-job.yaml
    ├── service-account.yaml
    └── ...
```

## 🔄 Fluxo de Execução

Ambos os algoritmos seguem o mesmo loop "applicação → carga → métricas → seleção", divergindo apenas na função objetivo e no critério de sobrevivência.

```
1. Inicialização
   ├── Carrega configurações (env vars)
   ├── Cria população inicial aleatória (respeitando o search space)
   └── Inicializa clientes (Prometheus, K8s, Load Tester)

2. Loop de Gerações
   ├── Para cada indivíduo da população:
   │   ├── Verifica cache
   │   ├── Aplica configuração no K8s
   │   ├── Aguarda rollout
   │   ├── Executa load test
   │   ├── Coleta métricas do Prometheus
   │   └── GA: calcula fitness escalar
   │       NSGA-II: calcula vetor (f1, f2, f3)
   │
   ├── GA: torneio + crossover + mutação + elitismo
   │   NSGA-II: P ∪ Q → fast non-dominated sort →
   │            crowding distance → próxima geração
   │
   └── Persiste estatísticas da geração

3. Finalização
   ├── GA: aplica melhor configuração + exporta JSON
   ├── NSGA-II: persiste último Pareto front + summary
   └── Encerra adapters (cleanup)
```

## 🧬 Algoritmo Genético (mono-objetivo)

### Componentes

1. **Population Manager** (`ga/population.py`)
   - Inicialização aleatória
   - Seleção por torneio
   - Crossover (média ponderada, escolha aleatória)
   - Mutação (gaussiana para contínuos, delta para discretos)
   - Elitismo

2. **Fitness Calculator** (`ga/fitness.py`)
   - Fitness multicritério:
     - Throughput (30%)
     - Latency (25%)
     - Resource Efficiency (25%)
     - Reliability (20%)

3. **Cache** (`ga/cache.py`)
   - Cache de resultados por configuração
   - TTL configurável
   - Evita reavaliações desnecessárias

### Parâmetros Configuráveis

- `GA_POPULATION`: Tamanho da população (default: 6)
- `GA_GENERATIONS`: Número de gerações (default: 5)
- `GA_MUTATION_RATE`: Taxa de mutação (default: 0.2)
- `GA_CROSSOVER_RATE`: Taxa de crossover (default: 0.8)
- `GA_ELITISM_COUNT`: Número de elite (default: 1)
- `GA_STABILIZATION_SECONDS`: Tempo de estabilização (default: 30)

## 🎯 NSGA-II (multi-objetivo)

### Componentes

1. **Domínio** (`nsga/domain.py`)
   - `Genome(cpu_m, mem_mib, replicas)` — codificação inteira
   - `RawMetrics` — saída crua do Prometheus + load tester
   - `Objectives(f1, f2, f3)` — vetor de objetivos (todos minimizados)
   - `Individual` — `Genome + Objectives + status + rank + crowding_distance`

2. **Search Space** (`nsga/search_space.py`)
   - Bounds discretos: `cpu_m ∈ [min, max] step`, `mem_mib ∈ [min, max] step`, `replicas ∈ [min, max]`
   - `repair()` reprojeta qualquer genoma para o múltiplo de `step` mais próximo dentro dos bounds (usado após crossover/mutação)

3. **Operadores** (`nsga/operators.py`)
   - **Crossover uniforme** por gene (`pc`, default 0.9)
   - **Mutação por gene** (`pm` por gene, default 0.1) — sorteia novo valor dentro do search space, seguido de `repair()`

4. **Algoritmo** (`nsga/nsga2.py`)
   - `fast_non_dominated_sort` — implementação O(M·N²) iterando por **índices** (não por `population.index(...)`), explorando antissimetria da relação de dominância
   - `calculate_crowding_distance` — distância normalizada por objetivo, com extremos recebendo `inf`
   - `select_next_population(P ∪ Q)` — preenche frentes em ordem de rank, desempate por crowding distance descendente

5. **Objetivos** (`nsga/objectives.py`)
   - `f1 = w_cpu·cpu_throttle_rate + w_mem·mem_peak_ratio` (saturação) → defaults `(0.5, 0.5)` via `SaturationWeights`
   - `f2 = replicas · (w_cpu·cpu_cores + w_mem·mem_gib)` (recurso provisionado) → defaults `(1.0, 1.0)` via `ResourceWeights`, configuráveis na construção do pipeline
   - `f3 = -throughput_rps` (minimizar negativo equivale a maximizar throughput)
   - `penalty_objectives()` para indivíduos com `status = error/timeout` (dominados por qualquer medição real)

6. **Avaliação** (`nsga/evaluate.py`)
   - Pipeline `apply_config → wait_ready → sleep(stabilization) → run_load_test → collect_metrics → calculate_objectives`
   - Tratamento de exceções/timeout com fallback para penalidades

7. **Cache** (`nsga/cache.py`)
   - JSONL append-only (carregamento eager no startup)
   - Chave: `MD5(genome | load_profile | sorted(load_params))` — mudar duração, concorrência ou endpoint invalida automaticamente entradas antigas

8. **Storage** (`nsga/storage.py`)
   - `manifest.json` (parâmetros do experimento)
   - `generation_NNN.csv` (população completa por geração com rank/crowding)
   - `pareto_front_NNN.csv` (apenas rank 0)
   - `summary.json` (estatísticas finais e cache hits)

9. **Adapters** (`nsga/adapters/`)
   - Três interfaces (`K8sAdapter`, `PrometheusAdapter`, `LoadAdapter`) com `Real*` (delegam aos clientes em `integrations/`) e `Mock*` (sintéticos, determinísticos)
   - Permitem rodar `python scripts/run_nsga.py --mock` sem cluster, útil para testes e CI

### Parâmetros Configuráveis

- `NSGA_POPULATION` / `NSGA_GENERATIONS` (default: 6 / 5)
- `NSGA_CROSSOVER_RATE` / `NSGA_MUTATION_RATE` (default: 0.9 / 0.1)
- `NSGA_SEED` (default: 42) — reprodutibilidade do RNG do operador
- `NSGA_STABILIZATION_S` (default: 5)
- `NSGA_OUTPUT_DIR` (default: `/results/nsga`)
- `NSGA_MOCK` (default: `false`) — força adapters sintéticos
- Search space: `NSGA_CPU_*`, `NSGA_MEM_*`, `NSGA_REP_*`

### Diferenças relevantes vs. GA mono-objetivo

| Aspecto | GA (`ga/`) | NSGA-II (`nsga/`) |
|---|---|---|
| Saída | Único melhor indivíduo | Pareto front (frente 0) |
| Seleção | Torneio binário por fitness | Torneio binário por (rank, crowding) |
| Sobrevivência | Elitismo top-k | P ∪ Q → frentes ordenadas |
| Operadores | Média ponderada / gaussiana | Uniforme / per-gene aleatório com `repair()` |
| Cache key | Configuração | Configuração + load_params (`sort_keys=True`) |
| Acoplamento a K8s | Direto via `integrations/` | Via interfaces (`adapters/`), mockáveis |

## 🔌 Integrações

### Prometheus Client

- **Retries automáticos** com exponential backoff
- **Cache de queries** (TTL: 5s)
- **Tolerância a falhas** com valores padrão
- **Métricas suportadas**:
  - CPU usage
  - Memory usage
  - Request rate
  - Request latency (p50, p95, p99)
  - Error rate
  - Pod count

### Kubernetes Client

- **Validação** de configurações antes de aplicar
- **Rollback automático** em caso de falhas
- **Dry-run mode** para testes
- **Espera confiável** de rollout
- **Operações atômicas** (scale + patch resources)

## 📊 Load Testing

### Perfis de Carga

1. **Sustained**: Carga constante
2. **Burst**: Picos periódicos
3. **Ramp-up**: Aumento gradual
4. **Spiky**: Cargas irregulares
5. **Wave**: Padrão senoidal

### Métricas Coletadas

- Throughput (req/s)
- Latency (avg, min, max, p50, p95, p99)
- Success rate
- Total requests

## 🎯 Aplicação de Teste

### Endpoints

**CPU-Bound:**
- `/sort` - Ordenação
- `/search` - Busca binária
- `/prime` - Geração de primos
- `/cpu-stress` - Stress puro

**IO-Bound:**
- `/io-read` - Simula leitura
- `/io-write` - Simula escrita
- `/io-mixed` - Operações mistas

**DB-Bound:**
- `/db/insert` - Inserção
- `/db/query` - Consulta
- `/db/search` - Busca com LIKE
- `/db/aggregate` - Agregações
- `/db/complex` - Operação complexa

**Mixed:**
- `/mixed` - CPU + IO + DB

## 📈 Exportação de Dados

### Formatos Suportados

- **CSV**: Para análise em Excel/Sheets
- **Parquet**: Para análise em Python/R
- **JSON**: Para integração com outras ferramentas

### Dados Exportados

- Resultados de avaliação (fitness, métricas)
- Estatísticas de gerações
- Melhor configuração encontrada
- Histórico completo

## 🚀 Preparação para ML

### Estrutura de Dados

- **Datasets exportáveis** em Parquet
- **Features**: Configuração (replicas, CPU, mem) + Métricas
- **Target**: Fitness score
- **Pronto para**: Treinamento de modelos preditivos

### Integrações Futuras

- **ArgoCD**: Para GitOps
- **Argo Workflows**: Para pipelines
- **ML Models**: Para predição de fitness
- **Auto-scaling preditivo**: Baseado em modelos treinados

## 🔧 Configuração

### Variáveis de Ambiente

- GA: ver `ga/config.py`
- NSGA-II: ver `scripts/run_nsga.py` (helpers `_env_*` e `NSGAConfig`) e `manifests/nsga-job.yaml`

Principais (compartilhadas entre os dois algoritmos):
- `PROMETHEUS_URL`, `PROM_QUERY_TIMEOUT`
- `K8S_DEPLOYMENT_NAME`, `K8S_NAMESPACE`
- `APP_URL`, `APP_LABEL`
- `LOAD_TEST_DURATION`, `LOAD_TEST_CONCURRENCY`, `LOAD_TEST_PROFILE`

Específicas do GA: `GA_POPULATION`, `GA_GENERATIONS`, `GA_MUTATION_RATE`, `GA_CROSSOVER_RATE`, ...
Específicas do NSGA-II: `NSGA_POPULATION`, `NSGA_GENERATIONS`, `NSGA_CROSSOVER_RATE`, `NSGA_MUTATION_RATE`, `NSGA_CPU_*`, `NSGA_MEM_*`, `NSGA_REP_*`, `NSGA_OUTPUT_DIR`, `NSGA_MOCK`, ...

## 📝 Boas Práticas Implementadas

1. **Separação de responsabilidades**: Módulos bem definidos
2. **Type hints**: Tipagem completa
3. **Error handling**: Exceções customizadas
4. **Logging estruturado**: Logs informativos
5. **Configuração centralizada**: Dataclasses de config
6. **Cache inteligente**: Evita reavaliações
7. **Paralelização opcional**: Para avaliações
8. **Rollback automático**: Segurança no K8s
9. **Exportação de dados**: Para análise e ML
10. **Documentação**: Docstrings completas

## 🎓 Decisões Arquiteturais

### Por que modular?

- **Manutenibilidade**: Fácil de entender e modificar
- **Testabilidade**: Cada módulo pode ser testado isoladamente
- **Escalabilidade**: Fácil adicionar novos componentes
- **Reutilização**: Componentes podem ser usados em outros projetos

### Por que dataclasses?

- **Type safety**: Validação em tempo de desenvolvimento
- **Imutabilidade**: Evita bugs de estado
- **Serialização**: Fácil converter para JSON/dict
- **Legibilidade**: Código mais limpo

### Por que cache?

- **Performance**: Evita reavaliações custosas
- **Economia**: Menos recursos do cluster
- **Reprodutibilidade**: Resultados consistentes

## 🔮 Evolução Futura

1. **Multi-objective Optimization** ✅ *implementado em `nsga/`*
   - NSGA-II com saturação, recurso provisionado e throughput como objetivos
   - Próximos passos: experimentar SPEA2/IBEA, hipervolume como métrica de qualidade,
     comparação direta GA vs. NSGA-II em tese.

2. **Model-based Autoscaling**
   - Treinar modelos ML com os datasets exportados (CSV/Parquet do GA + CSVs por geração do NSGA-II)
   - Predizer objetivos sem executar load test (surrogate model)
   - Ajustar recursos proativamente

3. **Distributed Search**
   - Múltiplos clusters
   - Populações isoladas com migração entre nós

4. **Real-time Optimization**
   - Otimização contínua
   - Adaptação a mudanças de carga / drift de workload


