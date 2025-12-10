# integrations/__init__.py
"""Módulo de integrações com sistemas externos."""

from .prometheus_client import PrometheusClient
from .k8s_client import KubernetesClient

__all__ = ["PrometheusClient", "KubernetesClient"]


