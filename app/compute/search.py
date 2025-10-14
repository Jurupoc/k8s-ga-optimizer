import random

def generate_random_list(size: int):
    """Gera uma lista de números aleatórios ordenada."""
    data = [random.randint(0, size * 10) for _ in range(size)]
    data.sort()
    return data

def binary_search(arr, target):
    """Busca binária em lista ordenada."""
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return True
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return False
