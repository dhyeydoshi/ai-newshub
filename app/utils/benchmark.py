import time
import asyncio
import statistics
from typing import List, Callable, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class PerformanceBenchmark:

    def __init__(self, name: str):
        self.name = name
        self.measurements: List[float] = []
        self.start_time: float = 0

    def measure(self):
        """Context manager for measuring execution time"""
        class MeasureContext:
            def __init__(self, benchmark):
                self.benchmark = benchmark
                self.start = 0

            def __enter__(self):
                self.start = time.perf_counter()
                return self

            def __exit__(self, *args):
                duration = time.perf_counter() - self.start
                self.benchmark.measurements.append(duration)

        return MeasureContext(self)

    async def measure_async(self, func: Callable, *args, **kwargs) -> Any:
        """Measure async function performance"""
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        duration = time.perf_counter() - start
        self.measurements.append(duration)
        return result

    def get_stats(self) -> Dict[str, float]:
        """Calculate performance statistics"""
        if not self.measurements:
            return {}

        return {
            'count': len(self.measurements),
            'min': min(self.measurements),
            'max': max(self.measurements),
            'mean': statistics.mean(self.measurements),
            'median': statistics.median(self.measurements),
            'stdev': statistics.stdev(self.measurements) if len(self.measurements) > 1 else 0,
            'total': sum(self.measurements),
            'p95': statistics.quantiles(self.measurements, n=20)[18] if len(self.measurements) > 20 else max(self.measurements),
            'p99': statistics.quantiles(self.measurements, n=100)[98] if len(self.measurements) > 100 else max(self.measurements)
        }

    def print_report(self):
        """Print formatted performance report"""
        stats = self.get_stats()

        if not stats:
            logger.warning(f"No measurements for '{self.name}'")
            return

        print(f"\n{'='*60}")
        print(f"Performance Report: {self.name}")
        print(f"{'='*60}")
        print(f"Total Runs:      {stats['count']}")
        print(f"Total Time:      {stats['total']:.3f}s")
        print(f"Mean Time:       {stats['mean']:.3f}s")
        print(f"Median Time:     {stats['median']:.3f}s")
        print(f"Min Time:        {stats['min']:.3f}s")
        print(f"Max Time:        {stats['max']:.3f}s")
        print(f"Std Deviation:   {stats['stdev']:.3f}s")
        print(f"95th Percentile: {stats['p95']:.3f}s")
        print(f"99th Percentile: {stats['p99']:.3f}s")
        print(f"{'='*60}\n")

        # Performance rating
        if stats['mean'] < 0.1:
            rating = " Excellent"
        elif stats['mean'] < 0.5:
            rating = " Good"
        elif stats['mean'] < 1.0:
            rating = " Acceptable"
        else:
            rating = " Needs Optimization"

        print(f"Rating: {rating}")
        print(f"Throughput: {stats['count'] / stats['total']:.2f} operations/second\n")


class APIBenchmark:

    def __init__(self):
        self.results: Dict[str, PerformanceBenchmark] = {}

    async def run_benchmark(
        self,
        name: str,
        func: Callable,
        concurrency: int = 1,
        iterations: int = 100
    ):
        benchmark = PerformanceBenchmark(name)
        self.results[name] = benchmark

        print(f"\n Running benchmark: {name}")
        print(f"   Concurrency: {concurrency}, Iterations: {iterations}")

        # Run iterations in batches
        batch_size = concurrency
        num_batches = (iterations + batch_size - 1) // batch_size

        for batch in range(num_batches):
            tasks = []
            for _ in range(min(batch_size, iterations - batch * batch_size)):
                tasks.append(benchmark.measure_async(func))

            await asyncio.gather(*tasks)

            # Progress indicator
            completed = min((batch + 1) * batch_size, iterations)
            print(f"   Progress: {completed}/{iterations} ({completed/iterations*100:.1f}%)")

        benchmark.print_report()

    def compare_benchmarks(self, name1: str, name2: str):
        """Compare two benchmarks"""
        if name1 not in self.results or name2 not in self.results:
            logger.error("Benchmarks not found")
            return

        stats1 = self.results[name1].get_stats()
        stats2 = self.results[name2].get_stats()

        improvement = ((stats1['mean'] - stats2['mean']) / stats1['mean']) * 100

        print(f"\n{'='*60}")
        print(f"Comparison: {name1} vs {name2}")
        print(f"{'='*60}")
        print(f"{name1} mean: {stats1['mean']:.3f}s")
        print(f"{name2} mean: {stats2['mean']:.3f}s")

        if improvement > 0:
            print(f" {name2} is {improvement:.1f}% faster")
        else:
            print(f" {name2} is {abs(improvement):.1f}% slower")

        print(f"{'='*60}\n")


async def benchmark_database_operations():
    from app.core.database import AsyncSessionLocal
    from app.models.article import Article
    from sqlalchemy import select

    print("\n Starting Database Operations Benchmark")

    # Benchmark 1: Query 100 articles
    async def query_articles():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Article)
                .where(Article.is_active == True)
                .limit(100)
            )
            return result.scalars().all()

    benchmark = PerformanceBenchmark("Query 100 Articles")
    for _ in range(50):
        await benchmark.measure_async(query_articles)

    benchmark.print_report()


async def benchmark_cache_operations():
    """Benchmark cache read/write performance"""
    from app.core.cache import get_cache_manager

    cache = get_cache_manager()
    if not cache:
        logger.error("Cache manager not initialized")
        return

    print("\n Starting Cache Operations Benchmark")

    # Test data
    test_data = {
        f"key_{i}": {"data": f"value_{i}" * 100}
        for i in range(100)
    }

    # Benchmark: Individual sets
    benchmark1 = PerformanceBenchmark("Cache: Individual Set (100 items)")
    with benchmark1.measure():
        for key, value in test_data.items():
            await cache.set(key, value)
    benchmark1.print_report()

    # Benchmark: Batch set
    benchmark2 = PerformanceBenchmark("Cache: Batch Set (100 items)")
    with benchmark2.measure():
        await cache.set_many(test_data)
    benchmark2.print_report()

    # Calculate improvement
    stats1 = benchmark1.get_stats()
    stats2 = benchmark2.get_stats()
    improvement = ((stats1['mean'] - stats2['mean']) / stats1['mean']) * 100

    print(f" Batch operations are {improvement:.1f}% faster!\n")


if __name__ == "__main__":
    asyncio.run(benchmark_database_operations())
    asyncio.run(benchmark_cache_operations())


