"""Exact, offline verifier for the hidden-coin stopping-time challenge.

Run with ``python tests/verify_probability.py``.  Uses only the standard library.
The exact linear system is cross-checked against a separate finite-horizon
enumeration that stores the last two literal outcomes, not automaton prefixes.
"""

from fractions import Fraction as F


PREFIXES = ("", "H", "HT", "T", "TH")
STATES = tuple((prefix, coin) for prefix in PREFIXES for coin in (0, 1))
INDEX = {state: i for i, state in enumerate(STATES)}
WIN = "HTH"
LOSE = "THH"


def solve(matrix, rhs):
    """Gauss-Jordan elimination over exact rational numbers."""
    n = len(rhs)
    rows = [list(row) + [value] for row, value in zip(matrix, rhs)]
    for col in range(n):
        pivot = next(row for row in range(col, n) if rows[row][col])
        rows[col], rows[pivot] = rows[pivot], rows[col]
        scale = rows[col][col]
        rows[col] = [value / scale for value in rows[col]]
        for row in range(n):
            if row != col:
                scale = rows[row][col]
                rows[row] = [x - scale * y for x, y in zip(rows[row], rows[col])]
    result = [row[-1] for row in rows]
    assert all(sum(a * x for a, x in zip(row, result)) == b for row, b in zip(matrix, rhs))
    return result


def exact_solution():
    n = len(STATES)
    transient = [[F(0) for _ in STATES] for _ in STATES]
    winning = [F(0) for _ in STATES]
    losing = [F(0) for _ in STATES]
    for i, (prefix, coin) in enumerate(STATES):
        heads = F(2, 3) if coin == 0 else F(1, 3)
        for outcome, emission in (("H", heads), ("T", 1 - heads)):
            record = prefix + outcome
            if record.endswith(WIN):
                winning[i] += emission
            elif record.endswith(LOSE):
                losing[i] += emission
            else:
                suffix = max((p for p in PREFIXES if record.endswith(p)), key=len)
                for following_coin, switch in ((coin, F(3, 4)), (1 - coin, F(1, 4))):
                    transient[i][INDEX[(suffix, following_coin)]] += emission * switch
        assert sum(transient[i]) + winning[i] + losing[i] == 1

    matrix = [[F(i == j) - transient[i][j] for j in range(n)] for i in range(n)]
    probability = solve(matrix, winning)
    failure_probability = solve(matrix, losing)
    # g_s = E_s[N 1_W] = P_s(W) + sum_j Q_sj g_j.
    weighted_time = solve(matrix, probability)
    failure_weighted_time = solve(matrix, failure_probability)
    expected_time = solve(matrix, [F(1)] * n)
    assert all(p + q == 1 for p, q in zip(probability, failure_probability))
    assert all(g + h == t for g, h, t in zip(weighted_time, failure_weighted_time, expected_time))

    a, b = INDEX[("", 0)], INDEX[("", 1)]
    answers = {
        "P(W)": (probability[a] + probability[b]) / 2,
        "P(initial A | W)": probability[a] / (probability[a] + probability[b]),
        "E[N | W]": (weighted_time[a] + weighted_time[b]) / (probability[a] + probability[b]),
        "E[N]": (expected_time[a] + expected_time[b]) / 2,
    }
    return probability, weighted_time, expected_time, answers


def check_by_literal_history(probability, weighted_time, expected_time, horizon=240):
    """Independently sum stopped path mass; rigorous tail bounds enclose answers."""
    # Key is (up-to-two literal previous outcomes, next coin, initial coin).
    active = {("", 0, 0): F(1, 2), ("", 1, 1): F(1, 2)}
    win_mass = [F(0), F(0)]
    win_time = [F(0), F(0)]
    loss_mass = F(0)
    for step in range(1, horizon + 1):
        following = {}
        for (history, coin, initial), mass in active.items():
            for outcome in "HT":
                emission = F(2 if (outcome == "H") == (coin == 0) else 1, 3)
                branch = mass * emission
                history3 = history + outcome
                if history3 == "HTH":
                    win_mass[initial] += branch
                    win_time[initial] += step * branch
                elif history3 == "THH":
                    loss_mass += branch
                else:
                    for next_coin in (0, 1):
                        key = (history3[-2:], next_coin, initial)
                        following[key] = following.get(key, F(0)) + branch * F(3 if next_coin == coin else 1, 4)
        active = following

    tail_mass = sum(active.values())
    assert sum(win_mass) + loss_mass + tail_mass == 1
    # All states have a probability >= 1/27 of hitting HTH within the next
    # three steps, hence E[remaining time] <= 3 / (1/27) = 81.
    assert max(expected_time) <= 81
    for initial in (0, 1):
        i = INDEX[("", initial)]
        tail = sum(m for (_, _, origin), m in active.items() if origin == initial)
        assert win_mass[initial] <= probability[i] / 2 <= win_mass[initial] + tail
        assert win_time[initial] <= weighted_time[i] / 2 <= win_time[initial] + (horizon + 81) * tail
    assert tail_mass < F(1, 10**12)
    return float(tail_mass)


def main():
    probability, weighted_time, expected_time, answers = exact_solution()
    assert answers == {
        "P(W)": F(154365, 320138),
        "P(initial A | W)": F(259297, 463095),
        "E[N | W]": F(20815361171, 3529864455),
        "E[N]": F(1006983, 160069),
    }
    tail = check_by_literal_history(probability, weighted_time, expected_time)
    for (prefix, coin), p, g in zip(STATES, probability, weighted_time):
        print(f"state={prefix or 'empty'}{chr(65 + coin)}: p={p}, g={g}")
    for label, value in answers.items():
        print(f"{label} = {value} = {float(value):.12f}")
    print(f"PASS: rational equations and independent 240-step path enumeration; tail={tail:.3g}")


if __name__ == "__main__":
    main()
