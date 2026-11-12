"""CI-only server with a known CAPTCHA image. Never used by Docker/production."""
from unittest.mock import patch
import uvicorn
import os
from app.main import app, limits
from starlette.responses import Response
from .helpers import CAPTCHA_ANSWER

class ScenarioApp:
    """Isolate rate-limit windows between E2E scenarios, never installed in production."""
    async def __call__(self, scope, receive, send):
        if scope['type']=='http' and scope['path']=='/__test/reset-rate-limits' and scope['method']=='POST':
            limits.clear()
            await Response(status_code=204)(scope,receive,send)
            return
        await app(scope,receive,send)

if __name__ == '__main__':
    with patch('app.auth.new_code', return_value=CAPTCHA_ANSWER):
        uvicorn.run(ScenarioApp(), host='127.0.0.1', port=int(os.getenv('E2E_API_PORT','8000')), access_log=False)
