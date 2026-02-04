"""
Cache de avaliações em disco para evitar re-avaliações.
"""
import json
import hashlib
from pathlib import Path
from typing import Optional
from nsga.domain import Genome, EvaluationResult


class EvaluationCache:
    """
    Cache simples em disco (JSONL) para resultados de avaliação.
    
    Chave: hash(genome + load_profile)
    Valor: EvaluationResult serializado
    """
    
    def __init__(self, cache_file: Path, load_profile: str = "default"):
        """
        Inicializa o cache.
        
        Args:
            cache_file: Caminho do arquivo de cache (JSONL)
            load_profile: Identificador do perfil de carga (para diferenciar experimentos)
        """
        self.cache_file = cache_file
        self.load_profile = load_profile
        self.cache = {}
        
        # Criar diretório se não existir
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Carregar cache existente
        self._load()
    
    def _make_key(self, genome: Genome) -> str:
        """
        Cria chave de cache baseada no genome e perfil de carga.
        
        Args:
            genome: Genome a ser usado como chave
            
        Returns:
            Hash string
        """
        key_data = f"{genome.cpu_m}:{genome.mem_mib}:{genome.replicas}:{self.load_profile}"
        return hashlib.sha256(key_data.encode()).hexdigest()
    
    def get(self, genome: Genome) -> Optional[EvaluationResult]:
        """
        Busca resultado no cache.
        
        Args:
            genome: Genome a ser buscado
            
        Returns:
            EvaluationResult se encontrado, None caso contrário
        """
        key = self._make_key(genome)
        if key in self.cache:
            return EvaluationResult.from_dict(self.cache[key])
        return None
    
    def put(self, result: EvaluationResult) -> None:
        """
        Armazena resultado no cache.
        
        Args:
            result: Resultado a ser armazenado
        """
        key = self._make_key(result.genome)
        self.cache[key] = result.to_dict()
        
        # Append ao arquivo
        self._append(key, result)
    
    def _load(self) -> None:
        """Carrega cache do disco."""
        if not self.cache_file.exists():
            return
        
        try:
            with open(self.cache_file, 'r') as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line)
                        key = entry['key']
                        self.cache[key] = entry['result']
        except Exception as e:
            print(f"Aviso: Erro ao carregar cache: {e}")
            self.cache = {}
    
    def _append(self, key: str, result: EvaluationResult) -> None:
        """
        Adiciona entrada ao arquivo de cache.
        
        Args:
            key: Chave do cache
            result: Resultado a ser armazenado
        """
        try:
            with open(self.cache_file, 'a') as f:
                entry = {
                    'key': key,
                    'result': result.to_dict()
                }
                f.write(json.dumps(entry) + '\n')
        except Exception as e:
            print(f"Aviso: Erro ao escrever cache: {e}")
    
    def size(self) -> int:
        """
        Retorna o número de entradas no cache.
        
        Returns:
            Número de entradas
        """
        return len(self.cache)
    
    def hit_rate(self, hits: int, total: int) -> float:
        """
        Calcula taxa de acerto do cache.
        
        Args:
            hits: Número de hits
            total: Número total de buscas
            
        Returns:
            Taxa de acerto (0..1)
        """
        return hits / total if total > 0 else 0.0
