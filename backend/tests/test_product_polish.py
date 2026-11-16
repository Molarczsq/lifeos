"""Regression tests for the product polish pass (2026-11-16).

Covers: profile skip without consent, context-based default question
suggestions, and free-form extra ingredients reaching the model prompt.
"""

def test_profile_skip_needs_no_consent(c):
    c.put('/api/v1/consents', json={'diet': False, 'health': False, 'external_ai': False})
    r = c.post('/api/v1/ai/profile/turn', json={'skip': True})
    assert r.status_code == 200, r.text
    assert r.json()['skipped'] is True and r.json()['action'] is None
    assert c.get('/api/v1/ai/preferences').json()['preferences']['allergens'] == []
    # Skipping is special; a real profile turn still requires diet consent.
    assert c.post('/api/v1/ai/profile/turn', json={'text': '我对大豆过敏'}).status_code == 403


def test_suggestions_predict_from_context(c):
    empty = c.get('/api/v1/advisor/suggestions').json()
    assert empty['predicted'] is True and empty['mode'] == 'context-rules'
    assert any('我还没记录过一餐' in q for q in empty['questions'])
    by_page = c.get('/api/v1/advisor/suggestions?page=recipes').json()
    assert '用手里的食材' in by_page['questions'][0]

    assert c.post('/api/v1/food/entries', json={
        'items': [{'food_id': 'rice', 'grams': 100}], 'label': '米饭'}).status_code == 200
    fed = c.get('/api/v1/advisor/suggestions').json()
    assert any('今天已记录' in q for q in fed['questions'])
    assert '今日饮食记录' in fed['basis']

    c.put('/api/v1/consents', json={'diet': False, 'health': False, 'external_ai': False})
    revoked = c.get('/api/v1/advisor/suggestions').json()
    assert revoked['predicted'] is True
    assert any('开启饮食上下文授权' in q for q in revoked['questions'])


def test_recipes_extra_ingredients_reach_model(c, monkeypatch):
    from app import recipes
    captured = {}

    async def fake_generate(self, prompt, schema, image=None):
        captured['prompt'] = prompt
        return schema(recipes=[{
            'name': '香菇炒饭', 'minutes': 15, 'ingredients_text': '米饭、香菇',
            'items': [{'food_id': 'rice', 'grams': 150}],
            'steps': [{'title': '备料', 'detail': '切片', 'heat': '无需开火'},
                      {'title': '炒制', 'detail': '下锅快炒', 'heat': '大火'}],
            'heat_tips': '大火快炒', 'note': ''}])

    monkeypatch.setenv('LLM_API_KEY', 'test-only')
    monkeypatch.setattr(recipes.OpenAICompatibleProvider, 'generate', fake_generate)
    c.put('/api/v1/consents', json={'external_ai': True})
    r = c.post('/api/v1/recipes/recommend', json={
        'ingredients': ['rice'], 'extra_ingredients': ['香菇', '剩饭']})
    assert r.status_code == 200, r.text
    assert '香菇' in captured['prompt'] and '剩饭' in captured['prompt']
    assert '手头补充食材' in r.json()['note']
    assert c.post('/api/v1/recipes/recommend', json={
        'extra_ingredients': ['x' * 41]}).status_code == 422
