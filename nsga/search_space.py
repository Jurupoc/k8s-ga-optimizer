"""
Definição do espaço de busca para otimização de recursos.
"""
from dataclasses import dataclass
import random
from nsga.domain import Genome


@dataclass
class SearchSpace:
    """
    Define os limites e steps para cada gene.
    
    Attributes:
        cpu_min: CPU mínima em millicores
        cpu_max: CPU máxima em millicores
        cpu_step: Step para mutação de CPU
        mem_min: Memória mínima em MiB
        mem_max: Memória máxima em MiB
        mem_step: Step para mutação de memória
        rep_min: Número mínimo de réplicas
        rep_max: Número máximo de réplicas
    """
    cpu_min: int
    cpu_max: int
    cpu_step: int
    mem_min: int
    mem_max: int
    mem_step: int
    rep_min: int
    rep_max: int
    
    def __post_init__(self):
        """Valida os parâmetros do espaço de busca."""
        assert self.cpu_min > 0 and self.cpu_min <= self.cpu_max, "CPU range inválido"
        assert self.cpu_step > 0, "CPU step deve ser positivo"
        assert self.mem_min > 0 and self.mem_min <= self.mem_max, "Memory range inválido"
        assert self.mem_step > 0, "Memory step deve ser positivo"
        assert self.rep_min > 0 and self.rep_min <= self.rep_max, "Replicas range inválido"
    
    def random_genome(self, rng: random.Random) -> Genome:
        """
        Gera um genome aleatório válido dentro do espaço de busca.
        
        Args:
            rng: Gerador de números aleatórios
            
        Returns:
            Genome aleatório válido
        """
        # Gerar valores aleatórios respeitando os steps
        cpu_range = (self.cpu_max - self.cpu_min) // self.cpu_step
        cpu_m = self.cpu_min + rng.randint(0, cpu_range) * self.cpu_step
        
        mem_range = (self.mem_max - self.mem_min) // self.mem_step
        mem_mib = self.mem_min + rng.randint(0, mem_range) * self.mem_step
        
        replicas = rng.randint(self.rep_min, self.rep_max)
        
        return Genome(cpu_m=cpu_m, mem_mib=mem_mib, replicas=replicas)
    
    def repair(self, genome: Genome) -> Genome:
        """
        Repara um genome para garantir que está dentro dos limites.
        Arredonda para o step mais próximo.
        
        Args:
            genome: Genome a ser reparado
            
        Returns:
            Genome reparado
        """
        # Clamp e arredondar para step mais próximo
        cpu_m = max(self.cpu_min, min(self.cpu_max, genome.cpu_m))
        cpu_m = self.cpu_min + ((cpu_m - self.cpu_min) // self.cpu_step) * self.cpu_step
        
        mem_mib = max(self.mem_min, min(self.mem_max, genome.mem_mib))
        mem_mib = self.mem_min + ((mem_mib - self.mem_min) // self.mem_step) * self.mem_step
        
        replicas = max(self.rep_min, min(self.rep_max, genome.replicas))
        
        return Genome(cpu_m=cpu_m, mem_mib=mem_mib, replicas=replicas)
    
    def is_valid(self, genome: Genome) -> bool:
        """
        Verifica se um genome está dentro dos limites.
        
        Args:
            genome: Genome a ser validado
            
        Returns:
            True se válido, False caso contrário
        """
        if not (self.cpu_min <= genome.cpu_m <= self.cpu_max):
            return False
        if not (self.mem_min <= genome.mem_mib <= self.mem_max):
            return False
        if not (self.rep_min <= genome.replicas <= self.rep_max):
            return False
        
        # Verificar se está nos steps corretos
        if (genome.cpu_m - self.cpu_min) % self.cpu_step != 0:
            return False
        if (genome.mem_mib - self.mem_min) % self.mem_step != 0:
            return False
        
        return True
    
    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "cpu_min": self.cpu_min,
            "cpu_max": self.cpu_max,
            "cpu_step": self.cpu_step,
            "mem_min": self.mem_min,
            "mem_max": self.mem_max,
            "mem_step": self.mem_step,
            "rep_min": self.rep_min,
            "rep_max": self.rep_max
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SearchSpace":
        """Cria SearchSpace a partir de dicionário."""
        return cls(**data)
    
    @classmethod
    def default(cls) -> "SearchSpace":
        """
        Retorna um SearchSpace padrão seguro para testes.
        
        Returns:
            SearchSpace com valores conservadores
        """
        return cls(
            cpu_min=100,      # 0.1 core
            cpu_max=2000,     # 2 cores
            cpu_step=100,     # 0.1 core
            mem_min=128,      # 128 MiB
            mem_max=2048,     # 2 GiB
            mem_step=128,     # 128 MiB
            rep_min=1,
            rep_max=10
        )
