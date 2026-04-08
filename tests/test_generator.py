# -*- coding: utf-8 -*-
"""Tests for SkillGenerator (Layer 3 generation engine)"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from adaptive_skill.generator import (
    GenerationStrategy,
    GenerationContext,
    GeneratedSkillDraft,
    SkillGenerator,
)


class TestGenerationStrategy:
    """Tests for GenerationStrategy enum"""
    
    def test_generation_strategies_exist(self):
        """Should have expected generation strategies"""
        # Check that the enum has the expected values
        strategies = list(GenerationStrategy)
        assert len(strategies) >= 4  # At least 4 strategies


class TestGenerationContext:
    """Tests for GenerationContext"""
    
    def test_create_generation_context(self):
        """Should create context with problem and domain"""
        context = GenerationContext(
            problem="Design a customer onboarding flow",
            keywords=["onboarding", "customer", "flow"],
            domain="customer-success",
            complexity="medium",
            available_frameworks=["product-launch", "customer-journey"],
            ltm_info=None,
        )
        
        assert context.problem == "Design a customer onboarding flow"
        assert context.domain == "customer-success"
        assert "onboarding" in context.keywords
    
    def test_generation_context_with_ltm_info(self):
        """Should accept LTM info for context enrichment"""
        ltm_data = {"memories": ["mem-001", "mem-002"], "relevance": 0.85}
        
        context = GenerationContext(
            problem="Create a pricing strategy",
            keywords=["pricing", "strategy"],
            domain="business",
            complexity="high",
            available_frameworks=[],
            ltm_info=ltm_data,
        )
        
        assert context.ltm_info == ltm_data


class TestGeneratedSkillDraft:
    """Tests for GeneratedSkillDraft"""
    
    def test_create_generated_skill_draft(self):
        """Should create draft with skill and metadata"""
        draft = GeneratedSkillDraft(
            skill_id="skill-001",
            name="customer-onboarding-flow",
            description="Onboarding flow for new customers",
            domain="customer-success",
            steps=[
                {"step": "Welcome email", "details": "Send within 24h"},
                {"step": "Product tour", "details": "Interactive guide"},
            ],
            rationale="Based on best practices",
            generation_strategy=GenerationStrategy.TEMPLATE_BASED,
            confidence=0.85,
            needs_verification=True,
            verification_checklist=["Verify email templates"],
            potential_issues=["May need localization"],
            ltm_references=["mem-001"],
        )
        
        assert draft.name == "customer-onboarding-flow"
        assert draft.confidence == 0.85
        assert draft.generation_strategy == GenerationStrategy.TEMPLATE_BASED


class TestSkillGenerator:
    """Tests for SkillGenerator initialization and configuration"""
    
    def test_generator_initialization_with_provider(self):
        """Should initialize with LLM provider"""
        mock_provider = Mock()
        
        generator = SkillGenerator(llm_provider=mock_provider)
        
        assert generator.llm_provider is mock_provider
    
    def test_generator_without_llm_provider(self):
        """Should handle missing LLM provider gracefully"""
        generator = SkillGenerator()
        
        assert generator.llm_provider is None
    
    def test_generator_with_threshold_policy(self):
        """Should use threshold policy for quality gates"""
        from adaptive_skill.thresholds import DEFAULT_THRESHOLD_POLICY
        
        generator = SkillGenerator(threshold_policy=DEFAULT_THRESHOLD_POLICY)
        
        assert generator.threshold_policy is DEFAULT_THRESHOLD_POLICY


class TestSkillGeneratorIntegration:
    """Integration tests for SkillGenerator"""
    
    def test_generator_uses_threshold_policy_for_quality_gates(self):
        """Should use threshold policy for quality gates"""
        from adaptive_skill.thresholds import DEFAULT_THRESHOLD_POLICY
        
        generator = SkillGenerator(
            llm_provider=Mock(),
            threshold_policy=DEFAULT_THRESHOLD_POLICY,
        )
        
        # Verify threshold policy is configured
        assert generator.threshold_policy is DEFAULT_THRESHOLD_POLICY
        # Verify key thresholds are accessible
        assert generator.threshold_policy.layer3_quality_gate_threshold == 0.70
        assert generator.threshold_policy.layer3_success_status_threshold == 0.75
    
    def test_generator_can_create_context(self):
        """Should create valid GenerationContext"""
        generator = SkillGenerator()
        
        context = GenerationContext(
            problem="Test problem",
            keywords=["test"],
            domain="testing",
            complexity="low",
            available_frameworks=[],
            ltm_info=None,
        )
        
        # Context should be valid
        assert context.problem == "Test problem"
