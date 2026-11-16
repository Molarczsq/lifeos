"""Model-generated cooking guide.

This feature deliberately has no local recipe library. It requires a configured
OpenAI-compatible provider plus the user's external AI consent; when either is
missing, or the model fails, the API reports unavailability explicitly instead
of presenting rule-based output as model output.
"""
import hashlib
import json

from .schemas import RecipePlan, RecipeRequest
from .llm import OpenAICompatibleProvider, ProviderUnavailable
from .agents import review_answer

FLAVORS = {'any': '不限', 'light': '清淡', 'savory': '家常咸鲜', 'spicy': '香辣'}


def build_prompt(req: RecipeRequest, catalog: dict[str, str]) -> str:
    """Build the model request. Food ids are supplied so the answer can be
    validated against the user's own catalog, never invented by the model."""
    return json.dumps({
        'task': '根据手里的食材、口味、可用时间、份数与忌口，生成 1 到 3 道可操作的家常菜，每道给出用料、分步做法与每步火候。',
        'request': {
            'ingredient_names': [catalog.get(i, i) for i in req.ingredients],
            'extra_ingredient_names': req.extra_ingredients,
            'flavor': FLAVORS.get(req.flavor, '不限'),
            'max_minutes': req.max_minutes,
            'servings': req.servings,
            'banned': req.allergens,
        },
        'available_food_ids': [
            {'food_id': fid, 'name': name} for fid, name in list(catalog.items())[:60]
        ],
        'rules': [
            'items 中的 food_id 只能取自 available_food_ids；找不到对应食物时把 items 留空，不要编造 id。',
            'extra_ingredient_names 是用户手头另有的食材，不在食物目录中；可以用来搭配做法，但 items 不要引用它们，也不要估算其营养。',
            '必须排除 banned 中的忌口食材及其常见别名与含该成分的调味料；不确定是否含有时不要使用，并在 note 中说明无法核实。',
            '每道菜至少 2 步，每步写清火候；只写一般家常烹饪做法。',
            '份量与营养均为估计，不是实测；调味料与另备食材需单独说明。',
            '不诊断、不开药、不承诺疗效、不声称营养实测、不给出极端饮食建议。',
            '只输出符合 JSON Schema 的 JSON 对象，不要输出其他内容。',
        ],
    }, ensure_ascii=False)


def public_recipe(answer, index: int, catalog: dict[str, str], req: RecipeRequest):
    """Keep only food ids that actually exist in this user's catalog."""
    items = [
        {'food_id': item.food_id, 'grams': item.grams}
        for item in answer.items if item.food_id in catalog
    ]
    matched = len({i['food_id'] for i in items} & set(req.ingredients))
    rid = 'ai-' + hashlib.sha1((answer.name + str(index)).encode('utf-8')).hexdigest()[:10]
    return {
        'id': rid,
        'name': answer.name,
        'minutes': answer.minutes,
        'source': 'live-model',
        'items': items,
        'seasonings': '',
        'ingredients_text': answer.ingredients_text,
        'steps': [step.model_dump() for step in answer.steps],
        'heat_tips': answer.heat_tips,
        'note': answer.note,
        'matched_ingredients': matched,
    }


async def recommend(req: RecipeRequest, catalog: dict[str, str]):
    plan = await OpenAICompatibleProvider().generate(build_prompt(req, catalog), RecipePlan)
    texts = []
    for answer in plan.recipes:
        texts += [answer.name, answer.ingredients_text, answer.heat_tips, answer.note]
        texts += [step.title + ' ' + step.detail + ' ' + step.heat for step in answer.steps]
    if review_answer(' '.join(texts)):
        raise ProviderUnavailable('模型输出未通过复核')

    recipes = [
        public_recipe(answer, index, catalog, req)
        for index, answer in enumerate(plan.recipes)
    ]
    note = ('菜谱由 AI 模型生成并经 JSON Schema 校验与安全复核，未经人工逐条核验；'
            '份量与营养均为估计，调味料与另备食材需自行准备。')
    if req.extra_ingredients:
        note += ' 手头补充食材仅用于生成做法，未写入食物目录、不计入营养估计，也不能直接记录这餐。'
    if req.allergens:
        note += (' 忌口「' + '、'.join(req.allergens) + '」由模型按要求排除，'
                 '服务端无法核实别名、调味料成分与交叉接触风险，请食用前自行确认。')
    return {'recipes': recipes, 'mode': 'live-model', 'note': note, 'estimated': True}
