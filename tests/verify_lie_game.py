"""Exact minimax certificate for nine cards, <=2 lies, query size <=3."""

from functools import lru_cache
from math import comb


def weight(state, remaining):
    a, b, c = state
    return a * (1 + remaining + comb(remaining, 2)) + b * (1 + remaining) + c


def branches(state, query):
    a, b, c = state
    i, j, k = query
    return (i, a - i + j, b - j + k), (a - i, i + b - j, j + c - k)


@lru_cache(None)
def strategy(state, remaining):
    """Return winning group counts, () at a leaf, or None if impossible."""
    if sum(state) <= 1:
        return ()
    if remaining <= 0 or weight(state, remaining) > 2**remaining:
        return None
    a, b, c = state
    for i in range(min(a, 3) + 1):
        for j in range(min(b, 3 - i) + 1):
            for k in range(min(c, 3 - i - j) + 1):
                query = i, j, k
                if all(strategy(child, remaining - 1) is not None for child in branches(state, query)):
                    return query
    return None


def verify_concrete_strategy():
    """Execute against every secret and every <=2-error schedule independently."""
    from itertools import combinations

    paths = 0
    maximum = 0
    for secret in range(1, 10):
        for count in range(3):
            for lie_positions in combinations(range(10), count):
                mismatches = {card: 0 for card in range(1, 10)}
                used = 0
                while len(mismatches) > 1:
                    groups = [[card for card, n in mismatches.items() if n == j] for j in range(3)]
                    pick = strategy(tuple(map(len, groups)), 10 - used)
                    assert pick is not None and len(pick) == 3
                    question = {card for group, n in zip(groups, pick) for card in group[:n]}
                    assert len(question) <= 3
                    reply = (secret in question) ^ (used in lie_positions)
                    mismatches = {
                        card: n + ((card in question) != reply)
                        for card, n in mismatches.items()
                        if n + ((card in question) != reply) <= 2
                    }
                    used += 1
                    assert used <= 10 and secret in mismatches
                assert list(mismatches) == [secret]
                maximum = max(maximum, used)
                paths += 1
    assert maximum == 10
    return paths, maximum


def verify():
    assert strategy((9, 0, 0), 9) is None
    assert strategy((9, 0, 0), 10) is not None
    # Short independent lower bound: a first question of size <=2 already
    # exceeds the 8-question capacity in its "no" branch. Size 3 leaves
    # (6,3,0); any next question has 3*i+j<=9, but capacity requires >=10.
    assert all(weight((9 - i, i, 0), 8) > 256 for i in range(3))
    for i in range(4):
        for j in range(min(3, 3 - i) + 1):
            assert weight(branches((6, 3, 0), (i, j, 0))[1], 7) > 128
    return verify_concrete_strategy()


if __name__ == "__main__":
    paths, maximum = verify()
    print(f"minimum=10; checked {paths} secret/error schedules; maximum={maximum}")
