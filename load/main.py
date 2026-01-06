import os
from load_test import LoadTester
from shared.utils import log


def main() -> None:
    # Lê variáveis de ambiente do manifest
    base_url = os.environ.get("TARGET_URL", "http://app-ga.default.svc.cluster.local:8080")
    duration = os.environ.get("DURATION")
    concurrency = os.environ.get("CONCURRENCY")

    # Mapeia variáveis de ambiente para LoadTestConfig se necessário
    if duration:
        os.environ["LOAD_TEST_DURATION"] = duration
    if concurrency:
        os.environ["LOAD_TEST_CONCURRENCY"] = concurrency

    # Cria LoadTester (já lê as variáveis de ambiente via LoadTestConfig.from_env())
    load_tester = LoadTester()
    target_url = f"{base_url}/cpu-stress"

    # Executa o load test com a URL do ambiente
    load_tester.run(
        url=target_url,
        duration=int(duration) if duration else None,
        concurrency=int(concurrency) if concurrency else None
    )


if __name__ == "__main__":
    main()
