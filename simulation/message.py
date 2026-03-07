from dataclasses import dataclass

VALID_INTENTS = {"share_info", "request_help", "warn", "trade_offer"}


@dataclass
class IncomingMessage:
    sender: str
    tick: int
    message: str
    intent: str
