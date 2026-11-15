"""Generate the synthetic IT ticket dataset (all data is synthetic and labelled as such).

Usage (from backend/):  python scripts/generate_data.py --seed 42

Writes to backend/data/:
  historical_tickets.csv   resolved tickets -> retrieval corpus + classifier training
  kb_articles.json         one runbook per scenario (approved) + a few draft/superseded ones
  test/holdout_tickets.csv unseen generator tickets, input fields only (later paraphrased by an LLM)
  test/novel_tickets.csv   tickets with no matching history (expected ESCALATE / CLARIFY)
  test/labels.csv          ground truth for every test ticket (evaluation only)
  test/handwritten_tickets.csv  template for tickets written by hand (filled in by the team)
  DATA_CARD.md             what was generated and how

Honesty rules:
  - scenario_id is stored for evaluation only; the app must never read it.
  - holdout tickets use a separate random stream and later dates, and any text that
    duplicates a historical ticket is regenerated (no train/test leakage).
"""
import argparse
import csv
import json
import random
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from scenarios import NOVEL_SCENARIOS, SCENARIOS

N_HISTORICAL = 1200
N_HOLDOUT = 120

HIST_START, HIST_END = datetime(2025, 1, 1), datetime(2026, 6, 30)
TEST_START, TEST_END = datetime(2026, 7, 1), datetime(2026, 10, 31)

FIRST = ["Rahul", "Priya", "Anil", "Sneha", "Vikram", "Divya", "Arjun", "Kavya", "Rohit", "Meera",
         "Sanjay", "Pooja", "Karthik", "Ananya", "John", "Emma", "Imran", "Fatima", "Wei", "Maria"]
LAST = ["Kumar", "Sharma", "Reddy", "Iyer", "Patel", "Nair", "Rao", "Gupta", "Singh", "Menon",
        "Smith", "Khan", "Chen", "Garcia", "Das", "Joshi"]
DOMAIN = "acmecorp.example"

GREETINGS = ["Hi team,", "Hello,", "Hi,", "Dear IT,", "Hi support,", ""]
DURATION = ["This started this morning.", "Started yesterday.", "It's been like this for 2 days.",
            "Since Monday.", "Started after lunch today.", ""]
TRIED = ["I already restarted my laptop.", "I tried logging out and in again.",
         "Rebooting didn't help.", "", ""]
CLOSINGS = ["Please help.", "Thanks.", "Kindly assist.", "Can someone look into this?", "Thanks in advance.", ""]
IMPACT = {
    "P1": ["This is critical, many users are affected.", "Business is stopped, please treat as urgent."],
    "P2": ["I am completely blocked.", "My whole team is affected.", "This is blocking a client deliverable."],
    "P3": ["I can work around it for now.", "Only my machine seems affected.", "It slows me down."],
    "P4": ["Not urgent.", "Whenever someone gets a chance.", "Low priority."],
}
PRIORITIES = ["P1", "P2", "P3", "P4"]
ENVIRONMENTS = ["prod"] * 9 + ["uat"]


def bump(priority: str) -> str:
    """Raise priority one level (P3 -> P2). P1 stays P1."""
    return PRIORITIES[max(0, PRIORITIES.index(priority) - 1)]


def random_date(rng: random.Random, start: datetime, end: datetime) -> datetime:
    seconds = int((end - start).total_seconds())
    return start + timedelta(seconds=rng.randint(0, seconds))


def add_pii(rng: random.Random, text: str) -> str:
    """Sometimes add personal data so the redaction step has real work to do."""
    roll = rng.random()
    name = f"{rng.choice(FIRST).lower()}.{rng.choice(LAST).lower()}"
    if roll < 0.12:
        return text + f" You can reach me at {name}@{DOMAIN}."
    if roll < 0.20:
        return text + f" My number is +91 9{rng.randint(100000000, 999999999)}."
    if roll < 0.26:
        return text + f" My laptop IP is 10.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}."
    return text


def make_ticket(rng: random.Random, sc: dict, start: datetime, end: datetime) -> dict:
    priority = sc["priority"]
    if rng.random() < 0.15:  # some users report a wider impact -> higher priority
        priority = bump(priority)

    symptom = rng.choice(sc["symptoms"])
    details = rng.sample(sc["details"], k=rng.randint(0, 2))
    parts = [rng.choice(GREETINGS), symptom[0].upper() + symptom[1:] + ".", *details,
             rng.choice(DURATION), rng.choice(TRIED), rng.choice(IMPACT[priority]), rng.choice(CLOSINGS)]
    description = " ".join(p for p in parts if p)
    if rng.random() < 0.2:  # informal, lower-case writing
        description = description.lower()
    description = add_pii(rng, description)

    title = symptom if len(symptom) <= 60 else symptom[:57].rsplit(" ", 1)[0] + "..."
    created = random_date(rng, start, end)
    return dict(
        title=title[0].upper() + title[1:],
        description=description,
        category=sc["category"],
        subcategory=sc["subcategory"],
        priority=priority,
        application=sc["application"],
        environment=rng.choice(ENVIRONMENTS),
        assignment_group=sc["group"],
        created_at=created.isoformat(timespec="minutes"),
        scenario_id=sc["id"],
    )


def resolution_notes(rng: random.Random, sc: dict) -> str:
    steps = list(sc["resolution"])
    if len(steps) > 2 and rng.random() < 0.3:  # engineers sometimes skip a step in notes
        steps.pop(rng.randrange(len(steps)))
    return " ".join(steps)


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def generate(seed: int, out: Path) -> dict:
    hist_rng = random.Random(seed)
    test_rng = random.Random(seed + 1000)  # separate stream: holdout is not a slice of history

    # ---- historical (resolved) tickets ----
    historical, seen_text = [], set()
    for i in range(N_HISTORICAL):
        sc = SCENARIOS[i % len(SCENARIOS)]  # balanced across scenarios
        t = make_ticket(hist_rng, sc, HIST_START, HIST_END)
        created = datetime.fromisoformat(t["created_at"])
        resolved = created + timedelta(hours=hist_rng.randint(1, 72))
        historical.append(dict(
            ticket_id="", **t, status="Resolved",
            resolved_at=resolved.isoformat(timespec="minutes"),
            resolution_notes=resolution_notes(hist_rng, sc),
        ))
        seen_text.add(t["description"].lower())
    historical.sort(key=lambda r: r["created_at"])
    for n, row in enumerate(historical, start=1):
        row["ticket_id"] = f"INC{n:06d}"

    # ---- knowledge base: one approved runbook per scenario + 2 non-approved ----
    kb = []
    for n, sc in enumerate(SCENARIOS, start=1):
        kb.append(dict(kb_id=f"KB{n:04d}", title=f"{sc['subcategory']}: {sc['symptoms'][0]}",
                       category=sc["category"], subcategory=sc["subcategory"],
                       application=sc["application"], status="approved",
                       steps=sc["resolution"], scenario_id=sc["id"]))
    kb.append(dict(kb_id="KB9001", title="VPN: old client workaround (superseded)", category="Network",
                   subcategory="VPN", application="GlobalProtect VPN", status="superseded",
                   steps=["Uninstall GlobalProtect 5.x and install the legacy AnyConnect client."], scenario_id="net_vpn_cert"))
    kb.append(dict(kb_id="KB9002", title="Outlook: delete OST file (draft, unreviewed)", category="Email & Collaboration",
                   subcategory="Outlook sync", application="Outlook", status="draft",
                   steps=["Delete all files in the Outlook folder including PST archives."], scenario_id="eml_outlook_profile"))

    # ---- holdout test tickets (unseen, later dates, no duplicate text) ----
    holdout, labels = [], []
    lookalike_of = {sc["id"]: sc.get("lookalike", "") for sc in SCENARIOS}
    for i in range(N_HOLDOUT):
        sc = SCENARIOS[i % len(SCENARIOS)]
        for _ in range(20):
            t = make_ticket(test_rng, sc, TEST_START, TEST_END)
            if t["description"].lower() not in seen_text:
                break
        seen_text.add(t["description"].lower())
        test_id = f"TST{i + 1:04d}"
        holdout.append(dict(test_id=test_id, title=t["title"], description=t["description"],
                            application=t["application"], environment=t["environment"], created_at=t["created_at"]))
        labels.append(dict(test_id=test_id, source="generator_holdout", category=t["category"],
                           subcategory=t["subcategory"], priority=t["priority"], scenario_id=sc["id"],
                           hard_negative_scenario=lookalike_of[sc["id"]], expected_outcome="RECOMMEND"))

    # ---- novel / out-of-scope test tickets ----
    novel, n = [], 0
    for sc in NOVEL_SCENARIOS:
        for text in sc["texts"]:
            n += 1
            test_id = f"NOV{n:04d}"
            created = random_date(test_rng, TEST_START, TEST_END)
            novel.append(dict(test_id=test_id, title=text[:60], description=text, application="",
                              environment="prod", created_at=created.isoformat(timespec="minutes")))
            labels.append(dict(test_id=test_id, source="novel", category="", subcategory="", priority="",
                               scenario_id=sc["id"], hard_negative_scenario="",
                               expected_outcome=sc["expected_outcome"]))

    # ---- write everything ----
    write_csv(out / "historical_tickets.csv", historical)
    (out / "kb_articles.json").write_text(json.dumps(kb, indent=2), encoding="utf-8")
    write_csv(out / "test" / "holdout_tickets.csv", holdout)
    write_csv(out / "test" / "novel_tickets.csv", novel)
    write_csv(out / "test" / "labels.csv", labels)
    handwritten = out / "test" / "handwritten_tickets.csv"
    if not handwritten.exists():  # never overwrite tickets the team has written
        handwritten.write_text("test_id,title,description,application,environment,category,subcategory,"
                               "priority,scenario_id,expected_outcome\n", encoding="utf-8")

    stats = dict(
        seed=seed, scenarios=len(SCENARIOS), historical=len(historical), kb_articles=len(kb),
        holdout=len(holdout), novel=len(novel),
        category_counts=dict(sorted(Counter(r["category"] for r in historical).items())),
        priority_counts=dict(sorted(Counter(r["priority"] for r in historical).items())),
        tickets_with_pii=sum(1 for r in historical if f"@{DOMAIN}" in r["description"] or "+91" in r["description"] or " IP is " in r["description"]),
    )
    write_data_card(out / "DATA_CARD.md", stats)
    return stats


def write_data_card(path: Path, s: dict) -> None:
    cats = "\n".join(f"| {k} | {v} |" for k, v in s["category_counts"].items())
    pris = "\n".join(f"| {k} | {v} |" for k, v in s["priority_counts"].items())
    path.write_text(f"""# Data card

All data is **synthetic**, produced by `scripts/generate_data.py --seed {s['seed']}` from {s['scenarios']} scenarios
in `scripts/scenarios.py`. Each scenario is one root cause with typical symptoms and a fix.

| File | Rows | Use |
|---|---|---|
| historical_tickets.csv | {s['historical']} | Retrieval corpus, classifier training |
| kb_articles.json | {s['kb_articles']} | Approved runbooks (+2 draft/superseded that must never be cited) |
| test/holdout_tickets.csv | {s['holdout']} | Unseen generator tickets, separate random stream, later dates |
| test/novel_tickets.csv | {s['novel']} | No matching history: expected ESCALATE or CLARIFY |
| test/handwritten_tickets.csv | team-written | Independent tickets written by hand |

Historical tickets by category:

| Category | Count |
|---|---|
{cats}

Historical tickets by priority:

| Priority | Count |
|---|---|
{pris}

{s['tickets_with_pii']} historical tickets contain synthetic personal data (email, phone, IP) to exercise redaction.

**Limits (stated honestly):** the holdout set comes from the same scenarios as the training data, so its
scores are optimistic. Hand-written, LLM-paraphrased and novel tickets are reported separately in the
evaluation report because they are the real test. `scenario_id` is for evaluation only.
""", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent / "data")
    args = parser.parse_args()
    print(json.dumps(generate(args.seed, args.out), indent=2))
