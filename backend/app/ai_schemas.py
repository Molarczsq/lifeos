from typing import Literal
from pydantic import Field, field_validator
from .schemas import Strict, CatalogInput, Food
class Preferences(Strict):
    goal: str = Field(default='',max_length=200)
    habits: str = Field(default='',max_length=300)
    allergens: list[str] = Field(default_factory=list,max_length=20)
    avoid: list[str] = Field(default_factory=list,max_length=20)
    likes: list[str] = Field(default_factory=list,max_length=20)
    activity: str = Field(default='',max_length=200)
    @field_validator('allergens','avoid','likes')
    @classmethod
    def bounded(cls,values):
        if any(not v.strip() or len(v)>60 for v in values): raise ValueError('偏好条目需为1–60字')
        return list(dict.fromkeys(v.strip() for v in values))
class ProfileTurn(Strict):
    text:str=Field(default='',max_length=1000)
    skip:bool=False
class ProfileDraft(Strict):
    preferences:Preferences
    question:str=Field(max_length=300)
class PlanRequest(Strict):
    request:str=Field(default='给我一个下一餐建议',min_length=1,max_length=1500)
    budget:float=Field(default=30,gt=0,le=1000)
    ingredients:str=Field(default='',max_length=500)
    restrictions:list[str]=Field(default_factory=list,max_length=20)
    mode:Literal['balanced','surprise','protein','vegetable','budget','fridge']='balanced'
    previous_id:str|None=Field(default=None,max_length=64)
    @field_validator('restrictions')
    @classmethod
    def bounded_restrictions(cls,values):
        return Preferences.bounded(values)
class RecipeItem(CatalogInput):
    grams:float=Field(gt=0,le=2000)
class Recipe(Strict):
    name:str=Field(min_length=1,max_length=80)
    reason:str=Field(min_length=1,max_length=1000)
    items:list[RecipeItem]=Field(min_length=1,max_length=12)
    price_estimate:float=Field(ge=0,le=1000)
    steps:list[str]=Field(default_factory=list,max_length=10)
    alternatives:list[str]=Field(default_factory=list,max_length=5)
class QueryArgs(Strict):
    query:str=Field(min_length=1,max_length=500)
class NameArgs(Strict):
    prepare_meal:bool=False
    name:str=Field(min_length=1,max_length=80)
class EmptyArgs(Strict): pass
class NavigateArgs(Strict):
    page:Literal['overview','scan','plan','box','catalog','settings','history']='scan'
class ToolMeal(Food): pass
class ProactiveRequest(Strict):
    event:Literal['open','meal_saved','vision_confirmed','next_meal']='open'
class Advice(Strict):
    text:str=Field(min_length=1,max_length=1500)
    questions:list[str]=Field(default_factory=list,max_length=4)
