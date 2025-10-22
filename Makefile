# Makefile para Kubernetes GA Optimizer

# Variáveis
APP_NAME = app-ga
APP_IMAGE = $(APP_NAME):latest
LOADTEST_IMAGE = $(APP_NAME)-loadtest:latest
NAMESPACE = default
MONITOR_NAMESPACE = monitoring
LOADTEST_DURATION = 60
LOADTEST_THREADS = 20

# =====================================================
# API
# =====================================================
.PHONY: build-api
build-api:
	docker build -t $(APP_IMAGE) .

.PHONY: push-api
push-api:
	docker push $(APP_IMAGE)

.PHONY: deploy-api
deploy-api:
	kubectl apply -f manifests/deployment.yaml
	kubectl apply -f manifests/service.yaml
	kubectl apply -f manifests/service-monitor.yaml

.PHONY: delete-api
delete-api:
	kubectl delete -f manifests/deployment.yaml || true
	kubectl delete -f manifests/service.yaml || true
	kubectl delete -f manifests/service-monitor.yaml || true

# =====================================================
# Load Test
# =====================================================
.PHONY: build-loadtest
build-loadtest:
	docker build -t $(LOADTEST_IMAGE) tests/

.PHONY: run-load-test
run-load-test:
	kubectl run -it --rm loadtest \
		--image=$(LOADTEST_IMAGE) \
		--restart=Never \
		--env LOADTEST_DURATION=$(LOADTEST_DURATION) \
		--env LOADTEST_THREADS=$(LOADTEST_THREADS)

# =====================================================
# Algoritmo Genético
# =====================================================
.PHONY: run-ga
run-ga:
	python ga/optimizer.py

# =====================================================
# Monitoramento e debug
# =====================================================
.PHONY: logs-api
logs-api:
	kubectl logs -f deployment/$(APP_NAME)

.PHONY: port-forward
port-forward:
	kubectl port-forward svc/$(APP_NAME) 8080:8080

# =====================================================
# Limpeza
# =====================================================
.PHONY: clean
clean:
	docker rmi -f $(APP_IMAGE) || true
	docker rmi -f $(LOADTEST_IMAGE) || true
	kubectl delete pod -l app=loadtest || true
