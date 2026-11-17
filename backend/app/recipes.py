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

ALIASES={'鸡蛋':['egg','eggs','鸡蛋'],'西红柿':['tomato','tomatoes','番茄','西红柿'],'土豆':['potato','potatoes','马铃薯','土豆'],'鸡肉':['chicken','鸡胸肉','鸡胸','鸡腿','鸡肉'],'牛奶':['milk','牛奶'],'花生':['peanut','peanuts','花生'],'大豆':['soy','tofu','豆腐','大豆']}
def canonical(name):
    value=name.strip().casefold()
    return next((key for key,aliases in ALIASES.items() if value in aliases),value)
def inventory(req,catalog):
    result={}
    for item in [{'name':catalog.get(x,x),'quantity':None,'unit':''} for x in req.ingredients]+[x.model_dump() for x in req.pantry]:
        key=canonical(item['name'])
        if not key:continue
        if key in result:
            if item['quantity'] is not None:result[key]=item
        else:result[key]=item
    return list(result.values())
def validate_exclusions(text,excluded):
    from .ai_services import check_restrictions
    banned=list(dict.fromkeys(excluded+[alias for x in excluded for alias in ALIASES.get(canonical(x),[])]))
    check_restrictions(text,banned)

FLAVORS = {'any': '不限', 'light': '清淡', 'savory': '家常咸鲜', 'spicy': '香辣'}


def build_prompt(req: RecipeRequest, catalog: dict[str, str], previous=None) -> str:
    """Build the model request. Food ids are supplied so the answer can be
    validated against the user's own catalog, never invented by the model."""
    return json.dumps({
        'task': '根据手里的食材、口味、可用时间、份数与忌口，生成 1 到 3 道可操作的家常菜，每道给出用料、分步做法与每步火候。',
        'request': {
            'available_ingredients': inventory(req,catalog),
            'equipment':req.equipment,'difficulty':req.difficulty,'adjustment':req.adjustment,'previous_recipe':previous,
            'flavor': FLAVORS.get(req.flavor, '不限'),
            'max_minutes': req.max_minutes,
            'servings': req.servings,
            'banned': list(dict.fromkeys(req.allergens+req.excluded)),
        },
        'available_food_ids': [
            {'food_id': fid, 'name': name} for fid, name in list(catalog.items())[:60]
        ],
        'rules': [
            'items 中的 food_id 只能取自 available_food_ids；找不到对应食物时把 items 留空，不要编造 id。',
            '必须排除 banned 中的忌口食材及其常见别名与含该成分的调味料；不确定是否含有时不要使用，并在 note 中说明无法核实。',
            '每道菜至少 2 步，每步写清火候；只写一般家常烹饪做法。',
            '使用本次available_ingredients及数量，优先已有食材。额外食材必须列入missing_ingredients；输出每份nutrition估算及alternatives替代食材，遵守时间、难度和厨具。替代食材也不能包含banned。',
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
    available = {canonical(x['name']) for x in inventory(req,catalog)}
    matched = len({canonical(catalog[i['food_id']]) for i in items} & available)
    rid = 'ai-' + hashlib.sha1((answer.name + str(index)).encode('utf-8')).hexdigest()[:10]
    return {
        'id': rid,
        'name': answer.name,
        'nutrition':answer.nutrition.model_dump() if answer.nutrition else None,
        'alternatives':answer.alternatives,'missing_ingredients':answer.missing_ingredients,
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


async def recommend(req: RecipeRequest, catalog: dict[str, str], previous=None):
    plan = await OpenAICompatibleProvider().generate(build_prompt(req, catalog, previous), RecipePlan)
    texts = []
    for answer in plan.recipes:
        texts += [answer.name, answer.ingredients_text, answer.heat_tips, answer.note, *answer.alternatives, *answer.missing_ingredients]
        texts += [step.title + ' ' + step.detail + ' ' + step.heat for step in answer.steps]
    if review_answer(' '.join(texts)):
        raise ProviderUnavailable('模型输出未通过复核')

    validate_exclusions(json.dumps(plan.model_dump(),ensure_ascii=False),req.allergens+req.excluded)
    if any(answer.minutes>req.max_minutes for answer in plan.recipes):
        from fastapi import HTTPException
        raise HTTPException(422,'生成做法超出可用时间，请重试或调整时间')
    recipes = [
        public_recipe(answer, index, catalog, req)
        for index, answer in enumerate(plan.recipes)
    ]
    note = ('菜谱由 AI 生成，请按实际食材核对；'
            '份量与营养均为估计，调味料与另备食材需自行准备。')
    if req.allergens:
        note += (' 忌口「' + '、'.join(req.allergens) + '」由模型按要求排除，'
                 '无法全面核实别名、调味料成分与交叉接触风险，请食用前自行确认。')
    return {'recipes': recipes, 'mode': 'live-model', 'note': note, 'estimated': True}
