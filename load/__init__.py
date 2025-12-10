# load/__init__.py
"""Módulo de testes de carga e perfis de workload."""

from .load_test import LoadTester, LoadTestResult
from .workload_profiles import WorkloadProfile, get_profile

__all__ = ["LoadTester", "LoadTestResult", "WorkloadProfile", "get_profile"]


