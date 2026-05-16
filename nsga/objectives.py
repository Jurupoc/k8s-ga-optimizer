"""
Cálculo de objetivos a partir de métricas cruas e genome.

Os três objetivos do NSGA-II (todos para minimização) são:

- ``f1``: Saturação — combinação ponderada de CPU throttling e pico de memória.
  Reflete o quão pressionado o pod está; valores baixos indicam folga.

- ``f2``: Recursos provisionados — proxy do "custo" da configuração.
  Combina CPU (em cores) e memória (em GiB) ponderados, multiplicado pelas
  réplicas. Quanto menor, mais barata a configuração.

- ``f3``: ``-throughput`` — negativo do throughput (rps) para que o NSGA-II,
  que minimiza, maximize a vazão.

Os pesos podem ser ajustados via ``ResourceWeights`` (para ``f2``) e
``SaturationWeights`` (para ``f1``). Os defaults preservam o comportamento
histórico do projeto (1.0/1.0 em ambos os pares).
"""
from dataclasses import dataclass

from nsga.domain import Genome, Objectives, RawMetrics


@dataclass(frozen=True)
class ResourceWeights:
    """
    Pesos para combinar CPU (cores) e memória (GiB) em ``f2``.

    Default ``(1.0, 1.0)`` significa que 1 core e 1 GiB têm o mesmo "custo"
    relativo na função objetivo. Esse é um trade-off arbitrário: ajuste
    conforme o custo real da sua infraestrutura (ex.: se memória for ~3x
    mais cara que CPU no seu provedor, use ``ResourceWeights(1.0, 3.0)``).
    """
    cpu: float = 1.0
    mem: float = 1.0


@dataclass(frozen=True)
class SaturationWeights:
    """
    Pesos para combinar CPU throttling e pico de memória em ``f1``.

    Default ``(0.5, 0.5)`` dá importância igual aos dois sinais. Os pesos
    devem somar 1.0 para manter ``f1 ∈ [0, 1]``, mas isso não é validado.
    """
    cpu_throttle: float = 0.5
    mem_peak: float = 0.5


# Constantes pra evitar instanciação repetida quando o caller não passa pesos
_DEFAULT_RESOURCE_WEIGHTS = ResourceWeights()
_DEFAULT_SATURATION_WEIGHTS = SaturationWeights()


def calculate_objectives(
    genome: Genome,
    metrics: RawMetrics,
    resource_weights: ResourceWeights | None = None,
    saturation_weights: SaturationWeights | None = None,
) -> Objectives:
    """
    Calcula os três objetivos a partir do genome e das métricas medidas.

    Fórmulas (todas para minimização):

    .. code-block:: text

        f1 = w_throttle * cpu_throttle_rate + w_mem_peak * mem_peak_ratio
        f2 = replicas * (w_cpu * cpu_cores + w_mem * mem_gib)
        f3 = -throughput_rps

    onde ``cpu_cores = cpu_m / 1000`` e ``mem_gib = mem_mib / 1024``.

    Args:
        genome: Configuração de recursos avaliada.
        metrics: Métricas cruas (Prometheus + load test).
        resource_weights: Pesos para CPU/MEM em ``f2`` (default 1:1).
        saturation_weights: Pesos para throttle/mem peak em ``f1`` (default 0.5/0.5).

    Returns:
        ``Objectives`` com ``f1``, ``f2`` e ``f3`` calculados.
    """
    rw = resource_weights or _DEFAULT_RESOURCE_WEIGHTS
    sw = saturation_weights or _DEFAULT_SATURATION_WEIGHTS

    f1 = sw.cpu_throttle * metrics.cpu_throttle_rate + sw.mem_peak * metrics.mem_peak_ratio

    cpu_cores = genome.cpu_m / 1000.0
    mem_gib = genome.mem_mib / 1024.0
    f2 = genome.replicas * (rw.cpu * cpu_cores + rw.mem * mem_gib)

    f3 = -metrics.throughput_rps

    return Objectives(f1=f1, f2=f2, f3=f3)


def penalty_objectives(
    genome: Genome,
    resource_weights: ResourceWeights | None = None,
    *,
    f1_penalty: float = 10.0,
    f3_penalty: float = 0.0,
) -> Objectives:
    """
    Retorna objetivos com penalidade para avaliações que falharam (FAIL/TIMEOUT).

    Estratégia:
    - ``f1`` recebe um valor alto (default 10.0) para que o indivíduo seja
      dominado por qualquer avaliação real (cuja saturação é ≤ 1.0).
    - ``f2`` é calculado normalmente — os recursos foram de fato provisionados.
    - ``f3`` recebe 0.0 (throughput zero, pior caso possível para minimização
      de ``-throughput``).

    Args:
        genome: Configuração que falhou.
        resource_weights: Mesmos pesos usados em ``calculate_objectives``.
        f1_penalty: Valor de saturação atribuído à falha (deve ser >> 1).
        f3_penalty: Valor de throughput negativo da penalidade (default 0.0).

    Returns:
        ``Objectives`` com penalidade.
    """
    rw = resource_weights or _DEFAULT_RESOURCE_WEIGHTS

    cpu_cores = genome.cpu_m / 1000.0
    mem_gib = genome.mem_mib / 1024.0
    f2 = genome.replicas * (rw.cpu * cpu_cores + rw.mem * mem_gib)

    return Objectives(f1=f1_penalty, f2=f2, f3=f3_penalty)
