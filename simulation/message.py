from dataclasses import dataclass, field

VALID_INTENTS = {"share_info", "request_help", "warn", "trade_offer"}


@dataclass
class IncomingMessage:
    sender: str
    tick: int
    message: str
    intent: str
    tokens: list[str] = field(default_factory=list)
    interpreted_message: str = ""
    misunderstood: bool = False
