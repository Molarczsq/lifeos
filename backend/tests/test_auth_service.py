"""Synchronous service tests also runnable without local networking privileges."""
import time
from http.cookies import SimpleCookie
import pytest
from fastapi import HTTPException, Request, Response
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app import auth
from app.db import Base, CaptchaChallenge, User
from app.schemas import Auth, Registration

@pytest.fixture()
def service(monkeypatch):
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    monkeypatch.setattr(auth, 'new_code', lambda: 'K7M9Q')
    with Session(engine, expire_on_commit=False) as s:
        yield s

def request(cookie=''):
    return Request({'type': 'http', 'headers': [(b'cookie', cookie.encode())]})

def cookie(response, key):
    jar = SimpleCookie()
    for value in response.headers.getlist('set-cookie'):
        jar.load(value)
    return jar[key].value

def challenge(s):
    response = Response()
    data = auth.captcha(request(), response, s)
    binding = cookie(response, auth.CAPTCHA_COOKIE)
    return data, request(auth.CAPTCHA_COOKIE + '=' + binding)

def register(s, name='new_user'):
    data, req = challenge(s)
    response = Response()
    profile = auth.register(Registration(username=name, password='secure-test-pass', captcha_id=data['id'], captcha_answer='k7m9q'), req, response, s)
    return profile, response

def test_registration_session_and_database_service(service):
    profile, response = register(service, 'New_User')
    assert profile == {'username':'new_user','consents':{}}
    token = cookie(response, auth.SESSION_COOKIE)
    account = auth.user(request('lifeos_session=' + token), service)
    assert account.username == 'new_user'
    assert account.token_hash == auth.digest(token)
    assert account.password != 'secure-test-pass'
    assert 'HttpOnly' in response.headers.getlist('set-cookie')[0]
    assert service.scalar(select(CaptchaChallenge)) is None

def test_wrong_captcha_is_not_reusable_service(service):
    data, req = challenge(service)
    fields = dict(username='alice',password='secure-test-pass',captcha_id=data['id'])
    for code in ['WRONG', 'K7M9Q']:
        with pytest.raises(HTTPException) as error:
            auth.register(Registration(**fields,captcha_answer=code),req,Response(),service)
        assert error.value.status_code == 400
    assert service.scalar(select(User)) is None

def test_captcha_binding_expiry_and_duplicates_service(service):
    data, req = challenge(service)
    body = Registration(username='alice',password='secure-test-pass',captcha_id=data['id'],captcha_answer='K7M9Q')
    with pytest.raises(HTTPException):
        auth.register(body,request(),Response(),service)
    assert service.get(CaptchaChallenge,data['id']) is not None
    service.get(CaptchaChallenge,data['id']).expires_at = time.time()-1
    service.commit()
    with pytest.raises(HTTPException):
        auth.register(body,req,Response(),service)
    register(service, 'alice')
    with pytest.raises(HTTPException) as error:
        register(service, 'ALICE')
    assert error.value.status_code == 409

def test_database_login_cookie_rotation_and_logout_service(service):
    _, response = register(service)
    old_token = cookie(response, auth.SESSION_COOKIE)
    account = service.scalar(select(User))
    account.consents = {'diet': True}
    service.commit()
    with pytest.raises(HTTPException):
        auth.login(Auth(username='new_user',password='incorrect-password'),Response(),service)
    response = Response()
    result = auth.login(Auth(username='NEW_USER',password='secure-test-pass'), response, service)
    assert result['consents']['diet'] is True
    new_token = cookie(response, auth.SESSION_COOKIE)
    assert new_token != old_token
    with pytest.raises(HTTPException):
        auth.user(request('lifeos_session=' + old_token), service)
    account = auth.user(request('lifeos_session=' + new_token), service)
    auth.logout(Response(), account, service)
    with pytest.raises(HTTPException):
        auth.user(request('lifeos_session=' + new_token), service)
