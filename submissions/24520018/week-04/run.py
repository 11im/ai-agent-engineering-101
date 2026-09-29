"""Runner: one run is one condition, one repeat, all scenarios.

    python run.py --condition free --repeat 1 --model claude-haiku-4-5

Appends one row per episode to results.csv and skips (run, scenario) pairs
already there, so an interrupted run continues where it stopped. The console
output is also written to logs/<run>.txt.
"""
import argparse
import csv
import json
import time
from pathlib import Path

from llm import Model, cli_version
from prompts import FORMAT, ROLE
from protocol import MAX_TURNS, PARSERS, step

HERE = Path(__file__).parent
HEADER = ["run", "condition", "scenario", "deal_possible", "outcome", "price", "correct",
          "violation", "turns", "format_errors", "reader_calls", "note"]


def render(history: list, me: str) -> str:
    if not history:
        return "The negotiation has started. Write your opening message."
    other = "seller" if me == "buyer" else "buyer"
    lines = [f"[{h['turn']}] {'You' if h['speaker'] == me else other.capitalize()}: {h['text']}"
             for h in history]
    return "Messages so far, oldest first:\n\n" + "\n\n".join(lines) + "\n\nWrite your next message."


def episode(model: Model, condition: str, sc: dict, log) -> dict:
    system = {
        role: ROLE[role].format(item=sc["item"], limit=sc[key], max_turns=MAX_TURNS)
        + "\n\n" + FORMAT[condition]
        for role, key in (("buyer", "budget"), ("seller", "reserve"))
    }
    parse = PARSERS[condition]
    history, notes = [], []
    state, price = "continue", None
    for turn in range(1, MAX_TURNS + 1):
        speaker = "buyer" if turn % 2 else "seller"
        text = model.complete(system[speaker], render(history, speaker))
        parsed = parse(text, speaker, model.reader)
        log(f"  [{turn}] {speaker}: {text}")
        if parsed["raw"] is not None:
            log(f"      reader: {parsed['raw']}")
        log(f"      parsed: act={parsed['performative']} price={parsed['price']}"
            + (f" ERROR={parsed['error']}" if parsed["error"] else ""))
        state, price, note = step(history, parsed, turn, speaker)
        if note:
            notes.append(note)
        history.append({"turn": turn, "speaker": speaker, "text": text, "parsed": parsed})
        if state != "continue":
            break
    fenced = sum(1 for h in history if h["parsed"].get("fenced"))
    if fenced:
        notes.append(f"{fenced} fenced JSON message(s)")
    return {"outcome": state, "price": price, "turns": len(history),
            "format_errors": sum(1 for h in history if h["parsed"]["error"]),
            "reader_calls": sum(h["parsed"]["reader_calls"] for h in history),
            "note": "; ".join(notes)}


def score(sc: dict, ep: dict) -> dict:
    possible = sc["reserve"] <= sc["budget"]
    deal = ep["outcome"] == "deal"
    inside = deal and sc["reserve"] <= ep["price"] <= sc["budget"]
    return {"deal_possible": int(possible),
            "correct": int(inside if possible else not deal),
            "violation": int(deal and not inside)}


def done_pairs(path: Path) -> set:
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as f:
        return {(r["run"], r["scenario"]) for r in csv.DictReader(f)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--condition", required=True, choices=sorted(PARSERS))
    ap.add_argument("--repeat", required=True, type=int)
    ap.add_argument("--model", default="claude-haiku-4-5")
    ap.add_argument("--scenarios", default=str(HERE / "scenarios.json"))
    ap.add_argument("--out", default=str(HERE / "results.csv"))
    ap.add_argument("--logs", default=str(HERE / "logs"))
    args = ap.parse_args()

    run_id = f"{args.condition}-{args.repeat}"
    out = Path(args.out)
    logdir = Path(args.logs)
    logdir.mkdir(parents=True, exist_ok=True)
    logfile = (logdir / f"{run_id}.txt").open("a", encoding="utf-8")

    def log(msg=""):
        print(msg, flush=True)
        logfile.write(msg + "\n")
        logfile.flush()

    scenarios = json.loads(Path(args.scenarios).read_text(encoding="utf-8"))
    done = done_pairs(out)
    model = Model(args.model)
    log(f"=== run {run_id} | model {args.model} | {cli_version()} | temperature: not settable "
        f"| max_turns {MAX_TURNS} | {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Run one process per results file at a time: parallel runs race on the header.
    with out.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if f.tell() == 0:
            w.writerow(HEADER)
        for sc in scenarios:
            if (run_id, str(sc["id"])) in done:
                log(f"--- {sc['id']}: already in {out.name}, skipped")
                continue
            log(f"--- {sc['id']} {sc['item']} reserve={sc['reserve']} budget={sc['budget']}")
            try:
                ep = episode(model, args.condition, sc, log)
                s = score(sc, ep)
                row = [run_id, args.condition, sc["id"], s["deal_possible"], ep["outcome"],
                       "" if ep["price"] is None else ep["price"], s["correct"], s["violation"],
                       ep["turns"], ep["format_errors"], ep["reader_calls"], ep["note"]]
                log(f"=> outcome={ep['outcome']} price={ep['price']} correct={s['correct']} "
                    f"violation={s['violation']} turns={ep['turns']} "
                    f"format_errors={ep['format_errors']} reader_calls={ep['reader_calls']}")
            except Exception as e:
                row = [run_id, args.condition, sc["id"], int(sc["reserve"] <= sc["budget"]),
                       "", "", "", "", "", "", "", f"crash: {e}"]
                log(f"=> CRASH {e}")
            w.writerow(row)
            f.flush()
    log(f"=== calls: agent {model.calls['agent']}, reader {model.calls['reader']}")
    logfile.close()


if __name__ == "__main__":
    main()
