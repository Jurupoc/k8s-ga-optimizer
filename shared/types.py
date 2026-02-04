
from dataclasses import dataclass

@dataclass
class GenericIndividual:
    cpu_limit: float
    memory_limit: float
    replicas: int