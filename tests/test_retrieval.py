from simulation.retrieval import RetrievalContext, rank_memory_entries


def test_retrieval_prioritizes_hunger_knowledge():
    context = RetrievalContext(
        hunger=85,
        energy=60,
        life=90,
        visible_resources={"fruit"},
        inventory_items=set(),
        current_goal="stabilize food",
        current_subgoal="move toward fruit",
        blockers=(),
    )

    ranked = rank_memory_entries(
        semantic=["Fruit reduces hunger quickly", "Rest helps when energy is low"],
        episodic=["I failed to reach the river yesterday"],
        task=["Plan blocked when fruit disappeared"],
        context=context,
        limit=2,
    )

    assert ranked[0] == "Fruit reduces hunger quickly"
