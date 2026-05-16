# Makefile para Kubernetes GA Optimizer
# Atualizado para estrutura modular refatorada

# Variáveis
APP_NAME = app-ga
GA_APP_NAME = ga-optimizer
NSGA_APP_NAME = nsga-optimizer
APP_IMAGE = $(APP_NAME):latest
LOADTEST_IMAGE = $(APP_NAME)-loadtest:latest
GA_IMAGE = $(GA_APP_NAME):latest
NSGA_IMAGE = $(NSGA_APP_NAME):latest
NAMESPACE = default
MONITOR_NAMESPACE = monitoring
LOADTEST_DURATION = 60
LOADTEST_CONCURRENCY = 20
GA_OUTPUT = ga_results.json
GA_CONFIG = ga_config.json
GA_MANIFEST = manifests/ga-job.yaml
NSGA_MANIFEST = manifests/nsga-job.yaml

# Python e ambiente
PYTHON = python
VENV = .venv

# =====================================================
# Setup e Dependências
# =====================================================
.PHONY: install
install:
	pip install -r requirements.txt

.PHONY: install-dev
install-dev:
	pip install -r requirements-dev.txt

.PHONY: venv
venv:
	python -m venv $(VENV)
	$(VENV)/bin/pip install -r requirements.txt || $(VENV)/Scripts/pip install -r requirements.txt

# =====================================================
# API
# =====================================================
.PHONY: build-api
build-api:
	minikube image build -t app-ga:latest -f Dockerfile .

.PHONY: deploy-api
deploy-api:
	kubectl apply -f manifests/deployment-app-ga.yaml
	kubectl apply -f manifests/service-app-ga.yaml
	kubectl apply -f manifests/service-monitoring-app-ga.yaml

.PHONY: delete-api
delete-api:
	kubectl delete -f manifests/deployment-app-ga.yaml || true
	kubectl delete -f manifests/service-app-ga.yaml || true
	kubectl delete -f manifests/service-monitoring-app-ga.yaml || true

.PHONY: restart-api
restart-api: delete-api
	sleep 2
	$(MAKE) deploy-api

# =====================================================
# Load Test
# =====================================================
.PHONY: run-load-test
run-load-test:
	@if kubectl get job app-ga-loadtest -n $(NAMESPACE) >/dev/null 2>&1; then \
		echo "Deletando job app-ga-loadtest existente..."; \
		kubectl delete job app-ga-loadtest -n $(NAMESPACE); \
	fi
	minikube image build -f dockerfile.loadtest -t $(LOADTEST_IMAGE) .
	kubectl apply -f manifests/job-loadtest.yaml

# =====================================================
# Algoritmo Genético
# =====================================================

.PHONY: build-ga
build-ga:
	minikube image build -f dockerfile.ga -t $(GA_IMAGE) .

.PHONY: run-ga
run-ga:
	kubectl apply -f $(GA_MANIFEST)

.PHONY: delete-ga
delete-ga:
	kubectl delete job $(GA_APP_NAME) --ignore-not-found=true

.PHONY: logs-ga
logs-ga:
	kubectl logs -f job/$(GA_APP_NAME)

.PHONY: ga
ga:
	minikube image build -f dockerfile.ga -t $(GA_IMAGE) .
	kubectl delete job $(GA_APP_NAME) --ignore-not-found=true
	kubectl apply -f $(GA_MANIFEST)
	kubectl get pods -w

# =====================================================
# NSGA-II (multiobjetivo)
# =====================================================
.PHONY: build-nsga
build-nsga:
	minikube image build -f dockerfile.nsga -t $(NSGA_IMAGE) .

.PHONY: run-nsga
run-nsga:
	kubectl apply -f $(NSGA_MANIFEST)

.PHONY: delete-nsga
delete-nsga:
	kubectl delete job $(NSGA_APP_NAME) --ignore-not-found=true

.PHONY: logs-nsga
logs-nsga:
	kubectl logs -f job/$(NSGA_APP_NAME)

.PHONY: nsga
nsga:
	minikube image build -f dockerfile.nsga -t $(NSGA_IMAGE) .
	kubectl delete job $(NSGA_APP_NAME) --ignore-not-found=true
	kubectl apply -f $(NSGA_MANIFEST)
	kubectl get pods -w

.PHONY: run-nsga-local
run-nsga-local:
	$(PYTHON) -u scripts/run_nsga.py --mock --output-dir nsga_results

# =====================================================
# Exportação de Dados
# =====================================================
.PHONY: export-csv
export-csv:
	$(PYTHON) scripts/export_metrics.py --input $(GA_OUTPUT) --output ga_results.csv --format csv

.PHONY: export-parquet
export-parquet:
	$(PYTHON) scripts/export_metrics.py --input $(GA_OUTPUT) --output ga_results.parquet --format parquet

.PHONY: export-json
export-json:
	$(PYTHON) scripts/export_metrics.py --input $(GA_OUTPUT) --output ga_results_export.json --format json

.PHONY: export-all
export-all: export-csv export-parquet export-json

# =====================================================
# Monitoramento e Debug
# =====================================================
.PHONY: logs-api
logs-api:
	kubectl logs -f deployment/$(APP_NAME) -n $(NAMESPACE)

.PHONY: port-forward
port-forward:
	kubectl port-forward svc/$(APP_NAME) 8080:8080 -n $(NAMESPACE)

.PHONY: port-forward-prometheus
port-forward-prometheus:
	kubectl port-forward svc/monitoring-kube-prometheus-prometheus 9090:9090 -n $(MONITOR_NAMESPACE)

.PHONY: status
status:
	kubectl get deployment $(APP_NAME) -n $(NAMESPACE)
	kubectl get pods -l app=$(APP_NAME) -n $(NAMESPACE)
	kubectl get svc $(APP_NAME) -n $(NAMESPACE)

.PHONY: describe
describe:
	kubectl describe deployment $(APP_NAME) -n $(NAMESPACE)

# =====================================================
# Desenvolvimento e Testes
# =====================================================
.PHONY: test
test:
	$(PYTHON) -m pytest tests/ -v

.PHONY: test-ga
test-ga:
	$(PYTHON) -m pytest ga/tests/ -v || echo "No tests in ga/tests/"

.PHONY: lint
lint:
	flake8 ga/ nsga/ integrations/ load/ scripts/ app/ shared/ --max-line-length=120 --ignore=E501,W503 || true
	mypy ga/ nsga/ integrations/ load/ scripts/ app/ shared/ --ignore-missing-imports || true

.PHONY: format
format:
	black ga/ nsga/ integrations/ load/ scripts/ app/ shared/ --line-length=120

.PHONY: check
check: lint test

# =====================================================
# Utilitários
# =====================================================
.PHONY: shell
shell:
	$(PYTHON) -i -c "import sys; from pathlib import Path; sys.path.insert(0, str(Path.cwd())); from ga import *; from nsga import *; from integrations import *; from load import *"

.PHONY: clean-cache
clean-cache:
	find . -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -r {} + 2>/dev/null || true

.PHONY: clean-results
clean-results:
	rm -f ga_results*.json ga_results*.csv ga_results*.parquet || true

.PHONY: clean
clean: clean-cache clean-results
	docker rmi -f $(APP_IMAGE) || true
	docker rmi -f $(LOADTEST_IMAGE) || true
	docker rmi -f $(GA_IMAGE) || true
	docker rmi -f $(NSGA_IMAGE) || true
	kubectl delete pod -l app=loadtest -n $(NAMESPACE) || true
	kubectl delete job ga-optimizer -n $(NAMESPACE) --ignore-not-found=true
	kubectl delete job nsga-optimizer -n $(NAMESPACE) --ignore-not-found=true

.PHONY: clean-all
clean-all: clean
	kubectl delete -f manifests/ --ignore-not-found=true || true

# =====================================================
# Help
# =====================================================
.PHONY: help
help:
	@echo "Kubernetes GA Optimizer - Makefile"
	@echo ""
	@echo "Setup:"
	@echo "  make install          - Instala dependencias"
	@echo "  make install-dev      - Instala dependencias + dev tools"
	@echo "  make venv             - Cria ambiente virtual"
	@echo ""
	@echo "API:"
	@echo "  make build-api        - Build da imagem Docker da API"
	@echo "  make deploy-api       - Deploy da API no cluster"
	@echo "  make delete-api       - Remove API do cluster"
	@echo "  make restart-api      - Reinicia a API"
	@echo ""
	@echo "Load Test:"
	@echo "  make build-loadtest      - Build da imagem de load test"
	@echo "  make run-load-test       - Executa load test no cluster"
	@echo "  make run-load-test-local - Executa load test localmente"
	@echo ""
	@echo "Algoritmo Genetico (mono-objetivo):"
	@echo "  make build-ga          - Build da imagem Docker do GA"
	@echo "  make run-ga            - Aplica o manifest do GA"
	@echo "  make delete-ga         - Remove o Job do GA"
	@echo "  make logs-ga           - Logs do job GA"
	@echo "  make ga                - Build + delete + apply + watch (atalho)"
	@echo ""
	@echo "NSGA-II (multiobjetivo):"
	@echo "  make build-nsga        - Build da imagem Docker do NSGA-II"
	@echo "  make run-nsga          - Aplica o manifest do NSGA-II"
	@echo "  make delete-nsga       - Remove o Job do NSGA-II"
	@echo "  make logs-nsga         - Logs do job NSGA-II"
	@echo "  make nsga              - Build + delete + apply + watch (atalho)"
	@echo "  make run-nsga-local    - Roda NSGA-II localmente com adapters mock"
	@echo ""
	@echo "Exportacao:"
	@echo "  make export-csv        - Exporta resultados para CSV"
	@echo "  make export-parquet    - Exporta resultados para Parquet"
	@echo "  make export-json       - Exporta resultados para JSON"
	@echo "  make export-all        - Exporta em todos os formatos"
	@echo ""
	@echo "Monitoramento:"
	@echo "  make logs-api                - Logs da API"
	@echo "  make logs-ga                 - Logs do job GA"
	@echo "  make port-forward            - Port forward da API (8080)"
	@echo "  make port-forward-prometheus - Port forward do Prometheus (9090)"
	@echo "  make status                  - Status dos recursos"
	@echo "  make describe                - Descricao detalhada do deployment"
	@echo ""
	@echo "Desenvolvimento:"
	@echo "  make test              - Executa testes"
	@echo "  make lint              - Verifica codigo (flake8 + mypy)"
	@echo "  make format            - Formata codigo (black)"
	@echo "  make check             - Lint + testes"
	@echo "  make shell             - Shell interativo Python"
	@echo ""
	@echo "Limpeza:"
	@echo "  make clean-cache       - Remove __pycache__ e .pyc"
	@echo "  make clean-results     - Remove arquivos de resultados"
	@echo "  make clean             - Limpeza completa (imagens + pods)"
	@echo "  make clean-all         - Limpeza completa + manifests"
	@echo ""
	@echo "Variaveis configuraveis:"
	@echo "  APP_NAME=$(APP_NAME)"
	@echo "  NAMESPACE=$(NAMESPACE)"
	@echo "  LOADTEST_DURATION=$(LOADTEST_DURATION)"
	@echo "  LOADTEST_CONCURRENCY=$(LOADTEST_CONCURRENCY)"
	@echo "  GA_OUTPUT=$(GA_OUTPUT)"

.DEFAULT_GOAL := help
