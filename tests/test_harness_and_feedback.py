import pytest
from omni_core.self_improvement.human_feedback_learner import (
    is_user_correction,
    extract_correction_rule,
    record_user_feedback,
    UserCorrectionRule
)
from omni_core.coding_council.regression_guard import RegressionGuard
from omni_core.harness.evidence_verifier import EvidenceVerifier
from omni_core.harness.harness_runner import HarnessRunner
from omni_core.skills_registry.skill_router import SkillRouter
from omni_core.skills_registry.skill_harvester import SkillHarvester

def test_human_feedback_learner_detection():
    assert is_user_correction("Não faça assim, está errado!") is True
    assert is_user_correction("Por favor, liste os arquivos.") is False
    
    rule = extract_correction_rule("Nunca altere o arquivo de produção sem teste", last_assistant_action="Edição direta")
    assert isinstance(rule, UserCorrectionRule)
    assert rule.scope == "global"
    assert "Nunca altere" in rule.mandatory_correct_behavior

def test_regression_guard_and_test_creation(tmp_path):
    guard = RegressionGuard(root_dir=tmp_path)
    test_path = guard.create_regression_test(
        issue_title="Divide by zero in calc",
        failing_code_snippet="1 / 0",
        expected_behavior="Return error or 0",
    )
    assert test_path.exists()
    passed, log = guard.run_regression_suite()
    assert passed is True

def test_evidence_verifier():
    assert EvidenceVerifier.verify_evidence([]) is False
    assert EvidenceVerifier.verify_evidence([{"verified": True}]) is True
    assert EvidenceVerifier.verify_evidence([{"exit_code": 0}]) is True
    assert EvidenceVerifier.verify_evidence([{"exit_code": 1}]) is False

def test_harness_runner_lifecycle(tmp_path):
    runner = HarnessRunner(workspace_root=tmp_path)
    stage1 = runner.execute_stage_1_discovery("Build user authentication")
    assert stage1["autonomous_mode"] is True
    
    plan_path = runner.execute_stage_2_plan("Build user authentication")
    assert plan_path.exists()
    assert "OMNI_PLAN" in plan_path.read_text(encoding="utf-8")

def test_skill_router_and_harvester(tmp_path):
    skills = SkillRouter.get_skills_for_niche("sec_reverse")
    assert "reverse-engineer-anything" in skills
    
    harvester = SkillHarvester(target_dir=tmp_path)
    sanitized = harvester.sanitize_skill_markdown("rm -rf /")
    assert sanitized is False
    
    res = harvester.search_and_install_github_skill("Cybersecurity Hardening")
    assert res["installed"] is True
