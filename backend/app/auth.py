"""Username authentication and database-backed, browser-bound image challenges."""
import base64
import hashlib
import hmac
import io
import os
import secrets
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from .db import CaptchaChallenge, User, db
from .schemas import Auth, Registration

router = APIRouter(prefix='/api/v1')
CAPTCHA_TTL = 300
SESSION_TTL = 86400
CAPTCHA_COOKIE = 'lifeos_captcha'
SESSION_COOKIE = 'lifeos_session'

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def password(value, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + ':' + hashlib.scrypt(value.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()

def new_code():
    return ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(5))

def render_image(code):
    image = Image.new('RGB', (240, 86), '#f0f5ea')
    draw = ImageDraw.Draw(image)
    for _ in range(55):
        x, y = secrets.randbelow(240), secrets.randbelow(86)
        draw.ellipse((x, y, x + 2, y + 2), fill='#a8bca3')
    font = ImageFont.load_default(size=37)
    for index, char in enumerate(code):
        tile = Image.new('RGBA', (46, 64))
        ImageDraw.Draw(tile).text((7, 8), char, font=font, fill='#254d39')
        tile = tile.rotate(secrets.randbelow(25) - 12, resample=Image.Resampling.BICUBIC)
        image.paste(tile, (index * 44 + 8, 8 + secrets.randbelow(8)), tile)
    for _ in range(3):
        draw.line((0, secrets.randbelow(86), 240, secrets.randbelow(86)), fill='#a0b9a1', width=1)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()

def secure_cookie():
    return os.getenv('COOKIE_SECURE', 'false') == 'true'

def public_profile(account):
    return {'username': account.username, 'consents': account.consents}

def issue_session(account, response, session):
    token = secrets.token_urlsafe(32)
    account.token_hash = digest(token)
    account.token_expires = time.time() + SESSION_TTL
    session.commit()
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite='strict',
                        secure=secure_cookie(), max_age=SESSION_TTL, path='/')
    return public_profile(account)

def user(request: Request, s=Depends(db)):
    token = request.cookies.get(SESSION_COOKIE, '')
    account = s.scalar(select(User).where(User.token_hash == digest(token))) if token else None
    if not account or account.token_expires < time.time():
        raise HTTPException(401, '请登录')
    return account

@router.get('/auth/captcha')
def captcha(request: Request, response: Response, s=Depends(db)):
    old_binding = request.cookies.get(CAPTCHA_COOKIE)
    s.execute(delete(CaptchaChallenge).where(CaptchaChallenge.expires_at <= time.time()))
    if old_binding:
        s.execute(delete(CaptchaChallenge).where(CaptchaChallenge.binding_hash == digest(old_binding)))
    challenge_id, binding, code = secrets.token_hex(24), secrets.token_urlsafe(32), new_code()
    s.add(CaptchaChallenge(id=challenge_id, answer_hash=digest(challenge_id + code),
                          binding_hash=digest(binding), expires_at=time.time() + CAPTCHA_TTL))
    s.commit()
    response.set_cookie(CAPTCHA_COOKIE, binding, httponly=True, samesite='strict',
                        secure=secure_cookie(), max_age=CAPTCHA_TTL, path='/api/v1/auth')
    return {'id': challenge_id, 'image': render_image(code), 'expires_in': CAPTCHA_TTL}

def consume_captcha(body, request, s):
    binding = request.cookies.get(CAPTCHA_COOKIE, '')
    # Atomic delete makes a challenge single-use even across parallel requests/workers.
    row = s.execute(delete(CaptchaChallenge).where(
        CaptchaChallenge.id == body.captcha_id,
        CaptchaChallenge.binding_hash == digest(binding),
    ).returning(CaptchaChallenge.answer_hash, CaptchaChallenge.expires_at)).first()
    s.commit()
    answer = body.captcha_answer.strip().upper()
    if not row or row.expires_at <= time.time() or not hmac.compare_digest(row.answer_hash, digest(body.captcha_id + answer)):
        raise HTTPException(400, '图案验证码错误或已过期，请刷新后重试')

@router.post('/auth/register')
def register(body: Registration, request: Request, response: Response, s=Depends(db)):
    consume_captcha(body, request, s)
    account = User(id=str(uuid4()), username=body.username, password=password(body.password), consents={})
    s.add(account)
    try:
        s.flush()
        profile = issue_session(account, response, s)
    except IntegrityError:
        s.rollback()
        raise HTTPException(409, '用户名已存在，请换一个或直接登录') from None
    response.delete_cookie(CAPTCHA_COOKIE, path='/api/v1/auth')
    return profile

@router.post('/auth/login')
def login(body: Auth, response: Response, s=Depends(db)):
    account = s.scalar(select(User).where(User.username == body.username))
    # Always perform the password hash computation, including for unknown accounts.
    stored = account.password if account else '0' * 32 + ':' + '0' * 128
    supplied = password(body.password, stored.split(':')[0])
    if not hmac.compare_digest(stored, supplied) or not account:
        raise HTTPException(401, '用户名或密码不正确')
    return issue_session(account, response, s)

@router.post('/auth/logout')
def logout(response: Response, account=Depends(user), s=Depends(db)):
    account.token_hash = None
    account.token_expires = 0
    s.commit()
    response.delete_cookie(SESSION_COOKIE, path='/')
    return {'ok': True}

@router.get('/me')
def me(account=Depends(user)):
    return public_profile(account)
