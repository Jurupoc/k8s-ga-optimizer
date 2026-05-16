"""
Implementação do NSGA-II: fast non-dominated sorting, crowding distance e selection.
"""
import random
from nsga.domain import Individual


def fast_non_dominated_sort(population: list[Individual]) -> list[list[Individual]]:
    """
    Fast non-dominated sorting (Deb et al., 2002) para classificar indivíduos
    em frentes de Pareto.

    Trabalha internamente com índices para evitar buscas O(n) por indivíduo
    e explora a antissimetria de `dominates` (se i domina j, então j não
    domina i) iterando apenas pares (i, j) com i < j.

    Complexidade: O(M · N²) onde M = nº de objetivos e N = tamanho da população.

    Args:
        population: lista de indivíduos

    Returns:
        lista de frentes (cada frente é uma lista de indivíduos), ordenadas
        do melhor (rank 0) para o pior. Os atributos `rank` dos indivíduos
        são atualizados in-place.
    """
    n = len(population)
    if n == 0:
        return []

    # Para cada indivíduo p (representado pelo índice):
    # - S[p]: índices dos indivíduos dominados por p
    # - n_dominated[p]: número de indivíduos que dominam p
    S: list[list[int]] = [[] for _ in range(n)]
    n_dominated: list[int] = [0] * n

    # Calcular relações de dominância iterando pares (i, j) com i < j
    for i in range(n):
        for j in range(i + 1, n):
            if population[i].dominates(population[j]):
                S[i].append(j)
                n_dominated[j] += 1
            elif population[j].dominates(population[i]):
                S[j].append(i)
                n_dominated[i] += 1

    # Frente 0 = indivíduos não dominados por ninguém
    first_front: list[int] = []
    for i in range(n):
        if n_dominated[i] == 0:
            population[i].rank = 0
            first_front.append(i)

    fronts_idx: list[list[int]] = [first_front]

    # Construir frentes subsequentes propagando dominância
    front_idx = 0
    while front_idx < len(fronts_idx) and fronts_idx[front_idx]:
        next_front: list[int] = []

        for p_idx in fronts_idx[front_idx]:
            for q_idx in S[p_idx]:
                n_dominated[q_idx] -= 1
                if n_dominated[q_idx] == 0:
                    population[q_idx].rank = front_idx + 1
                    next_front.append(q_idx)

        front_idx += 1
        if next_front:
            fronts_idx.append(next_front)

    # Converter índices para indivíduos no formato de retorno
    return [[population[i] for i in front] for front in fronts_idx]


def calculate_crowding_distance(front: list[Individual]) -> None:
    """
    Calcula crowding distance para indivíduos em uma frente.
    Modifica os indivíduos in-place.

    Args:
        front: lista de indivíduos na mesma frente
    """
    n = len(front)

    if n == 0:
        return

    # Inicializar crowding distance
    for ind in front:
        ind.crowding_distance = 0.0

    # Se só tem 1 ou 2 indivíduos, todos têm distância infinita
    if n <= 2:
        for ind in front:
            ind.crowding_distance = float('inf')
        return

    # Para cada objetivo
    objective_names: list[str] = ['f1', 'f2', 'f3']

    for obj_name in objective_names:
        def _value(ind: Individual, _name: str = obj_name) -> float:
            return float(getattr(ind.objectives, _name))

        # Ordenar por objetivo
        front_sorted = sorted(front, key=_value)

        # Extremos têm distância infinita
        front_sorted[0].crowding_distance = float('inf')
        front_sorted[-1].crowding_distance = float('inf')

        # Calcular range do objetivo
        obj_min = _value(front_sorted[0])
        obj_max = _value(front_sorted[-1])
        obj_range = obj_max - obj_min

        # Evitar divisão por zero
        if obj_range == 0:
            continue

        # Calcular crowding distance para indivíduos intermediários
        for i in range(1, n - 1):
            if front_sorted[i].crowding_distance == float('inf'):
                continue

            obj_prev = _value(front_sorted[i - 1])
            obj_next = _value(front_sorted[i + 1])

            front_sorted[i].crowding_distance += (obj_next - obj_prev) / obj_range


def crowding_distance_assignment(fronts: list[list[Individual]]) -> None:
    """
    Calcula crowding distance para todas as frentes.

    Args:
        fronts: lista de frentes
    """
    for front in fronts:
        calculate_crowding_distance(front)


def binary_tournament_selection(population: list[Individual], rng: random.Random) -> Individual:
    """
    Seleção por torneio binário baseada em rank e crowding distance.

    Critério:
    1. Menor rank é melhor
    2. Se ranks iguais, maior crowding distance é melhor

    Args:
        population: População de indivíduos
        rng: Gerador de números aleatórios

    Returns:
        Indivíduo selecionado
    """
    # Selecionar dois indivíduos aleatórios
    ind1 = rng.choice(population)
    ind2 = rng.choice(population)

    # Comparar por rank
    if ind1.rank < ind2.rank:
        return ind1
    elif ind2.rank < ind1.rank:
        return ind2

    # Ranks iguais, comparar por crowding distance
    if ind1.crowding_distance > ind2.crowding_distance:
        return ind1
    elif ind2.crowding_distance > ind1.crowding_distance:
        return ind2

    # Empate, escolher aleatório
    return rng.choice([ind1, ind2])


def select_next_population(combined: list[Individual], pop_size: int) -> list[Individual]:
    """
    Seleciona a próxima população usando elitismo (NSGA-II).

    Processo:
    1. Ordena combined por frentes de Pareto
    2. Adiciona frentes completas até não caber mais
    3. Na última frente, ordena por crowding distance e pega os melhores

    Args:
        combined: População combinada (P ∪ Q)
        pop_size: Tamanho da população desejada

    Returns:
        Nova população de tamanho pop_size
    """
    # Fast non-dominated sort
    fronts = fast_non_dominated_sort(combined)

    # Calcular crowding distance
    crowding_distance_assignment(fronts)

    # Selecionar próxima população
    next_pop: list[Individual] = []

    for front in fronts:
        if len(next_pop) + len(front) <= pop_size:
            # Adicionar frente completa
            next_pop.extend(front)
        else:
            # Frente não cabe completa, ordenar por crowding distance
            remaining = pop_size - len(next_pop)
            front_sorted = sorted(front, key=lambda ind: ind.crowding_distance, reverse=True)
            next_pop.extend(front_sorted[:remaining])
            break

    return next_pop
