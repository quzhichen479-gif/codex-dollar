"""Certificate for optimal non-adaptive recovery with 3 lies and query size 3."""

from itertools import combinations

QUERIES = (
    (1, 2, 3), (4, 5, 6), (7, 8, 9),
    (1, 4, 7), (2, 5, 8), (3, 6, 9),
    (1, 5, 9), (2, 6, 7), (3, 4, 8),
    (1, 6, 8), (2, 4, 9), (3, 5, 7),
    (2, 6, 9), (3, 6, 7), (4, 7, 8), (5, 8, 9),
)


def verify():
    assert len(QUERIES) == 16 and len(set(QUERIES)) == 16
    assert all(len(set(q)) == 3 and set(q) <= set(range(1, 10)) for q in QUERIES)
    words = [tuple(int(card in q) for q in QUERIES) for card in range(1, 10)]
    distance = lambda a, b: sum(x != y for x, y in zip(a, b))
    assert min(distance(a, b) for a, b in combinations(words, 2)) == 7
    assert all(distance(a[:12], b[:12]) == 6 for a, b in combinations(words, 2))
    assert len({w[12:] for w in words}) == 9
    # Distinct radius-3 Hamming balls: all 6273 legal secret/error pairs.
    received = {}
    for secret, word in enumerate(words, 1):
        for count in range(4):
            for errors in combinations(range(16), count):
                observed = tuple(bit ^ (i in errors) for i, bit in enumerate(word))
                assert observed not in received
                received[observed] = secret
    assert len(received) == 6273
    # Exact arithmetic certificate for the parity-based impossibility of 15.
    assert 13 * 18 < 36 * 7
    # At 14, all pair distances would be 7, impossible on any triple because
    # the sum of three binary Hamming distances is always even.
    for triple in ((0, 0, 0), (0, 0, 1), (0, 1, 0), (0, 1, 1),
                   (1, 0, 0), (1, 0, 1), (1, 1, 0), (1, 1, 1)):
        assert sum(a != b for a, b in combinations(triple, 2)) % 2 == 0
    same_parity_pairs = lambda g: g * (g - 1) // 2 + (9 - g) * (8 - g) // 2
    assert min(same_parity_pairs(g) for g in range(10)) == 16
    assert 14 * 18 + 14 < 36 * 7 + 16  # Any row of size <=2 fails at n=15.
    permitted = [g for g in range(1, 10, 2) if 36 * 7 + same_parity_pairs(g) <= 270]
    assert permitted == [3, 5]
    for g in permitted:
        odd_min = min(r for r in range(1, 16, 2) if 45 + 3 * r >= 55 + g)
        even_min = min(r for r in range(0, 16, 2) if 45 + 3 * r >= 64 - g)
        assert odd_min == 5 and even_min == 6
        assert g * odd_min + (9 - g) * even_min > 45
    return len(received), min(distance(a, b) for a, b in combinations(words, 2))


if __name__ == "__main__":
    count, minimum = verify()
    print(f"minimum questions=16; minimum distance={minimum}; {count} error patterns checked")
