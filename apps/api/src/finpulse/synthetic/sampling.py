"""Seeded randomness.

Each component of a simulation draws from its own named stream, derived from the scenario seed.
Adding a customer or an expense therefore does not shift the random numbers any other component
sees, which keeps scenario edits local and diffs readable.

``random.Random`` seeded with a string is stable across platforms and Python versions (it hashes
the string with SHA-512), unlike the built-in ``hash()``.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")


class Sampler:
    def __init__(self, seed: int, stream: str) -> None:
        self._rng = random.Random(f"finpulse:{seed}:{stream}")  # noqa: S311 - simulation, not crypto

    def uniform(self, low: float, high: float) -> float:
        return self._rng.uniform(low, high)

    def chance(self, probability: float) -> bool:
        return self._rng.random() < probability

    def normal(self, mean: float, sd: float) -> float:
        return self._rng.gauss(mean, sd) if sd > 0 else mean

    def lognormal_mean(self, mean: float, cv: float) -> float:
        """Positive value with the given mean and coefficient of variation."""
        if mean <= 0:
            return 0.0
        if cv <= 0:
            return mean
        sigma2 = math.log(1 + cv * cv)
        return self._rng.lognormvariate(math.log(mean) - sigma2 / 2, math.sqrt(sigma2))

    def poisson(self, lam: float) -> int:
        if lam <= 0:
            return 0
        if lam > 30:  # normal approximation; Knuth's method underflows for large lambda
            return max(0, round(self._rng.gauss(lam, math.sqrt(lam))))
        threshold, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= self._rng.random()
            if p <= threshold:
                return k
            k += 1

    def integer(self, low: int, high: int) -> int:
        return self._rng.randint(low, high)

    def choice(self, options: Sequence[T]) -> T:
        return self._rng.choice(options)

    def digits(self, n: int) -> str:
        return "".join(str(self._rng.randint(0, 9)) for _ in range(n))
