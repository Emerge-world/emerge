from dataclasses import replace

from simulation.runtime_policy import derive_runtime_policy
from simulation.runtime_profiles import build_default_profile


def test_derive_runtime_policy_maps_capabilities_and_world_overrides():
    profile = build_default_profile()
    profile = replace(
        profile,
        world_overrides=replace(
            profile.world_overrides,
            initial_resource_scale=0.5,
            regen_chance_scale=0.25,
            regen_amount_scale=2.0,
        ),
    )
    profile.capabilities.explicit_planning = False
    profile.capabilities.semantic_memory = False

    policy = derive_runtime_policy(profile)

    assert policy.agent.explicit_planning is False
    assert policy.memory.semantic_memory is False
    assert policy.world.initial_resource_scale == 0.5
    assert policy.oracle.innovation is True


def test_derive_runtime_policy_maps_oracle_mode_and_freeze_path():
    profile = build_default_profile()
    profile.oracle.mode = "symbolic"
    profile.oracle.freeze_precedents_path = "fixtures/symbolic.json"

    policy = derive_runtime_policy(profile)

    assert policy.oracle.mode == "symbolic"
    assert policy.oracle.freeze_precedents_path == "fixtures/symbolic.json"
