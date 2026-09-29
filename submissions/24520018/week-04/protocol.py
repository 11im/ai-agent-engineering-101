"""Protocol layer: read a message into a performative and a price, and decide when an episode ends."""
import json
import re

from prompts import PRICE_READER, READER

ACTS = ("propose", "accept-proposal", "reject-proposal", "refuse")
MAX_TURNS = 10

TAG_RE = re.compile(r"\((propose|accept-proposal|reject-proposal|refuse)\)")
FENCE_RE = re.compile(r"\A```(?:json)?\s*\n(.*)\n```\Z", re.DOTALL)


def result(performative=None, price=None, reader_calls=0, error=None, raw=None) -> dict:
    return {"performative": performative, "price": price,
            "reader_calls": reader_calls, "error": error, "raw": raw}


def as_price(value):
    """An integer price, or None. Bools and floats with a fraction are not prices."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def parse_free(text: str, speaker: str, reader) -> dict:
    raw = reader(READER.format(speaker=speaker, message=text))
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return result(reader_calls=1, error="reader gave no JSON", raw=raw)
    try:
        label = json.loads(m.group(0))
    except json.JSONDecodeError:
        return result(reader_calls=1, error="reader JSON invalid", raw=raw)
    act = label.get("performative")
    if act not in ACTS:
        return result(reader_calls=1, error=f"reader act {act!r} not in vocabulary", raw=raw)
    price = as_price(label.get("price"))
    if act == "propose" and price is None:
        return result(act, None, 1, "propose without a price", raw)
    return result(act, price if act == "propose" else None, 1, None, raw)


def parse_tagged(text: str, speaker: str, reader) -> dict:
    tags = TAG_RE.findall(text)
    if len(tags) != 1:
        return result(error=f"expected one tag, found {len(tags)}")
    if not TAG_RE.match(text.strip()):
        return result(error="tag is not at the start of the message")
    act = tags[0]
    if act != "propose":
        return result(act)
    raw = reader(PRICE_READER.format(message=text))
    digits = re.fullmatch(r"\$?\s*(\d+)", raw.strip())
    if not digits:
        return result(act, None, 1, f"price reader gave {raw.strip()[:40]!r}", raw)
    return result(act, int(digits.group(1)), 1, None, raw)


def parse_structured(text: str, speaker: str = "", reader=None) -> dict:
    # Haiku wraps the object in a ```json fence despite the format paragraph
    # (smoke/v1). One outer fence is stripped; the run notes how often.
    fenced = FENCE_RE.match(text.strip())
    if fenced:
        text = fenced.group(1)
    r = _parse_json_message(text)
    r["fenced"] = bool(fenced)
    return r


def _parse_json_message(text: str) -> dict:
    try:
        msg = json.loads(text)
    except json.JSONDecodeError as e:
        return result(error=f"not a JSON object: {e.msg}")
    if not isinstance(msg, dict):
        return result(error="JSON is not an object")
    act = msg.get("performative")
    if act not in ACTS:
        return result(error=f"performative {act!r} not in vocabulary")
    content = msg.get("content")
    price = as_price(content.get("price")) if isinstance(content, dict) else None
    if act == "propose" and price is None:
        return result(act, None, 0, "propose without an integer content.price")
    return result(act, price if act == "propose" else None)


PARSERS = {"free": parse_free, "tagged": parse_tagged, "structured": parse_structured}


def step(history: list, parsed: dict, turn: int, speaker: str):
    """Decide what the current message does to the episode.

    Returns (state, price, note). state is continue, deal, no_deal or open.
    A message that could not be parsed has no act: the episode goes on and the
    turn still counts. An accept with no earlier offer from the other side is
    treated the same way.
    """
    act = parsed["performative"]
    note = ""
    if act == "refuse":
        return "no_deal", None, note
    if act == "accept-proposal":
        offers = [h["parsed"]["price"] for h in history
                  if h["speaker"] != speaker and h["parsed"]["performative"] == "propose"]
        if offers:
            return "deal", offers[-1], note
        note = f"turn {turn}: accept with no offer from the other side"
    if turn >= MAX_TURNS:
        return "open", None, note
    return "continue", None, note
