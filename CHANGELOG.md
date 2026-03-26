# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2026-03-26

### Initial Release

#### Core Engine (`adaptive_skill/core.py`)
- Three-layer progressive architecture (Layer 1 / 2 / 3)
- Layer 1: KB cache search with Chinese 2-gram tokenization
- Layer 2: LTM-based skill composition via `SkillComposer`
- Layer 3: Auto-generation via `SkillGenerator` with 4 strategies
- Feedback-driven learning: `solve()` accepts optional `feedback` parameter
- `_analyze_feedback()`: tri-state sentiment (positive / negative / neutral)
- Full serialization: `Skill.to_dict()` / `Skill.from_dict()`

#### Quality Evaluator (`adaptive_skill/evaluator.py`)
- 7-dimension scoring: completeness, clarity, feasibility, evidence, generalizability, novelty, risk_mitigation
- Auto-approval threshold: overall_score ≥ 0.70
- Confidence level classification: high / medium / low

#### Skill Composer (`adaptive_skill/composer.py`)
- Problem analysis and LTM search
- Composability assessment
- Multi-framework composition plan generation

#### Skill Generator (`adaptive_skill/generator.py`)
- 4 generation strategies: template / analogy / decomposition / hybrid
- Intelligent strategy selection decision tree
- Integration with quality evaluator

#### Tests
- 23 unit tests, all passing
- Test groups: `TestSkillSerialization`, `TestSkillExecutor`, `TestAnalyzeFeedback`, `TestLayer1`, `TestSolveWithNoClients`, `TestSkillFromKBEntry`
