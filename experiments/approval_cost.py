"""
What human approval of agent actions costs, with and without Interlock. Every assumption is a flag.

    python3 experiments/approval_cost.py
    python3 experiments/approval_cost.py --minutes-per-review 2 --actions-per-day 500

Review share with Interlock defaults to 36 of 100, from results/approval_inbox.md (rules plus Interlock,
a synthetic day whose mix is itself an assumption). Labor only: recovered duplicate spend is not counted.
Standard library only.
"""
import argparse


def costs(actions_per_day, minutes_per_review, loaded_hourly, workdays, review_share, take_rate):
    per_review = minutes_per_review / 60 * loaded_hourly
    all_human = actions_per_day * workdays * per_review
    with_interlock = all_human * review_share
    savings = all_human - with_interlock
    return {"per_review": per_review, "all_human": all_human, "with_interlock": with_interlock,
            "savings": savings, "acv": savings * take_rate}


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--actions-per-day", type=float, default=2000, help="agent actions a day that need approval today")
    p.add_argument("--minutes-per-review", type=float, default=5, help="minutes a person spends per approval")
    p.add_argument("--loaded-hourly", type=float, default=50, help="loaded cost of that person per hour, USD")
    p.add_argument("--workdays", type=float, default=250, help="working days a year")
    p.add_argument("--review-share", type=float, default=0.36, help="share still reviewed by a person with rules plus Interlock")
    p.add_argument("--take-rate", type=float, default=0.20, help="share of savings charged as yearly contract value")
    c = costs(**{k: v for k, v in vars(p.parse_args()).items()})
    for label, key in [("one approval", "per_review"), ("a year, every action approved", "all_human"),
                       ("a year, rules plus Interlock", "with_interlock"), ("saved a year", "savings"),
                       ("contract value a year", "acv")]:
        print(f"{label:32} ${c[key]:>12,.2f}")


def _check():
    c = costs(2000, 5, 50, 250, 0.36, 0.20)
    assert round(c["per_review"], 2) == 4.17
    assert round(c["all_human"]) == 2_083_333
    assert round(c["with_interlock"]) == 750_000
    assert round(c["savings"]) == 1_333_333
    assert round(c["acv"]) == 266_667


if __name__ == "__main__":
    _check()
    main()
