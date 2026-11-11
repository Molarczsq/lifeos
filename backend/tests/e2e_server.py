"""CI-only server with a known CAPTCHA image. Never used by Docker/production."""
from unittest.mock import patch
import uvicorn
from app.main import app
from .helpers import CAPTCHA_ANSWER

if __name__ == '__main__':
    with patch('app.auth.new_code', return_value=CAPTCHA_ANSWER):
        uvicorn.run(app, host='127.0.0.1', port=8000, access_log=False)
