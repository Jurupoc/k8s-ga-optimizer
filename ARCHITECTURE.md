# Arquitetura do Sistema - Kubernetes GA Optimizer

## 📐 Visão Geral

Sistema de otimização automática de recursos Kubernetes usando Algoritmos Genéticos, projetado para evoluir para autoscaling preditivo baseado em ML.

## 🏗️ Estrutura Modular

```
/k8s-ga-optimizer
│
├── ga/                          # Módulo do Algoritmo Genético
│   ├── optimizer.py            # Executor principal do GA
│   ├── population.py            # Gerenciamento de população
│   ├── fitness.py               # Cálculo de fitness multicritério
│   ├── cache.py                 # Cache de resultados
│   ├── types.py                 # Tipos de dados (dataclasses)
│   ├── config.py                # Configurações centralizadas
│   ├── exceptions.py            # Exceções customizadas
│   └── utils.py                 # Utilitários
│
├── integrations/                # Integrações com sistemas externos
│   ├── prometheus_client.py     # Cliente Prometheus robusto
│   └── k8s_client.py            # Cliente Kubernetes com rollback
│
├── load/                        # Testes de carga
│   ├── load_test.py             # Executor de load tests
│   └── workload_profiles.py     # Perfis de carga (burst, sustained, etc)
│
├── app/                         # Aplicação de teste
│   ├── main.py                  # API FastAPI
│   ├── routes.py                # Rotas (planejado)
│   ├── db.py                    # SQLite para DB-bound workloads
│   ├── compute/                 # Operações CPU-bound
│   └── metrics.py               # Métricas Prometheus
│
├── scripts/                     # Scripts utilitários
│   ├── run_ga.py                # Script principal de execução
│   └── export_metrics.py        # Exportação CSV/Parquet/JSON
│
└── manifests/                   # Kubernetes manifests
    ├── deployment-app-ga.yaml
    └── ...
```

## 🔄 Fluxo de Execução

```
1. Inicialização
   ├── Carrega configurações (env vars)
   ├── Cria população inicial aleatória
   └── Inicializa clientes (Prometheus, K8s, Load Tester)

2. Loop de Gerações
   ├── Para cada indivíduo na população:
   │   ├── Verifica cache
   │   ├── Aplica configuração no K8s
   │   ├── Aguarda rollout
   │   ├── Executa load test
   │   ├── Coleta métricas do Prometheus
   │   └── Calcula fitness
   │
   ├── Calcula estatísticas da geração
   ├── Seleciona elite e sobreviventes
   ├── Gera filhos (crossover + mutação)
   └── Cria nova população

3. Finalização
   ├── Aplica melhor configuração
   ├── Exporta resultados
   └── Gera relatórios
```

## 🧬 Algoritmo Genético

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

Ver `ga/config.py` para lista completa.

Principais:
- `GA_POPULATION`, `GA_GENERATIONS`, etc.
- `PROMETHEUS_URL`
- `K8S_DEPLOYMENT_NAME`, `K8S_NAMESPACE`
- `APP_URL`, `APP_LABEL`
- `LOAD_TEST_DURATION`, `LOAD_TEST_CONCURRENCY`

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

1. **Model-based Autoscaling**
   - Treinar modelos ML com dados históricos
   - Predizer fitness sem executar
   - Ajustar recursos proativamente

2. **Multi-objective Optimization**
   - NSGA-II ou similar
   - Otimizar múltiplos objetivos simultaneamente

3. **Distributed GA**
   - Múltiplos clusters
   - Populações isoladas com migração

4. **Real-time Optimization**
   - Otimização contínua
   - Adaptação a mudanças de carga


