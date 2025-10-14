def generate_primes(limit: int):
    """Gera números primos até um limite usando o Crivo de Eratóstenes."""
    sieve = [True] * (limit + 1)
    sieve[0] = sieve[1] = False

    for i in range(2, int(limit ** 0.5) + 1):
        if sieve[i]:
            for j in range(i * i, limit + 1, i):
                sieve[j] = False

    return [i for i, is_prime in enumerate(sieve) if is_prime]
