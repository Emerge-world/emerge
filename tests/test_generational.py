from simulation.agent import Agent


def test_generational_fields_default_values():
    agent = Agent(name="Ada", x=0, y=0)
    assert agent.generation == 0
    assert agent.parent_ids == []
    assert agent.born_tick == 0


def test_generational_fields_in_get_status():
    agent = Agent(name="Ada", x=0, y=0)
    status = agent.get_status()
    assert "generation" in status
    assert "parent_ids" in status
    assert "born_tick" in status
    assert status["generation"] == 0
    assert status["parent_ids"] == []
    assert status["born_tick"] == 0


def test_generational_fields_settable():
    agent = Agent(name="Ada", x=0, y=0)
    agent.generation = 1
    agent.parent_ids = ["Ada", "Bruno"]
    agent.born_tick = 42
    assert agent.generation == 1
    assert agent.parent_ids == ["Ada", "Bruno"]
    assert agent.born_tick == 42
    # Also reflected in get_status
    status = agent.get_status()
    assert status["generation"] == 1
    assert status["parent_ids"] == ["Ada", "Bruno"]
    assert status["born_tick"] == 42
