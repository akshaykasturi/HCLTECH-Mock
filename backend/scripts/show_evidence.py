"""Print the evidence lines for one UC4 case.

Usage (from backend):  .\\.venv\\Scripts\\python.exe scripts\\show_evidence.py UC4-0050
Add --data to also print each item's raw numbers.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.uc4.evidence import collect_evidence  # noqa: E402
from app.uc4.store import get_case  # noqa: E402


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 2
    try:
        case = get_case(args[0])
    except KeyError as exc:
        print(exc.args[0])
        return 1
    print(f"{case.case_id}  {case.route}  onset {case.onset_ts:%Y-%m-%d %H:%M:%S} UTC  "
          f"focal {case.focal_correlation_id}")
    for item in collect_evidence(case):
        print(f"[{item.id}]\n    {item.text}")
        if "--data" in argv:
            print("    " + json.dumps(item.data, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
