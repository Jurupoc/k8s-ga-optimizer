# ===============================
# Makefile para app-ga (Minikube)
# ===============================

# Nome da imagem
IMAGE_NAME = app-ga
IMAGE_TAG = latest
DEPLOYMENT = app-ga
NAMESPACE = default

# Caminho dos manifests Kubernetes
MANIFESTS = manifests/app-ga-deployment.yaml manifests/app-ga-service.yaml manifests/app-ga-service-monitor.yaml

# ===============================
#  Targets principais
# ===============================

## Builda a imagem dentro do Docker do Minikube
build:
	@echo "Conectando ao Docker do Minikube..."
	eval $$(minikube docker-env) && \
	echo "Buildando imagem $(IMAGE_NAME):$(IMAGE_TAG)..." && \
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .

## Carrega a imagem local no Minikube (caso tenha buildado fora)
load:
	@echo "Enviando imagem local para o Minikube..."
	minikube image load $(IMAGE_NAME):$(IMAGE_TAG)

## Aplica (ou atualiza) os manifests do app no cluster
apply:
	@echo "Aplicando manifests..."
	kubectl apply -f $(MANIFESTS)

## Reinicia o Deployment para usar a nova imagem
restart:
	@echo "Reiniciando deployment $(DEPLOYMENT)..."
	kubectl rollout restart deployment $(DEPLOYMENT) -n $(NAMESPACE)

## Builda, aplica e reinicia (pipeline completo)
deploy: build apply restart
	@echo "Deploy completo! Aguarde alguns segundos para o pod iniciar."

## Mostra os pods do app
status:
	@echo "Status dos pods:"
	kubectl get pods -l app=$(DEPLOYMENT) -n $(NAMESPACE) -o wide

## Faz port-forward para acessar a API localmente
port-forward:
	@echo "Acessando API em http://localhost:8080"
	kubectl port-forward svc/$(DEPLOYMENT) 8080:8080 -n $(NAMESPACE)

## Faz port-forward para acessar o Prometheus
prometheus:
	@echo "Acessando Prometheus em http://localhost:9090"
	kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090

## Remove todos os recursos do app
clean:
	@echo "Limpando recursos..."
	kubectl delete -f $(MANIFESTS) --ignore-not-found

## Mostra logs do pod atual
logs:
	@echo "Logs do pod atual:"
	kubectl logs -l app=$(DEPLOYMENT) -n $(NAMESPACE) -f

## Abre um shell dentro do pod
shell:
	kubectl exec -it $$(kubectl get pod -l app=$(DEPLOYMENT) -o name -n $(NAMESPACE)) -- /bin/bash || \
	kubectl exec -it $$(kubectl get pod -l app=$(DEPLOYMENT) -o name -n $(NAMESPACE)) -- /bin/sh

## Mostra as métricas brutas (endpoint /metrics)
metrics:
	kubectl port-forward svc/$(DEPLOYMENT) 8000:8000 -n $(NAMESPACE) &
	sleep 2
	curl -s http://localhost:8000/metrics | head -20
