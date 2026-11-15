"""Dish and cooking-step recommendations.

The local library is a transparent fallback that always works without a model
key. Live model output is schema-validated, reviewed and explicitly labelled;
it is never presented as verified nutrition or a medically reviewed recipe.
"""
import json
from .schemas import RecipeRequest, RecipeAnswer
from .llm import OpenAICompatibleProvider, ProviderUnavailable
from .agents import review_answer

KNOWN_ALLERGENS = {
    '大豆', 'soy', '豆腐', '蛋', '鸡蛋', 'egg', '麸质', 'gluten', '燕麦',
    '鸡肉', '鸡胸肉', '西兰花', '糙米',
}

RECIPES = [
    {
        'id': 'garlic-chicken-broccoli',
        'name': '蒜香鸡胸炒西兰花',
        'minutes': 15,
        'flavors': ['light', 'savory'],
        'allergens': ['鸡肉', '鸡胸肉'],
        'food_ids': ['chicken', 'broccoli'],
        'items': [{'food_id': 'chicken', 'grams': 120}, {'food_id': 'broccoli', 'grams': 150}],
        'seasonings': '蒜 2 瓣、生抽 1 勺、盐少许、食用油 1 勺',
        'ingredients_text': '鸡胸肉 120g、西兰花 150g；蒜 2 瓣、生抽 1 勺、盐少许、食用油 1 勺',
        'steps': [
            {'title': '备料', 'detail': '鸡胸肉逆纹切薄片，用少许生抽抓匀；西兰花掰成小朵洗净沥干；蒜切末。', 'heat': '无需开火'},
            {'title': '焯水', 'detail': '水烧开加少许盐，西兰花下锅焯 60 秒，捞出过凉水并沥干，后面才不会出汤。', 'heat': '大火'},
            {'title': '滑炒鸡胸', 'detail': '锅烧热后倒油，下蒜末爆香，鸡胸片平铺入锅，先别翻动，边缘变白后再翻炒至断生。', 'heat': '中大火'},
            {'title': '合炒调味', 'detail': '倒入西兰花，沿锅边淋生抽，快速翻炒 30 秒，尝味后再决定加不加盐，立即出锅。', 'heat': '大火'},
        ],
        'heat_tips': '锅要先烧热再下油；鸡胸断生即出锅，久炒会发柴。',
        'note': '调味料与蒜需另备，未计入营养估计。',
    },
    {
        'id': 'braised-tofu-broccoli',
        'name': '家常豆腐烧西兰花',
        'minutes': 18,
        'flavors': ['light', 'savory'],
        'allergens': ['大豆', 'soy', '豆腐'],
        'food_ids': ['tofu', 'broccoli'],
        'items': [{'food_id': 'tofu', 'grams': 180}, {'food_id': 'broccoli', 'grams': 150}],
        'seasonings': '生抽 1 勺、蒜 1 瓣、盐少许、食用油 1 勺、清水半碗',
        'ingredients_text': '豆腐 180g、西兰花 150g；生抽 1 勺、蒜 1 瓣、盐少许、食用油 1 勺',
        'steps': [
            {'title': '处理豆腐', 'detail': '豆腐切成 2cm 方块，用厨房纸吸干表面水分，避免下锅溅油和碎裂。', 'heat': '无需开火'},
            {'title': '煎豆腐', 'detail': '平底锅热油，豆腐块平铺，中火煎至一面金黄再轻轻翻面，两面定形后盛出备用。', 'heat': '中火'},
            {'title': '烧制', 'detail': '锅里留底油爆香蒜末，加生抽和半碗清水烧开，放回豆腐，中小火焖 5 分钟让汤汁收浓。', 'heat': '中小火'},
            {'title': '收尾', 'detail': '加入西兰花翻拌 2 分钟至断生，尝味补盐，汤汁略挂住豆腐即可关火。', 'heat': '中火'},
        ],
        'heat_tips': '煎豆腐时别频繁翻动；焖煮用中小火，大火容易把汤汁烧干、豆腐变老。',
        'note': '调味料需另备，未计入营养估计。',
    },
    {
        'id': 'egg-fried-brown-rice',
        'name': '鸡蛋炒糙米饭',
        'minutes': 12,
        'flavors': ['savory'],
        'allergens': ['蛋', '鸡蛋', 'egg'],
        'food_ids': ['egg', 'rice'],
        'items': [{'food_id': 'egg', 'grams': 100}, {'food_id': 'rice', 'grams': 150}],
        'seasonings': '葱花少许、盐少许、生抽半勺、食用油 1 勺',
        'ingredients_text': '鸡蛋 2 个（约 100g）、熟糙米饭 150g；葱花、盐、生抽、食用油少许',
        'steps': [
            {'title': '备料', 'detail': '鸡蛋打散加一小撮盐；糙米饭若是隔夜冷藏的，先用手抓散，避免结块。', 'heat': '无需开火'},
            {'title': '炒蛋', 'detail': '热锅倒油，蛋液下锅后用铲子快速划散，刚凝固就盛出，不要炒老。', 'heat': '中大火'},
            {'title': '炒饭', 'detail': '锅里补少许油，下米饭中火翻炒 2 分钟，把米粒炒散、炒到微微发干。', 'heat': '中火'},
            {'title': '合炒', 'detail': '倒回鸡蛋，沿锅边淋生抽，撒葱花翻匀 30 秒，尝味后出锅。', 'heat': '中大火'},
        ],
        'heat_tips': '米饭要炒到粒粒分开再合炒；生抽沿锅边淋，香气更足也更容易控咸淡。',
        'note': '调味料与葱花需另备，未计入营养估计。',
    },
    {
        'id': 'spicy-chicken-broccoli',
        'name': '香辣鸡胸炒时蔬',
        'minutes': 14,
        'flavors': ['spicy', 'savory'],
        'allergens': ['鸡肉', '鸡胸肉'],
        'food_ids': ['chicken', 'broccoli'],
        'items': [{'food_id': 'chicken', 'grams': 120}, {'food_id': 'broccoli', 'grams': 150}],
        'seasonings': '干辣椒 2 个、蒜 2 瓣、生抽 1 勺、食用油 1 勺',
        'ingredients_text': '鸡胸肉 120g、西兰花 150g；干辣椒 2 个、蒜 2 瓣、生抽 1 勺',
        'steps': [
            {'title': '备料', 'detail': '鸡胸切薄片，西兰花掰小朵沥干；干辣椒剪段去籽，蒜切片。', 'heat': '无需开火'},
            {'title': '爆香', 'detail': '冷锅冷油下干辣椒，小火慢慢煸出香味，辣椒变深红立刻下蒜片。', 'heat': '小火'},
            {'title': '炒鸡胸', 'detail': '转中大火，下鸡胸片摊开煎 20 秒再翻炒，炒到表面完全变白。', 'heat': '中大火'},
            {'title': '合炒', 'detail': '下西兰花和生抽，大火翻炒约 1 分钟至断生，立刻出锅。', 'heat': '大火'},
        ],
        'heat_tips': '干辣椒必须小火慢煸，火大容易发苦发黑；不能吃辣就减少用量或去掉辣椒籽。',
        'note': '调味料与干辣椒需另备，未计入营养估计。',
    },
    {
        'id': 'chicken-oat-congee',
        'name': '鸡胸燕麦咸粥',
        'minutes': 20,
        'flavors': ['light'],
        'allergens': ['麸质', 'gluten', '燕麦', '鸡肉', '鸡胸肉'],
        'food_ids': ['chicken', 'oats'],
        'items': [{'food_id': 'chicken', 'grams': 100}, {'food_id': 'oats', 'grams': 60}],
        'seasonings': '姜 2 片、盐少许、白胡椒少许、清水 600ml',
        'ingredients_text': '鸡胸肉 100g、燕麦片 60g；姜 2 片、盐、白胡椒少许、清水 600ml',
        'steps': [
            {'title': '煮鸡胸', 'detail': '冷水下鸡胸和姜片，水开后转小火煮 8 分钟，捞出撕成细丝，汤留着别倒。', 'heat': '小火'},
            {'title': '下燕麦', 'detail': '把燕麦片倒进鸡汤，中火煮开后转小火，边煮边搅，避免糊底。', 'heat': '中小火'},
            {'title': '收稠', 'detail': '煮 6～8 分钟至粥体略浓稠，倒回鸡丝，加盐和白胡椒调味即可。', 'heat': '小火'},
        ],
        'heat_tips': '燕麦容易糊底，全程小火并勤搅拌；想要更顺滑可多煮 3 分钟。',
        'note': '调味料与姜需另备，未计入营养估计。',
    },
    {
        'id': 'broccoli-brown-rice',
        'name': '清炒西兰花配糙米饭',
        'minutes': 12,
        'flavors': ['light'],
        'allergens': [],
        'food_ids': ['broccoli', 'rice'],
        'items': [{'food_id': 'broccoli', 'grams': 180}, {'food_id': 'rice', 'grams': 150}],
        'seasonings': '蒜 2 瓣、盐少许、食用油 1 勺',
        'ingredients_text': '西兰花 180g、熟糙米饭 150g；蒜 2 瓣、盐少许、食用油 1 勺',
        'steps': [
            {'title': '备料', 'detail': '西兰花掰小朵泡洗后沥干，蒜切末；糙米饭提前回温或蒸热。', 'heat': '无需开火'},
            {'title': '爆香', 'detail': '热锅下油和蒜末，小火炒出蒜香，蒜末刚变浅黄就进入下一步。', 'heat': '小火'},
            {'title': '快炒', 'detail': '转大火下西兰花，沿锅边淋两勺清水盖锅焖 30 秒，再开盖翻炒至翠绿断生，加盐出锅。', 'heat': '大火'},
            {'title': '装盘', 'detail': '西兰花与热糙米饭同盘摆好，喜欢的话可把菜汁淋在饭上。', 'heat': '无需开火'},
        ],
        'heat_tips': '盖锅焖半分钟比一直干炒更容易熟且保持翠绿；出锅前才加盐，避免出水。',
        'note': '调味料与蒜需另备，未计入营养估计。',
    },
]


def match_recipes(req: RecipeRequest, limit: int = 3):
    scored = []
    wanted = set(req.ingredients)
    for recipe in RECIPES:
        if recipe['minutes'] > req.max_minutes:
            continue
        declared = {a.strip().lower() for a in req.allergens}
        if any(a.lower() in declared for a in recipe['allergens']):
            continue
        hits = len(wanted & set(recipe['food_ids']))
        score = hits * 3
        if req.flavor != 'any' and req.flavor in recipe['flavors']:
            score += 2
        score += max(0, 30 - recipe['minutes']) / 10
        scored.append((score, hits, recipe))
    scored.sort(key=lambda row: (-row[0], row[2]['minutes'], row[2]['id']))
    return [{**row[2], 'matched_ingredients': row[1]} for row in scored[:limit]]


def unknown_allergens(req: RecipeRequest):
    return [a.strip() for a in req.allergens
            if a.strip() and a.strip().lower() not in {x.lower() for x in KNOWN_ALLERGENS}]


def public_recipe(recipe, source: str):
    return {
        'id': recipe['id'], 'name': recipe['name'], 'minutes': recipe['minutes'],
        'source': source, 'items': recipe['items'], 'seasonings': recipe['seasonings'],
        'ingredients_text': recipe['ingredients_text'], 'steps': recipe['steps'],
        'heat_tips': recipe['heat_tips'], 'note': recipe.get('note', ''),
        'matched_ingredients': recipe.get('matched_ingredients', 0),
    }


async def enhance_first(recipe, req: RecipeRequest, catalog_names):
    prompt = json.dumps({
        'task': '为这道家常菜写一份可操作的中文烹饪步骤，按份数调整用量',
        'dish': recipe['name'],
        'reference_ingredients': recipe['ingredients_text'],
        'reference_steps': recipe['steps'],
        'user_ingredient_names': catalog_names,
        'requested_flavor': req.flavor,
        'max_minutes': min(req.max_minutes, recipe['minutes']),
        'servings': req.servings,
        'rules': '只写一般家常烹饪做法。不诊断、不开药、不承诺疗效，不声称营养实测。'
                 '每一步写清火候。不要输出 JSON 以外的任何内容。',
    }, ensure_ascii=False)
    result = await OpenAICompatibleProvider().generate(prompt, RecipeAnswer)
    joined = ' '.join([result.name, result.ingredients_text, result.heat_tips, result.note]
                      + [step.detail for step in result.steps])
    if review_answer(joined):
        raise ProviderUnavailable('模型输出未通过复核')
    return result


async def recommend(req: RecipeRequest, catalog_names, live: bool):
    candidates = match_recipes(req)
    if not candidates:
        return {'recipes': [], 'mode': 'rules',
                'note': '没有满足时间与忌口条件的菜谱，请放宽时间或调整忌口。'}
    recipes = []
    mode = 'rules'
    if live:
        try:
            answer = await enhance_first(candidates[0], req, catalog_names)
            first = dict(candidates[0])
            first.update({
                'name': answer.name, 'minutes': answer.minutes,
                'ingredients_text': answer.ingredients_text,
                'steps': [step.model_dump() for step in answer.steps],
                'heat_tips': answer.heat_tips,
                'note': (answer.note + ' ' + first.get('note', '')).strip(),
            })
            recipes.append(public_recipe(first, 'live-model'))
            mode = 'live-model'
        except ProviderUnavailable:
            fallback = dict(candidates[0])
            fallback['note'] = (fallback.get('note', '') + ' 模型不可用，已降级为本地菜谱库。').strip()
            recipes.append(public_recipe(fallback, 'fallback'))
            mode = 'fallback'
    else:
        recipes.append(public_recipe(candidates[0], 'local-library'))
    recipes.extend(public_recipe(r, 'local-library') for r in candidates[1:])

    note = '步骤为一般家常做法建议；食材份量与营养均为估计，调味料需另备，不是实测数据。'
    unknown = unknown_allergens(req)
    if unknown:
        note += ' 未识别的忌口「' + '、'.join(unknown) + '」无法核实，请自行确认食材与交叉接触风险。'
    if mode == 'live-model':
        note += ' 首选菜谱的做法由模型生成并通过结构化校验，未经人工逐条核验。'
    return {'recipes': recipes, 'mode': mode, 'note': note, 'estimated': True}
