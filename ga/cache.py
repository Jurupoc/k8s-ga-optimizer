# ga/cache.py
"""
Sistema de cache para resultados de avaliação.
Evita reavaliar configurações idênticas.

O cache mantém uma cópia em memória (rápida) e, opcionalmente, persiste
em disco no formato JSONL append-only (uma linha por entrada). Isso espelha
o padrão usado em ``nsga/cache.py``:

- Resiliência a crash: avaliações já completadas sobrevivem se o processo
  morrer no meio da run (pod K8s OOM, perda de API server, etc.).
- Reaproveitamento entre runs: re-rodar com a mesma seed e configuração
  pode reusar avaliações anteriores sem refazer o load test.

O carregamento do disco é tentado uma única vez no ``__init__``. Falhas
no append/load são logadas mas não propagadas — o cache em memória continua
funcional mesmo se o disco falhar.
"""

import time
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ga.types import Individual, EvaluationResult, EvaluationStatus, FitnessMetrics
from shared.utils import log


class EvaluationCache:
    """
    Cache de resultados de avaliação.
    """

    # 30 dias — runs do TCC podem se estender por várias semanas, e
    # avaliações K8s são caras (~4 min cada). TTL curto descarta resultados
    # válidos sem motivo. Para invalidar, mude ``load_profile``/``load_params``
    # ou delete o cache.jsonl.
    DEFAULT_TTL_S: float = 30 * 24 * 3600.0

    def __init__(
        self,
        ttl: float = DEFAULT_TTL_S,
        cache_file: Optional[Path] = None,
        load_profile: str = "",
        load_params: Optional[Dict[str, Any]] = None,
    ):
        """
        Inicializa o cache.

        Args:
            ttl: Time-to-live em segundos (default: 1 hora). Entradas
                expiradas são descartadas no ``get`` e em ``cleanup_expired``.
            cache_file: Caminho do arquivo JSONL para persistência opcional.
                Se ``None``, o cache funciona apenas em memória. Quando
                fornecido, o diretório pai é criado se necessário e o cache
                pré-existente é carregado.
            load_profile: Identificador do perfil de carga (ex.: "default",
                "burst"). Entra na chave do cache para invalidar medições
                antigas se o perfil mudar. Empty string mantém retrocompat
                com chaves antigas (sem profile).
            load_params: Parâmetros do load test que afetam as métricas
                (duration, concurrency, endpoint, etc.). Se mudarem, a chave
                muda e medições antigas não dão hit. Espelha exatamente o
                comportamento de ``nsga/cache.py``.

        Notas:
            Quando ``load_profile``/``load_params`` mudam de uma run pra
            outra, as entradas antigas no JSONL ficam inacessíveis (chave
            diferente). Não é problema correto: o ``_load_from_disk`` ainda
            consegue ler, e o cache em memória só serve novas requests com
            a chave atual. Para limpeza opcional, basta deletar o arquivo.
        """
        self.cache: Dict[str, Tuple[float, EvaluationResult]] = {}
        self.ttl = ttl
        self.cache_file: Optional[Path] = cache_file
        self.load_profile: str = load_profile or ""
        self.load_params: Dict[str, Any] = dict(load_params) if load_params else {}

        # Pré-calcula a serialização estável dos parâmetros (mesma
        # convenção usada em ``nsga/cache.py``).
        self._params_signature: str = (
            json.dumps(self.load_params, sort_keys=True, separators=(",", ":"))
            if self.load_params
            else ""
        )

        if self.cache_file is not None:
            try:
                self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                log(f"Failed to create cache directory: {e}", level="warning")
                self.cache_file = None
            else:
                self._load_from_disk()

    def _get_key(self, individual: Individual) -> str:
        """
        Gera chave única para um indivíduo + perfil de carga + params.

        A inclusão de ``load_profile`` e ``load_params`` na chave invalida
        automaticamente medições antigas quando a carga muda — política
        idêntica ao ``nsga/cache.py`` para consistência semântica.

        Args:
            individual: Indivíduo

        Returns:
            Chave hash (SHA-256)
        """
        ind_sig = json.dumps(individual.to_dict(), sort_keys=True)
        # Mantém compat com chaves antigas: só anexa segmentos extras se
        # houver profile/params definidos. Caches gerados sem profile/params
        # continuam usáveis com construtores que também não definam isso.
        parts: list[str] = [ind_sig]
        if self.load_profile:
            parts.append(self.load_profile)
        if self._params_signature:
            parts.append(self._params_signature)
        return hashlib.sha256(":".join(parts).encode()).hexdigest()

    def get(self, individual: Individual) -> Optional[EvaluationResult]:
        """
        Obtém resultado do cache se disponível e válido.

        Args:
            individual: Indivíduo a buscar

        Returns:
            Resultado em cache ou None
        """
        key = self._get_key(individual)

        if key in self.cache:
            timestamp, result = self.cache[key]
            if time.time() - timestamp < self.ttl:
                log(f"Cache hit for individual: {individual}", level="debug")
                return result
            else:
                # Expirou
                del self.cache[key]

        return None

    def put(self, individual: Individual, result: EvaluationResult) -> None:
        """
        Armazena resultado no cache.

        Args:
            individual: Indivíduo
            result: Resultado da avaliação
        """
        key = self._get_key(individual)
        timestamp = time.time()
        self.cache[key] = (timestamp, result)
        self._append_to_disk(key, timestamp, result)
        log(f"Cached result for individual: {individual}", level="debug")

    def _append_to_disk(
        self, key: str, timestamp: float, result: EvaluationResult
    ) -> None:
        """
        Anexa uma entrada ao arquivo JSONL.

        Args:
            key: Chave SHA-256 da entrada.
            timestamp: Timestamp Unix de quando a entrada foi criada.
            result: Resultado serializado via ``EvaluationResult.to_dict()``.
        """
        if self.cache_file is None:
            return
        try:
            entry: Dict[str, Any] = {
                "key": key,
                "timestamp": timestamp,
                "result": result.to_dict(),
            }
            with open(self.cache_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception as e:
            log(f"Failed to append cache entry to disk: {e}", level="warning")

    def _load_from_disk(self) -> None:
        """
        Carrega entradas pré-existentes do arquivo JSONL para o cache em
        memória. Entradas com timestamp expirado (mais antigas que ``ttl``)
        são ignoradas. Falhas de parsing em linhas individuais não abortam
        o carregamento — apenas registram um warning.
        """
        if self.cache_file is None or not self.cache_file.exists():
            return

        now = time.time()
        loaded = 0
        skipped_expired = 0
        skipped_invalid = 0

        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        key = entry["key"]
                        # Tolera formato sem timestamp (cache.jsonl gerado
                        # pelo NSGA-II usa só ``{key, result}``). Nesse
                        # caso assumimos "agora" — qualquer cache cruzado
                        # (NSGA -> GA) é considerado fresco. Como ambos
                        # produzem a mesma chave para o mesmo (genome +
                        # profile + params), os hits são corretos.
                        timestamp = float(entry["timestamp"]) if "timestamp" in entry else now
                        if now - timestamp >= self.ttl:
                            skipped_expired += 1
                            continue
                        result = self._deserialize_result(entry["result"])
                        self.cache[key] = (timestamp, result)
                        loaded += 1
                    except (KeyError, ValueError, TypeError) as e:
                        skipped_invalid += 1
                        log(
                            f"Skipping malformed cache line {line_num}: {e}",
                            level="debug",
                        )
        except Exception as e:
            log(f"Failed to load cache from disk: {e}", level="warning")
            return

        if loaded or skipped_expired or skipped_invalid:
            log(
                f"Cache loaded from disk: {loaded} entries"
                f" (skipped: {skipped_expired} expired, {skipped_invalid} invalid)"
            )

    @staticmethod
    def _deserialize_result(data: Dict[str, Any]) -> EvaluationResult:
        """
        Reconstrói um ``EvaluationResult`` a partir do dicionário serializado.

        Tolerante a campos ausentes (cache files de versões anteriores que
        não tinham ``cpu_throttling``, ``memory_peak_usage`` ou ``generation``
        ainda carregam — ficam com defaults).
        """
        ind_data = data["individual"]
        individual = Individual(
            replicas=int(ind_data["replicas"]),
            cpu_limit=float(ind_data["cpu_limit"]),
            memory_limit=int(ind_data["memory_limit"]),
        )

        metrics_data = data.get("metrics")
        metrics: Optional[FitnessMetrics]
        if metrics_data is None:
            metrics = None
        else:
            evaluated_at_raw = metrics_data.get("evaluated_at")
            if isinstance(evaluated_at_raw, str):
                try:
                    evaluated_at = datetime.fromisoformat(evaluated_at_raw)
                except ValueError:
                    evaluated_at = datetime.now()
            else:
                evaluated_at = datetime.now()

            metrics = FitnessMetrics(
                throughput=float(metrics_data.get("throughput", 0.0)),
                avg_latency=float(metrics_data.get("avg_latency", 0.0)),
                p95_latency=float(metrics_data.get("p95_latency", 0.0)),
                p99_latency=float(metrics_data.get("p99_latency", 0.0)),
                success_rate=float(metrics_data.get("success_rate", 0.0)),
                total_requests=int(metrics_data.get("total_requests", 0)),
                failed_requests=int(metrics_data.get("failed_requests", 0)),
                cpu_usage=float(metrics_data.get("cpu_usage", 0.0)),
                memory_usage=float(metrics_data.get("memory_usage", 0.0)),
                cpu_utilization=float(metrics_data.get("cpu_utilization", 0.0)),
                memory_utilization=float(metrics_data.get("memory_utilization", 0.0)),
                cpu_throttling=float(metrics_data.get("cpu_throttling", 0.0)),
                memory_peak_usage=float(metrics_data.get("memory_peak_usage", 0.0)),
                request_rate=float(metrics_data.get("request_rate", 0.0)),
                error_rate=float(metrics_data.get("error_rate", 0.0)),
                evaluated_at=evaluated_at,
            )

        # Status: usa o campo serializado se presente (post-Tier 2), senão
        # deriva de `error` para retrocompat com cache.jsonl pré-Tier 2.
        status_raw = data.get("status")
        if status_raw:
            try:
                status = EvaluationStatus(status_raw)
            except ValueError:
                status = EvaluationStatus.from_error(data.get("error"))
        else:
            status = EvaluationStatus.from_error(data.get("error"))

        return EvaluationResult(
            individual=individual,
            fitness=float(data["fitness"]),
            metrics=metrics,
            evaluation_time=float(data.get("evaluation_time", 0.0)),
            error=data.get("error"),
            generation=data.get("generation"),
            status=status,
        )

    def clear(self) -> None:
        """Limpa o cache."""
        self.cache.clear()
        log("Cache cleared")

    def size(self) -> int:
        """Retorna tamanho do cache."""
        return len(self.cache)

    def cleanup_expired(self) -> int:
        """
        Remove entradas expiradas.

        Returns:
            Número de entradas removidas
        """
        now = time.time()
        expired_keys = [
            key
            for key, (timestamp, _) in self.cache.items()
            if now - timestamp >= self.ttl
        ]

        for key in expired_keys:
            del self.cache[key]

        if expired_keys:
            log(f"Cleaned up {len(expired_keys)} expired cache entries")

        return len(expired_keys)
