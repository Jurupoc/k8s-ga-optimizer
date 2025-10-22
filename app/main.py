# app/main.py
from fastapi import FastAPI
from app.compute import sort, search, prime
from app.metrics import setup_metrics

app = FastAPI(title="Compute Service")

@app.get("/sort")
def sort_numbers(size: int = 10000):
    data = sort.generate_random_list(size)
    sorted_data = sort.quicksort(data)
    return {"sorted_first": sorted_data[0], "sorted_last": sorted_data[-1]}

@app.get("/search")
def search_number(size: int = 1000000, target: int = 42):
    data = search.generate_random_list(size)
    found = search.binary_search(sorted(data), target)
    return {"found": found}

@app.get("/prime")
def generate_primes(size: int = 10000):
    primes = prime.generate_primes(size)
    return {"count": len(primes)}

@app.get("/status")
def get_status():
    import socket, psutil
    return {
        "node": socket.gethostname(),
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent
    }

setup_metrics(app)
