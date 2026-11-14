"""BM25 retrieval adapted from Shiqi's Chinese bigram index; no vector claims."""
import math
import re
from collections import Counter
URL='https://www.who.int/news-room/fact-sheets/detail/healthy-diet'
DOCUMENTS=[
 {'id':'who-diversity','title':'饮食多样性','text':'选择不同类别的蔬菜、水果、豆类、全谷物和蛋白质来源，让餐食更丰富。','tags':'下一餐 蔬菜 营养 推荐 多样 搭配'},
 {'id':'who-balance','title':'饮食需要因人而异','text':'饮食搭配应考虑个人活动、偏好、文化习惯和可获得的食物，不能只按步数决定餐食。','tags':'活动 预算 热量 偏好'},
 {'id':'who-grains','title':'全谷物与主食搭配','text':'主食可从全谷物、豆类等多种来源选择，例如燕麦和糙米，而不只依赖精制谷物。','tags':'米饭 燕麦 面条 主食 全谷物'},
 {'id':'who-salt','title':'烹饪中的盐与调味品','text':'减少高盐调味品和咸味零食，选购食品时查看钠含量。','tags':'盐 钠 调味 酱油'},
 {'id':'who-protein','title':'蛋白质来源可以多样','text':'蛋白质可以来自动物和植物食物；豆类也是可选择的来源。','tags':'鸡肉 豆腐 豆类 鸡蛋 蛋白质 替换'},
 {'id':'who-sugar','title':'饮料中的游离糖','text':'果汁也可能含较多游离糖，选择饮品时需要留意，而非把果汁当作完整水果。','tags':'饮料 糖 果汁 水果'},
]
for doc in DOCUMENTS: doc.update(url=URL,version='WHO 2026-01-26 / reviewed 2026-11-14',scope='一般成人饮食教育；不用于疾病诊疗',source='WHO Healthy diet')
def tokens(text):
    parts=re.findall(r'[\u4e00-\u9fff]+|[a-z0-9]+',text.lower())
    return [t for part in parts for t in ([part] if part.isascii() or len(part)==1 else [part[i:i+2] for i in range(len(part)-1)])]
def search(query,k=3):
    terms=set(tokens(query[:2000])); corpus=[Counter(tokens(d['title']*2+d['text']+d['tags'])) for d in DOCUMENTS]
    lengths=[sum(c.values()) for c in corpus];avg=sum(lengths)/len(corpus);results=[]
    for d,tf,length in zip(DOCUMENTS,corpus,lengths):
        score=0
        for term in terms:
            f=tf[term]
            if not f: continue
            df=sum(term in c for c in corpus);idf=math.log(1+(len(corpus)-df+.5)/(df+.5))
            score+=idf*f*2.4/(f+1.4*(.28+.72*length/avg))
        if score>0: results.append({**d,'score':round(score,4),'method':'bm25'})
    return sorted(results,key=lambda d:d['score'],reverse=True)[:max(1,min(k,5))]
