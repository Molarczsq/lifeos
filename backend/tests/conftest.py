import os
os.environ['DATABASE_URL'] = 'sqlite://'
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from app import main, auth
from app.db import Base, Session
from .helpers import CAPTCHA_ANSWER, register

engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
Session.configure(bind=engine)

@pytest.fixture()
def anon(monkeypatch):
    monkeypatch.setattr(main, 'engine', engine)
    monkeypatch.setattr(auth, 'new_code', lambda: CAPTCHA_ANSWER)
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    Base.metadata.drop_all(engine)
    main.limits.clear()
    with TestClient(main.app) as client:
        yield client

@pytest.fixture()
def c(anon):
    assert register(anon).status_code == 200
    return anon
