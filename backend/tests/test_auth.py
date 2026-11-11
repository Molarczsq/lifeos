import base64
import hashlib
import io
import time
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session as OrmSession
from app import auth, main
from app.db import CaptchaChallenge, Session, User, initialize_schema
from .helpers import CAPTCHA_ANSWER, register

def payload(challenge, username='new_user', answer=CAPTCHA_ANSWER):
    return {'username': username, 'password': 'secure-test-pass', 'captcha_id': challenge['id'], 'captcha_answer': answer}

def test_captcha_is_image_and_stores_only_hash(anon):
    result = anon.get('/api/v1/auth/captcha')
    data = result.json()
    assert set(data) == {'id', 'image', 'expires_in'}
    assert data['expires_in'] == 300
    assert Image.open(io.BytesIO(base64.b64decode(data['image'].split(',')[1]))).size == (240, 86)
    assert result.headers['cache-control'] == 'no-store'
    with Session() as s:
        challenge = s.get(CaptchaChallenge, data['id'])
        assert challenge.answer_hash == auth.digest(data['id'] + CAPTCHA_ANSWER)
        assert challenge.binding_hash == auth.digest(anon.cookies.get('lifeos_captcha'))

def test_registration_database_and_session(anon):
    r = register(anon, '  Alice_123  ')
    assert r.status_code == 200 and r.json()['username'] == 'alice_123'
    cookie = next(value for value in r.headers.get_list('set-cookie') if value.startswith('lifeos_session='))
    assert 'HttpOnly' in cookie and 'SameSite=strict' in cookie and 'Max-Age=86400' in cookie
    assert 'Secure' not in cookie
    assert anon.get('/api/v1/me').json()['username'] == 'alice_123'
    with Session() as s:
        u = s.scalar(select(User))
        assert u.password != 'secure-test-pass'
        assert u.token_hash == hashlib.sha256(anon.cookies.get('lifeos_session').encode()).hexdigest()
    assert 'lifeos_captcha' not in anon.cookies

def test_required_captcha_and_invalid_username(anon):
    assert anon.post('/api/v1/auth/register', json={'username': 'test_user', 'password': 'secure-test-pass'}).status_code == 422
    challenge = anon.get('/api/v1/auth/captcha').json()
    for name in ['ab', 'bad user', 'new@example.com', 'a' * 33]:
        assert anon.post('/api/v1/auth/register', json=payload(challenge, name)).status_code == 422
    assert anon.post('/api/v1/auth/register', json=payload(challenge, '健康用户')).status_code == 200

def test_wrong_answer_consumed_and_refresh_invalidates(anon):
    challenge = anon.get('/api/v1/auth/captcha').json()
    assert anon.post('/api/v1/auth/register', json=payload(challenge, answer='WRONG')).status_code == 400
    assert anon.post('/api/v1/auth/register', json=payload(challenge)).status_code == 400
    first = anon.get('/api/v1/auth/captcha').json()
    second = anon.get('/api/v1/auth/captcha').json()
    assert anon.post('/api/v1/auth/register', json=payload(first)).status_code == 400
    assert anon.post('/api/v1/auth/register', json=payload(second, answer=CAPTCHA_ANSWER.lower())).status_code == 200
    assert anon.post('/api/v1/auth/register', json=payload(second, 'different_user')).status_code == 400

def test_captcha_expiry_and_browser_binding(anon):
    challenge = anon.get('/api/v1/auth/captcha').json()
    other = TestClient(main.app)
    assert other.post('/api/v1/auth/register', json=payload(challenge)).status_code == 400
    with Session() as s:
        s.get(CaptchaChallenge, challenge['id']).expires_at = time.time() - 1
        s.commit()
    assert anon.post('/api/v1/auth/register', json=payload(challenge)).status_code == 400
    assert anon.get('/api/v1/me').status_code == 401

def test_duplicate_username_case_insensitive(anon):
    assert register(anon, 'Test_Name').status_code == 200
    assert register(anon, 'test_name').status_code == 409
    with Session() as s:
        assert len(list(s.scalars(select(User)))) == 1

def test_login_rotation_restore_and_logout(c):
    c.post('/api/v1/food/entries', json={'items': [{'food_id': 'rice', 'grams': 180}]})
    c.put('/api/v1/consents', json={'diet': True})
    old_token = c.cookies.get('lifeos_session')
    profile = c.post('/api/v1/auth/login', json={'username': 'TEST_USER', 'password': 'secure-test-pass'})
    assert profile.status_code == 200 and profile.json()['consents']['diet'] is True
    assert c.cookies.get('lifeos_session') != old_token
    other = TestClient(main.app)
    other.cookies.set('lifeos_session', old_token)
    assert other.get('/api/v1/me').status_code == 401
    other.cookies.set('lifeos_session', c.cookies.get('lifeos_session'))
    assert len(other.get('/api/v1/food/entries').json()) == 1
    assert c.post('/api/v1/auth/logout').status_code == 200
    assert c.get('/api/v1/me').status_code == 401
    assert other.get('/api/v1/me').status_code == 401
    assert c.post('/api/v1/auth/login', json={'username': 'test_user', 'password': 'wrong-password'}).status_code == 401
    assert c.post('/api/v1/auth/login', json={'username': 'no_such_user', 'password': 'secure-test-pass'}).status_code == 401
    assert c.post('/api/v1/auth/login', json={'username': 'test_user', 'password': 'secure-test-pass'}).status_code == 200
    assert c.get('/api/v1/food/entries').json()[0]['items'][0]['grams'] == 180

def test_expired_session_and_secure_cookie(c, monkeypatch):
    with Session() as s:
        s.scalar(select(User)).token_expires = time.time() - 1
        s.commit()
    assert c.get('/api/v1/me').status_code == 401
    monkeypatch.setenv('COOKIE_SECURE', 'true')
    response = c.post('/api/v1/auth/login', json={'username': 'test_user', 'password': 'secure-test-pass'})
    assert 'Secure' in response.headers['set-cookie']

def test_legacy_database_migration_preserves_records(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'legacy.db'))
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE users (id VARCHAR PRIMARY KEY, email VARCHAR NOT NULL UNIQUE, password VARCHAR NOT NULL, token_hash VARCHAR, token_expires FLOAT NOT NULL, consents JSON NOT NULL)'))
        conn.execute(text("INSERT INTO users VALUES ('legacy', 'old@example.com', :password, NULL, 0, '{}')"), {'password': auth.password('legacy-pass-123')})
        conn.execute(text('CREATE TABLE records (id VARCHAR PRIMARY KEY, user_id VARCHAR, kind VARCHAR, data JSON, created_at DATETIME)'))
        conn.execute(text("INSERT INTO records VALUES ('meal', 'legacy', 'food', '{}', '2026-01-01 00:00:00')"))
    initialize_schema(engine)
    initialize_schema(engine)
    assert 'username' in {c['name'] for c in inspect(engine).get_columns('users')}
    assert 'email' not in {c['name'] for c in inspect(engine).get_columns('users')}
    with OrmSession(engine) as s:
        account = s.get(User, 'legacy')
        assert account.username == 'old@example.com'
        assert account.password == auth.password('legacy-pass-123', account.password.split(':')[0])
        assert s.execute(text('SELECT user_id FROM records WHERE id=:id'), {'id':'meal'}).scalar() == 'legacy'
