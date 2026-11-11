from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field, model_validator, field_validator, ConfigDict
class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
class Auth(Strict):
    # Legacy email accounts can still log in with their complete old login name.
    username: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=10, max_length=128)

    @field_validator('username', mode='before')
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

class Registration(Auth):
    username: str = Field(min_length=3, max_length=32, pattern=r'^[a-zA-Z0-9_\u4e00-\u9fff]+$')
    captcha_id: str = Field(min_length=32, max_length=64)
    captcha_answer: str = Field(min_length=1, max_length=10)

class Consent(Strict):
    diet: bool = False
    health: bool = False
    external_ai: bool = False
class FoodItem(Strict):
    food_id: str
    grams: float = Field(gt=0, le=2000)
    confidence: float = Field(ge=0, le=1, default=1)
class Food(Strict):
    items: list[FoodItem] = Field(min_length=1, max_length=20)
    label: str = Field(default='我的餐食', max_length=80)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
class Vision(Strict):
    items: list[FoodItem] = Field(max_length=20)
    explanation: str = Field(max_length=1500)
class MealRequest(Strict):
    budget: float = Field(default=30, gt=0, le=1000)
    allergens: list[str] = Field(default_factory=list, max_length=20)
    mode: Literal['healthy', 'surprise', 'budget'] = 'healthy'
class Metric(Strict):
    kind: Literal['steps','sleep','resting_hr','exercise']
    value: float = Field(ge=0)
    unit: Literal['steps','hours','bpm','minutes']
    recorded_at: datetime
    source: Literal['manual','import','demo'] = 'manual'
    @model_validator(mode='after')
    def check(self):
        units = {'steps':('steps',100000), 'sleep':('hours',24), 'resting_hr':('bpm',250), 'exercise':('minutes',1440)}
        unit, maximum = units[self.kind]
        if self.unit != unit or self.value > maximum: raise ValueError('单位或数值不合理')
        if self.kind == 'resting_hr' and self.value < 20: raise ValueError('心率超出可录入范围')
        if self.recorded_at.tzinfo is None: raise ValueError('时间必须包含时区')
        if self.recorded_at > datetime.now(timezone.utc): raise ValueError('不能录入未来数据')
        self.recorded_at = self.recorded_at.astimezone(timezone.utc)
        return self
class Chat(Strict):
    message: str = Field(min_length=1, max_length=2000)
class Answer(Strict):
    text: str = Field(min_length=1, max_length=5000)
class Feedback(Strict):
    meal_id: str
    action: Literal['like','dislike','favorite']
