import random
import re
from collections import defaultdict
# Explicit illustrative seed values; not a verified laboratory dataset.
FOODS = {
 'rice': {'name':'糙米饭','kcal':123,'protein':2.7,'fat':1,'carbs':25.6},
 'chicken': {'name':'鸡胸肉','kcal':165,'protein':31,'fat':3.6,'carbs':0},
 'broccoli': {'name':'西兰花','kcal':35,'protein':2.4,'fat':0.4,'carbs':7.2},
 'tofu': {'name':'豆腐','kcal':80,'protein':8,'fat':4,'carbs':2},
 'egg': {'name':'鸡蛋','kcal':155,'protein':13,'fat':11,'carbs':1.1},
 'oats': {'name':'燕麦','kcal':389,'protein':16.9,'fat':6.9,'carbs':66.3},
}
SOURCE = {'label':'演示营养估计种子 / 每100g；非实测数据','reference':'https://fdc.nal.usda.gov/','verified':False}
KNOWLEDGE = [
 {'id':'who-diversity','title':'饮食多样性','text':'均衡与多样性是健康饮食的基础，可选择不同种类的蔬菜、全谷物和豆类。','url':'https://www.who.int/news-room/fact-sheets/detail/healthy-diet','tags':'饮食 下一餐 蔬菜 营养 推荐 多样'},
 {'id':'who-balance','title':'饮食需要因人而异','text':'饮食结构取决于个人特点、活动水平和当地可获得的食物，不能仅凭步数决定下一餐。','url':'https://www.who.int/news-room/fact-sheets/detail/healthy-diet','tags':'运动 步数 热量 健康 预算'},
]
def search(q):
    def score(d): return sum(1 for c in set(q) if c in d['tags']+d['text'])
    return [d for d in sorted(KNOWLEDGE,key=score,reverse=True) if score(d)>0][:2]
def nutrition(items):
    totals = dict.fromkeys(['kcal','protein','fat','carbs'],0.)
    for i in items:
        f = FOODS[i['food_id']]
        for k in totals: totals[k] += f[k]*i['grams']/100
    return {'totals':{k:round(v,1) for k,v in totals.items()},'kcal_range':[round(totals['kcal']*.75),round(totals['kcal']*1.3)],'source':SOURCE,'estimated':True}
MEALS = [
 {'id':'green','name':'青蔬鸡肉糙米碗','price':26,'allergens':[], 'items':[{'food_id':'rice','grams':150},{'food_id':'chicken','grams':100},{'food_id':'broccoli','grams':150}]},
 {'id':'tofu','name':'豆腐双拼能量碗','price':16,'allergens':['大豆','soy'], 'items':[{'food_id':'tofu','grams':180},{'food_id':'rice','grams':150},{'food_id':'broccoli','grams':180}]},
 {'id':'egg','name':'暖心鸡蛋燕麦碗','price':12,'allergens':['蛋','egg','燕麦','麸质','gluten'], 'items':[{'food_id':'egg','grams':100},{'food_id':'oats','grams':60}]},
]
class NutritionPlannerAgent:
    def run(self, req, feedback, recent=None):
        excluded={r['meal_id'] for r in feedback if r['action']=='dislike'}
        candidates=[m for m in MEALS if m['price']<=req.budget and m['id'] not in excluded and not any(a.lower() in '|'.join(m['allergens']).lower() or any(a.lower() in FOODS[i['food_id']]['name'].lower() for i in m['items']) for a in req.allergens)]
        # Unknown allergens cannot be safely certified against this tiny catalog.
        supported={'大豆','soy','蛋','egg','燕麦','麸质','gluten','鸡肉','西兰花','糙米','豆腐'}
        if any(a.lower() not in supported for a in req.allergens): return []
        if req.mode=='surprise': random.shuffle(candidates)
        elif req.mode=='budget': candidates.sort(key=lambda m:m['price'])
        elif recent:
            seen=[i['food_id'] for r in recent for i in r['items']]
            candidates.sort(key=lambda m:sum(seen.count(i['food_id']) for i in m['items']))
        return [{**m,**nutrition(m['items']),'reason':'按预算及已声明过敏原过滤；食材与交叉接触需再次核实。','mode':'rules'} for m in candidates]
class HealthInsightAgent:
    def run(self, metrics):
        groups=defaultdict(list)
        for m in sorted(metrics,key=lambda m:m['recorded_at']): groups[m['kind']].append(m['value'])
        return {'mode':'rules','trends':{k:{'count':len(v),'average':round(sum(v)/len(v),1),'change':round(v[-1]-v[0],1) if len(v)>1 else None} for k,v in groups.items()}, 'text':'趋势仅描述已录入样本，缺失日期不按零计算。建议选择一个可持续的小习惯，不通过运动抵扣食物。'}
def safety(text):
    if any(w in text.lower() for w in ['胸痛','呼吸困难','昏厥','chest pain']): return '如果正在出现胸痛、呼吸困难或昏厥，请立即寻求当地急救帮助。此工具无法判断病情。'
    if any(w in text.lower() for w in ['处方','诊断','药量','停药','胰岛素','催吐','绝食','自杀','suicide']): return '我不能提供诊断、药物调整或危险的体重控制方案。请联系合格医疗人员获得个体化支持。'
    return None


def review_answer(text):
    """Rule-based output review; distinguish boundary statements from advice.

    Input triage stays in safety(). This is not a clinical safety classifier.
    Check each clause so a disclaimer cannot exempt subsequent instructions.
    """
    for clause in re.split(r'[。！？!?；;，,\n]|但是|不过|然而|但', text):
        # Remove only explicit refusals/boundaries, not the whole answer.
        cleaned = re.sub(
            r'(?:不能|无法|不会|不应|不要|不可以|不)(?:为你|为您)?(?:提供|进行|做出|作出|替代|代替|建议|自行)?'
            r'(?:疾病|医疗|医生的|医生|专业|医学|任何|具体|个体化|药物调整|治疗|或|和|及|、|与|\s)*'
            r'(?:诊断|处方|停药|药量|催吐|绝食|胰岛素)'
            r'(?:(?:、|或|和|及|与)(?:诊断|处方|治疗|药量|停药|催吐|绝食))*',
            '', clause)
        # Emergency guidance generated in an answer is not a new user symptom.
        cleaned = re.sub(r'胸痛|呼吸困难|昏厥|chest pain', '', cleaned, flags=re.I)
        blocked = safety(cleaned)
        if blocked:
            return blocked
    return None
