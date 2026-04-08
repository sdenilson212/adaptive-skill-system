# -*- coding: utf-8 -*-
"""Tests for SkillComposer (Layer 2 composition engine)"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock

from adaptive_skill.composer import (
    LTMSearchResult,
    CompositionPlan,
    SkillComposer,
)


class TestLTMSearchResult:
    """Tests for LTMSearchResult dataclass"""
    
    def test_create_ltm_search_result(self):
        """Should create LTM search result with all fields"""
        result = LTMSearchResult(
            memory_id="mem-001",
            content="Test content",
            category="strategy",
            tags=["marketing", "launch"],
            relevance_score=0.85,
            timestamp=datetime(2026, 4, 8, 12, 0, 0),
        )
        
        assert result.memory_id == "mem-001"
        assert result.content == "Test content"
        assert result.category == "strategy"
        assert result.tags == ["marketing", "launch"]
        assert result.relevance_score == 0.85
    
    def test_ltm_search_result_to_dict(self):
        """Should serialize to dictionary"""
        result = LTMSearchResult(
            memory_id="mem-002",
            content="Another test",
            category="execution",
            tags=["process"],
            relevance_score=0.75,
            timestamp=datetime(2026, 4, 8, 12, 0, 0),
        )
        
        d = result.to_dict()
        
        assert d["memory_id"] == "mem-002"
        assert d["content"] == "Another test"
        assert d["category"] == "execution"
        assert d["tags"] == ["process"]
        assert d["relevance_score"] == 0.75
        assert "timestamp" in d


class TestCompositionPlan:
    """Tests for CompositionPlan dataclass"""
    
    def test_create_composition_plan(self):
        """Should create composition plan with all fields"""
        plan = CompositionPlan(
            base_framework="product-launch",
            components=[
                {"source": "mem-001", "aspect": "target_audience"},
                {"source": "mem-002", "aspect": "channel_strategy"},
            ],
            adaptation_strategy={"merge_strategy": "priority_based"},
            estimated_quality=0.82,
        )
        
        assert plan.base_framework == "product-launch"
        assert len(plan.components) == 2
        assert plan.adaptation_strategy["merge_strategy"] == "priority_based"
        assert plan.estimated_quality == 0.82
    
    def test_composition_plan_to_dict(self):
        """Should serialize to dictionary"""
        plan = CompositionPlan(
            base_framework="content-strategy",
            components=[{"source": "mem-003", "aspect": "tone"}],
            adaptation_strategy={},
            estimated_quality=0.9,
        )
        
        d = plan.to_dict()
        
        assert d["base_framework"] == "content-strategy"
        assert d["components"] == [{"source": "mem-003", "aspect": "tone"}]
        assert d["estimated_quality"] == 0.9


class TestSkillComposer:
    """Tests for SkillComposer initialization and configuration"""
    
    def test_composer_initialization_with_clients(self):
        """Should initialize with LTM and KB clients"""
        mock_ltm = Mock()
        mock_kb = Mock()
        
        composer = SkillComposer(ltm_client=mock_ltm, kb_client=mock_kb)
        
        assert composer.ltm is mock_ltm
        assert composer.kb is mock_kb
    
    def test_composer_without_clients(self):
        """Should initialize without clients (graceful degradation)"""
        composer = SkillComposer()
        
        assert composer.ltm is None
        assert composer.kb is None
    
    def test_composer_with_threshold_policy(self):
        """Should accept custom threshold policy"""
        from adaptive_skill.thresholds import DEFAULT_THRESHOLD_POLICY
        
        composer = SkillComposer(threshold_policy=DEFAULT_THRESHOLD_POLICY)
        
        assert composer.threshold_policy is DEFAULT_THRESHOLD_POLICY


class TestSkillComposerIntegration:
    """Integration tests for SkillComposer with threshold policy"""
    
    def test_composer_uses_threshold_policy_for_decisions(self):
        """Should use threshold policy for coverage decisions"""
        from adaptive_skill.thresholds import RuntimeThresholdPolicy, DEFAULT_THRESHOLD_POLICY
        
        mock_ltm = Mock()
        mock_kb = Mock()
        
        composer = SkillComposer(
            ltm_client=mock_ltm,
            kb_client=mock_kb,
            threshold_policy=DEFAULT_THRESHOLD_POLICY,
        )
        
        # Composer should have threshold policy configured
        assert composer.threshold_policy is DEFAULT_THRESHOLD_POLICY
        # Verify threshold values are accessible
        assert composer.threshold_policy.layer2_min_ltm_coverage == 0.30
        assert composer.threshold_policy.layer2_composability_threshold == 0.65
