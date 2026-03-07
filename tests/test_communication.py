from simulation.message import IncomingMessage, VALID_INTENTS
from simulation.agent import Agent


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


def test_agent_has_incoming_messages():
    agent = Agent(name="Kai", x=0, y=0)
    assert agent.incoming_messages == []


def test_get_messages_prompt_empty():
    agent = Agent(name="Kai", x=0, y=0)
    assert agent.get_messages_prompt() == ""


def test_get_messages_prompt_with_message():
    agent = Agent(name="Kai", x=0, y=0)
    agent.incoming_messages.append(
        IncomingMessage(sender="Bruno", tick=12, message="Fruit east!", intent="share_info")
    )
    prompt = agent.get_messages_prompt()
    assert "INCOMING MESSAGES:" in prompt
    assert "Bruno" in prompt
    assert "tick 12" in prompt
    assert "Fruit east!" in prompt
    assert "[share_info]" in prompt


def test_get_messages_prompt_multiple():
    agent = Agent(name="Kai", x=0, y=0)
    agent.incoming_messages.append(IncomingMessage("Bruno", 10, "Go west", "warn"))
    agent.incoming_messages.append(IncomingMessage("Clara", 10, "I need help", "request_help"))
    prompt = agent.get_messages_prompt()
    assert "Bruno" in prompt
    assert "Clara" in prompt
