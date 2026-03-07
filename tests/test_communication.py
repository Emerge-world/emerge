from simulation.message import IncomingMessage, VALID_INTENTS


def test_incoming_message_fields():
    msg = IncomingMessage(sender="Bruno", tick=5, message="Fruit east!", intent="share_info")
    assert msg.sender == "Bruno"
    assert msg.tick == 5
    assert msg.message == "Fruit east!"
    assert msg.intent == "share_info"


def test_valid_intents_set():
    assert "share_info" in VALID_INTENTS
    assert "request_help" in VALID_INTENTS
    assert "warn" in VALID_INTENTS
    assert "trade_offer" in VALID_INTENTS
    assert "attack" not in VALID_INTENTS
