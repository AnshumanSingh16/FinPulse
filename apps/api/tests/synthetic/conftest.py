import pytest

from finpulse.synthetic import SCENARIOS, Dataset, generate

_cache: dict[str, Dataset] = {}


def dataset_for(code: str) -> Dataset:
    if code not in _cache:
        _cache[code] = generate(SCENARIOS[code])
    return _cache[code]


@pytest.fixture(params=sorted(SCENARIOS))
def ds(request: pytest.FixtureRequest) -> Dataset:
    """Each registered scenario, generated once per test session."""
    return dataset_for(request.param)
