"""
Test fixtures for the harness.

Each fixture module exposes:
    case    : CaseSpec
    grader  : GraderSpec

Usage::

    from tests.fixtures import layer1_kb_hit, layer2_compose, layer3_generate
    result = run_case(layer1_kb_hit.case, system, layer1_kb_hit.grader, system_version="test")
"""

from . import layer1_kb_hit, layer2_compose, layer3_generate

__all__ = ["layer1_kb_hit", "layer2_compose", "layer3_generate"]
