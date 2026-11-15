"""Offline cooking-guide fallback: rules, filters and source labelling."""

def test_recipes_rules_mode(c):
    r=c.post('/api/v1/recipes/recommend',json={'ingredients':['chicken','broccoli'],'flavor':'light','max_minutes':20})
    assert r.status_code==200
    data=r.json()
    assert data['mode']=='rules' and data['estimated'] is True
    assert data['recipes'] and all(row['source']=='local-library' for row in data['recipes'])
    first=data['recipes'][0]
    assert first['id']=='garlic-chicken-broccoli'
    assert len(first['steps'])>=2 and all(step['detail'] for step in first['steps'])
    assert all(i['food_id'] in ('rice','chicken','broccoli','tofu','egg','oats') for i in first['items'])
    c.post('/api/v1/food/entries',json={'items':first['items'],'label':first['name']})
    assert c.get('/api/v1/food/entries').json()

def test_recipes_filters_and_unknown_allergen(c):
    soy=c.post('/api/v1/recipes/recommend',json={'allergens':['大豆']}).json()
    assert all(r['id']!='braised-tofu-broccoli' for r in soy['recipes'])
    assert c.post('/api/v1/recipes/recommend',json={'max_minutes':5}).json()['recipes']==[]
    unknown=c.post('/api/v1/recipes/recommend',json={'allergens':['花生']}).json()
    assert '花生' in unknown['note'] and '无法核实' in unknown['note']

def test_recipes_live_mode_is_labelled(c, monkeypatch):
    from app import recipes
    async def fake_generate(self,prompt,schema,image=None):
        return schema(name='模拟模型菜谱',minutes=12,ingredients_text='鸡胸肉 120g',
                      steps=[{'title':'备料','detail':'切片','heat':'小火'},
                             {'title':'炒制','detail':'下锅快炒','heat':'大火'}],
                      heat_tips='大火快炒',note='模拟输出')
    monkeypatch.setenv('LLM_API_KEY','test-only')
    monkeypatch.setattr(recipes.OpenAICompatibleProvider,'generate',fake_generate)
    c.put('/api/v1/consents',json={'external_ai':True})
    data=c.post('/api/v1/recipes/recommend',json={'ingredients':['chicken']}).json()
    assert data['mode']=='live-model'
    assert data['recipes'][0]['source']=='live-model'
    assert data['recipes'][0]['name']=='模拟模型菜谱'
    assert all(r['source']=='local-library' for r in data['recipes'][1:])
    assert '未经人工逐条核验' in data['note']
