#!/usr/bin/env python3
"""Teste de parsing de memória Kubernetes."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from integrations.k8s_client import KubernetesClient

# Cria cliente (sem conectar)
client = KubernetesClient()

# Testes de memória
test_cases_memory = [
    ("256Mi", 256),
    ("512Mi", 512),
    ("1Gi", 1024),
    ("2Gi", 2048),
    ("1024Mi", 1024),
    ("1G", 1000),
    ("512M", 512),
    ("1024Ki", 1),
    ("1048576Ki", 1024),
]

print("Testing memory parsing:")
print("-" * 60)
for input_str, expected in test_cases_memory:
    try:
        result = client._parse_memory_to_mb(input_str)
        status = "✓" if result == expected else "✗"
        print(f"{status} {input_str:>12} -> {result:>6} MB (expected: {expected})")
        if result != expected:
            print(f"  ERROR: Got {result}, expected {expected}")
    except Exception as e:
        print(f"✗ {input_str:>12} -> ERROR: {e}")

# Testes de CPU
test_cases_cpu = [
    ("500m", 0.5),
    ("1000m", 1.0),
    ("250m", 0.25),
    ("1", 1.0),
    ("2", 2.0),
    ("1.5", 1.5),
    ("0.5", 0.5),
]

print("\nTesting CPU parsing:")
print("-" * 60)
for input_str, expected in test_cases_cpu:
    try:
        result = client._parse_cpu_to_cores(input_str)
        status = "✓" if abs(result - expected) < 0.001 else "✗"
        print(f"{status} {input_str:>12} -> {result:>6} cores (expected: {expected})")
        if abs(result - expected) >= 0.001:
            print(f"  ERROR: Got {result}, expected {expected}")
    except Exception as e:
        print(f"✗ {input_str:>12} -> ERROR: {e}")

print("\n" + "=" * 60)
print("All tests completed!")
