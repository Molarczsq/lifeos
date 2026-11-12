import pytest
from app.agents import review_answer, safety

@pytest.mark.parametrize('text', [
    '我是智膳顾问，可以提供饮食和生活方式建议，但不提供疾病诊断、治疗或处方。',
    '我不能提供诊断、药物调整或危险的体重控制方案。',
    '我无法替代医生的诊断。可以帮助你了解均衡饮食。',
    '不要自行停药，请咨询医生。',
    '你好！我是智膳 LifeOS 的健康生活助手。',
])
def test_safe_introduction_and_boundaries(text):
    assert review_answer(text) is None

@pytest.mark.parametrize('text', [
    '建议你停药。',
    '胸痛时建议停药。',
    '我不提供诊断。但是建议你停药。',
    '我不提供诊断，但建议你停药。',
    '你的诊断是糖尿病。',
    '每天绝食可以迅速减重。',
])
def test_boundary_does_not_exempt_unsafe_advice(text):
    assert review_answer(text)

def test_input_triage_unchanged():
    assert '急救' in safety('我现在胸痛')
    assert safety('给我处方')
    assert safety('你是谁') is None
