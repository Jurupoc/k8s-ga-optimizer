import random

def generate_random_list(size: int):
    """Gera uma lista de números inteiros aleatórios."""
    return [random.randint(0, size * 10) for _ in range(size)]

def quicksort(arr):
    """Implementação recursiva do QuickSort."""
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    left = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    return quicksort(left) + middle + quicksort(right)
