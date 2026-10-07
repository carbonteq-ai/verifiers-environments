"""Turn rewards follow the trajectory Posttrain trains, including re-rendered turns."""

from types import SimpleNamespace

from automationbench_v1.taskset import training_nodes


def node(role, parent, sampled=False):
    return SimpleNamespace(message=SimpleNamespace(role=role), parent=parent, sampled=sampled)


def trace(nodes, *paths):
    return SimpleNamespace(nodes=nodes, branches=[
        SimpleNamespace(trainable=True, nodes=[nodes[i] for i in path]) for path in paths])


def test_rerendered_turn_uses_its_sampled_sibling():
    # system, user, sampled raw reply (leaf), canonical copy, tool result, final sampled reply
    nodes = [node("system", None), node("user", 0), node("assistant", 1, sampled=True),
             node("assistant", 1), node("tool", 3), node("assistant", 4, sampled=True)]
    resolved = training_nodes(trace(nodes, [0, 1, 2], [0, 1, 3, 4, 5]))
    assert resolved == [nodes[0], nodes[1], nodes[2], nodes[4], nodes[5]]


def test_single_branch_is_unchanged_and_ambiguous_shapes_carry_no_turns():
    nodes = [node("user", None), node("assistant", 0, sampled=True)]
    assert training_nodes(trace(nodes, [0, 1])) == nodes
    forked = [node("user", None), node("assistant", 0, sampled=True), node("assistant", 0, sampled=True)]
    assert training_nodes(trace(forked, [0, 1], [0, 2])) is None
    # a sampled turn outside the terminal trajectory (not a sibling of a canonical copy)
    lost = [node("user", None), node("assistant", 0, sampled=True), node("tool", 1),
            node("assistant", 0), node("tool", 3), node("assistant", 4, sampled=True)]
    lost[1].parent = None
    assert training_nodes(trace(lost, [1, 2], [0, 3, 4, 5])) is None
