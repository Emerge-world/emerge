from unittest.mock import MagicMock

from simulation.agent import Agent
from simulation.message import IncomingMessage, VALID_INTENTS
from simulation.oracle import Oracle


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


# --- Oracle communicate tests ---

def make_two_agents():
    sender = Agent(name="Kai", x=5, y=5)
    sender.energy = 20
    target = Agent(name="Bruno", x=6, y=5)  # 1 tile away
    return sender, target


def make_oracle(sender, target):
    oracle = Oracle(world=MagicMock(), llm=None)
    oracle.current_tick_agents = [sender, target]
    oracle._communicated_this_tick = set()
    return oracle


def test_communicate_queues_message():
    sender, target = make_two_agents()
    oracle = make_oracle(sender, target)
    action = {"action": "communicate", "target": "Bruno", "message": "Fruit east!", "intent": "share_info"}
    result = oracle.resolve_action(sender, action, tick=1)
    assert result["success"] is True
    assert len(target.incoming_messages) == 1
    assert target.incoming_messages[0].sender == "Kai"
    assert target.incoming_messages[0].message == "Fruit east!"


def test_communicate_costs_energy():
    sender, target = make_two_agents()
    oracle = make_oracle(sender, target)
    action = {"action": "communicate", "target": "Bruno", "message": "Hey!", "intent": "warn"}
    oracle.resolve_action(sender, action, tick=1)
    assert sender.energy == 17  # 20 - 3


def test_communicate_invalid_intent():
    sender, target = make_two_agents()
    oracle = make_oracle(sender, target)
    action = {"action": "communicate", "target": "Bruno", "message": "Attack!", "intent": "attack"}
    result = oracle.resolve_action(sender, action, tick=1)
    assert result["success"] is False
    assert len(target.incoming_messages) == 0


def test_communicate_target_not_found():
    sender, _ = make_two_agents()
    oracle = Oracle(world=MagicMock(), llm=None)
    oracle.current_tick_agents = [sender]  # target not in list
    oracle._communicated_this_tick = set()
    action = {"action": "communicate", "target": "Ghost", "message": "Hey!", "intent": "share_info"}
    result = oracle.resolve_action(sender, action, tick=1)
    assert result["success"] is False


def test_communicate_target_out_of_range():
    sender = Agent(name="Kai", x=0, y=0)
    sender.energy = 20
    far_target = Agent(name="Bruno", x=9, y=9)  # 18 tiles away
    oracle = Oracle(world=MagicMock(), llm=None)
    oracle.current_tick_agents = [sender, far_target]
    oracle._communicated_this_tick = set()
    action = {"action": "communicate", "target": "Bruno", "message": "Hi!", "intent": "share_info"}
    result = oracle.resolve_action(sender, action, tick=1)
    assert result["success"] is False


def test_communicate_rate_limit():
    sender, target = make_two_agents()
    oracle = make_oracle(sender, target)
    oracle._communicated_this_tick = {"Kai"}  # already communicated this tick
    action = {"action": "communicate", "target": "Bruno", "message": "Again!", "intent": "warn"}
    result = oracle.resolve_action(sender, action, tick=1)
    assert result["success"] is False
    assert len(target.incoming_messages) == 0


def test_communicate_insufficient_energy():
    sender, target = make_two_agents()
    sender.energy = 2  # less than COMMUNICATE_ENERGY_COST=3
    oracle = make_oracle(sender, target)
    action = {"action": "communicate", "target": "Bruno", "message": "Hi!", "intent": "share_info"}
    result = oracle.resolve_action(sender, action, tick=1)
    assert result["success"] is False


def test_communicate_token_budget_enforced():
    sender, target = make_two_agents()
    oracle = make_oracle(sender, target)
    action = {
        "action": "communicate",
        "target": "Bruno",
        "intent": "share_info",
        "message_tokens": ["a", "b", "c", "d", "e", "f", "g"],
    }
    result = oracle.resolve_action(sender, action, tick=1)
    assert result["success"] is False
    assert "token budget" in result["message"].lower()


def test_communicate_with_structured_tokens_and_legacy_message_compat():
    sender, target = make_two_agents()
    sender.lexicon.register_symbol("zi", "fruit", owned=True)
    target.lexicon.register_symbol("zi", "fruit", owned=False)
    oracle = make_oracle(sender, target)
    action = {
        "action": "communicate",
        "target": "Bruno",
        "message": "legacy text",
        "message_tokens": ["zi", "east"],
        "intent": "share_info",
    }
    result = oracle.resolve_action(sender, action, tick=2)
    assert result["success"] is True
    queued = target.incoming_messages[0]
    assert queued.message == "zi east"
    assert queued.interpreted_message.startswith("fruit")


def test_deterministic_misunderstanding_same_input_same_output():
    sender, target = make_two_agents()
    sender.lexicon.register_symbol("ka", "water", owned=True)
    target.lexicon.register_symbol("ka", "water", owned=False)
    oracle = make_oracle(sender, target)
    action = {
        "action": "communicate",
        "target": "Bruno",
        "message_tokens": ["ka", "north"],
        "intent": "warn",
    }
    first = oracle.resolve_action(sender, action, tick=5)

    sender2, target2 = make_two_agents()
    sender2.lexicon.register_symbol("ka", "water", owned=True)
    target2.lexicon.register_symbol("ka", "water", owned=False)
    oracle2 = make_oracle(sender2, target2)
    second = oracle2.resolve_action(sender2, action, tick=5)

    assert first["communication"]["misunderstood"] == second["communication"]["misunderstood"]


def test_receiver_learns_symbol_from_sender_lexicon():
    sender, target = make_two_agents()
    sender.lexicon.register_symbol("zu", "fruit", owned=True)
    oracle = make_oracle(sender, target)
    action = {
        "action": "communicate",
        "target": "Bruno",
        "message_tokens": ["zu"],
        "intent": "share_info",
    }
    result = oracle.resolve_action(sender, action, tick=3)
    assert result["success"] is True
    assert target.lexicon.get_meaning("zu") == "fruit"
    assert "zu" in target.recently_learned_symbols


def test_no_llm_fallback_decision_still_works_with_language_prompt_empty():
    agent = Agent(name="Kai", x=0, y=0, llm=None)
    prompt = agent.get_language_prompt()
    assert prompt == ""
    action = agent.decide_action(nearby_tiles=[], tick=1)
    assert "action" in action
