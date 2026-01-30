#!/usr/bin/env python3
"""Teste simples de parsing."""

def parse_memory_to_mb(mem_str: str) -> int:
    """Converte string de memória Kubernetes para MB."""
    mem_str = mem_str.strip()
    
    if mem_str.endswith("Gi"):
        return int(float(mem_str.rstrip("Gi")) * 1024)
    elif mem_str.endswith("G"):
        return int(float(mem_str.rstrip("G")) * 1000)
    elif mem_str.endswith("Mi"):
        return int(mem_str.rstrip("Mi"))
    elif mem_str.endswith("M"):
        return int(mem_str.rstrip("M"))
    elif mem_str.endswith("Ki"):
        return int(float(mem_str.rstrip("Ki")) / 1024)
    elif mem_str.endswith("K"):
        return int(float(mem_str.rstrip("K")) / 1000)
    else:
        return int(float(mem_str) / (1024 * 1024))

# Testes
tests = [
    ("1Gi", 1024),
    ("2Gi", 2048),
    ("256Mi", 256),
    ("512Mi", 512),
    ("1G", 1000),
]

print("Testing memory parsing:")
for input_str, expected in tests:
    result = parse_memory_to_mb(input_str)
    status = "OK" if result == expected else "FAIL"
    print(f"  {status}: {input_str} -> {result} MB (expected: {expected})")
