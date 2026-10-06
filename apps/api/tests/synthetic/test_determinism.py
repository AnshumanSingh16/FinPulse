from dataclasses import replace

import pytest

from finpulse.synthetic import SCENARIOS, generate
from finpulse.synthetic.export import fingerprint
from finpulse.synthetic.ids import IdFactory


@pytest.mark.parametrize("code", sorted(SCENARIOS))
def test_same_spec_and_seed_reproduce_identical_data(code: str) -> None:
    first, second = generate(SCENARIOS[code]), generate(SCENARIOS[code])

    assert first == second
    assert fingerprint(first) == fingerprint(second)


def test_a_different_seed_produces_different_data() -> None:
    spec = SCENARIOS["sharma_electricals"]

    other = generate(replace(spec, seed=spec.seed + 1))

    assert fingerprint(other) != fingerprint(generate(spec))


def test_ids_are_stable_and_namespaced() -> None:
    a, b = IdFactory("x", 1), IdFactory("x", 2)

    assert a("invoice", "INV/1") == IdFactory("x", 1)("invoice", "INV/1")
    assert a("invoice", "INV/1") != b("invoice", "INV/1")
    assert a("invoice", "INV/1") != a("bill", "INV/1")


def test_fingerprint_is_pinned_for_the_primary_demo() -> None:
    """Changing the generator or the Sharma scenario changes the demo data everyone sees. If that
    is intended, bump GENERATOR_VERSION when the engine changed and update this value."""
    ds = generate(SCENARIOS["sharma_electricals"])

    assert fingerprint(ds) == PINNED_SHARMA_FINGERPRINT


PINNED_SHARMA_FINGERPRINT = "d75cc4b4b8ba6484268d126f4448439807b4b323cbccfd3df4ba197ad99725ec"
