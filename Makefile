# Makefile para Kubernetes GA Optimizer
# Atualizado para estrutura modular refatorada

# Variáveis
APP_NAME = app-ga
GA_APP_NAME = ga-optimizer
APP_IMAGE = $(APP_NAME):latest
LOADTEST_IMAGE = $(APP_NAME)-loadtest:latest
GA_IMAGE = $(GA_APP_NAME):latest
NAMESPACE = default
MONITOR_NAMESPACE = monitoring
LOADTEST_DURATION = 60
LOADTEST_CONCURRENCY = 20
GA_OUTPUT = ga_results.json
GA_CONFIG = ga_config.json

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
install-dev: install
	pip install pytest pytest-cov black flake8 mypy

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
.PHONY: run-ga
run-ga:
	$(PYTHON) scripts/run_ga.py --output $(GA_OUTPUT)

.PHONY: run-ga-parallel
run-ga-parallel:
	$(PYTHON) scripts/run_ga.py --output $(GA_OUTPUT) --parallel --workers 2

.PHONY: run-ga-config
run-ga-config:
	$(PYTHON) scripts/run_ga.py --config $(GA_CONFIG) --output $(GA_OUTPUT)

.PHONY: run-ga-legacy
run-ga-legacy:
	$(PYTHON) ga/optimizer.py

.PHONY: build-ga
build-ga:
	minikube image build -f dockerfile.ga -t $(GA_IMAGE) .

.PHONY: run-ga-k8s
run-ga-k8s:
	kubectl run -it --rm ga-optimizer \
		--image=$(GA_IMAGE) \
		--restart=Never \
		--env-file .env || true

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

.PHONY: logs-ga
logs-ga:
	kubectl logs -f job/ga-optimizer -n $(NAMESPACE) || kubectl logs -f pod/ga-optimizer -n $(NAMESPACE)

.PHONY: port-forward
port-forward:
	kubectl port-forward svc/$(APP_NAME) 8080:8080 -n $(NAMESPACE)

.PHONY: port-forward-prometheus
port-forward-prometheus:
	kubectl port-forward svc/prometheus-kube-prometheus-prometheus 9090:9090 -n $(MONITOR_NAMESPACE)

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
	flake8 ga/ integrations/ load/ scripts/ app/ --max-line-length=120 --ignore=E501,W503 || true
	mypy ga/ integrations/ load/ scripts/ app/ --ignore-missing-imports || true

.PHONY: format
format:
	black ga/ integrations/ load/ scripts/ app/ --line-length=120

.PHONY: check
check: lint test

# =====================================================
# Utilitários
# =====================================================
.PHONY: shell
shell:
	$(PYTHON) -i -c "import sys; from pathlib import Path; sys.path.insert(0, str(Path.cwd())); from ga import *; from integrations import *; from load import *"

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
	kubectl delete pod -l app=loadtest -n $(NAMESPACE) || true
	kubectl delete pod -l app=ga-optimizer -n $(NAMESPACE) || true

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
	@echo "Algoritmo Genetico:"
	@echo "  make run-ga            - Executa GA (sequencial)"
	@echo "  make run-ga-parallel   - Executa GA com paralelizacao"
	@echo "  make run-ga-config     - Executa GA com arquivo de config"
	@echo "  make run-ga-legacy     - Executa GA via modulo antigo"
	@echo "  make build-ga          - Build da imagem Docker do GA"
	@echo "  make run-ga-k8s        - Executa GA no cluster"
	@echo ""
	@echo "Exportacao:"
	@echo "  make export-csv        - Exporta resultados para CSV"
	@echo "  make export-parquet    - Exporta resultados para Parquet"
	@echo "  make export-json       - Exporta resultados para JSON"
	@echo "  make export-all        - Exporta em todos os formatos"
	@echo ""
	@echo "Monitoramento:"
	@echo "  make logs-api                - Logs da API"
	@echo "  make logs-ga                 - Logs do GA"
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
