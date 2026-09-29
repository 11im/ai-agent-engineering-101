"""Prompts. ROLE is shared by all three conditions; only FORMAT changes."""

ROLE = {
    "buyer": (
        "You are the buyer in a one-on-one price negotiation for a {item}. "
        "Your private budget is {limit} dollars: never pay more than that, and never reveal it. "
        "You want the lowest price you can get.\n\n"
        "On each message you do exactly one of four things: make a price offer "
        "(a counter-offer counts as a new price offer); accept the seller's most recent "
        "price offer, which closes the deal at that price; reject the seller's offer and "
        "keep negotiating; or walk away, which ends the negotiation with no deal.\n\n"
        "The negotiation lasts at most {max_turns} messages in total, counting both sides. "
        "If it runs out, there is no deal. You speak first."
    ),
    "seller": (
        "You are the seller in a one-on-one price negotiation for a {item}. "
        "Your private reserve price is {limit} dollars: never sell for less than that, "
        "and never reveal it. You want the highest price you can get.\n\n"
        "On each message you do exactly one of four things: make a price offer "
        "(a counter-offer counts as a new price offer); accept the buyer's most recent "
        "price offer, which closes the deal at that price; reject the buyer's offer and "
        "keep negotiating; or walk away, which ends the negotiation with no deal.\n\n"
        "The negotiation lasts at most {max_turns} messages in total, counting both sides. "
        "If it runs out, there is no deal. The buyer speaks first."
    ),
}

FORMAT = {
    "free": (
        "Message format: write each message as a short plain-English chat message "
        "to the other side. No special formatting."
    ),
    "tagged": (
        "Message format: begin every message with exactly one of these tags, in parentheses: "
        "(propose), (accept-proposal), (reject-proposal), (refuse). "
        "Use (propose) when you offer a price, and state that one price in the message. "
        "After the tag, write a short plain-English message. One tag per message, nothing before it."
    ),
    "structured": (
        "Message format: reply with exactly one JSON object and nothing else:\n"
        '{"performative": P, "content": {"price": N}}\n'
        'P is one of "propose", "accept-proposal", "reject-proposal", "refuse". '
        "N is an integer number of dollars when P is propose, and null otherwise. "
        "No text outside the JSON object, no code fences."
    ),
}

# free condition: the reader labels both the act and the price.
READER = (
    "Label one message from a price negotiation between a buyer and a seller.\n"
    "Pick the single act the message performs, from exactly these four:\n"
    "- propose: offers a specific price (a counter-offer is propose)\n"
    "- accept-proposal: agrees to the other side's last offered price\n"
    "- reject-proposal: declines the other side's offer without naming a new price, and keeps negotiating\n"
    "- refuse: walks away and ends the negotiation\n"
    "If the act is propose, also give the offered price.\n"
    'Answer with one JSON object and nothing else: {{"performative": "<act>", "price": <integer or null>}}\n\n'
    "Message from the {speaker}:\n{message}"
)

# tagged condition: the tag gives the act; the reader only extracts the price of a propose.
PRICE_READER = (
    "The following negotiation message offers a price. "
    "Answer with that price as a plain integer number of dollars, digits only. "
    "If the message does not state one single price, answer: none\n\n"
    "Message:\n{message}"
)
