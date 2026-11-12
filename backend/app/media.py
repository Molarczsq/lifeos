"""Private image storage: decoded, resized and re-encoded, never remote-fetched."""
import base64
import hashlib
import io
from uuid import uuid4
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .auth import user
from .db import MediaAsset, db

router = APIRouter(prefix='/api/v1')

def owned_image(s, u, image_id):
    asset = s.get(MediaAsset, image_id)
    if not asset or asset.user_id != u.id:
        raise HTTPException(404, '图片不存在')
    return asset

def image_url(asset):
    return 'data:image/jpeg;base64,' + base64.b64encode(asset.content).decode()

async def save_upload(file, s, u):
    if file.content_type not in ('image/jpeg', 'image/png', 'image/webp'):
        raise HTTPException(415, '仅支持 JPEG、PNG、WebP 图片')
    raw = await file.read(5_000_001)
    if len(raw)>5_000_000: raise HTTPException(413, '图片须小于5MB')
    try:
        with Image.open(io.BytesIO(raw)) as im:
            if im.format not in ('JPEG', 'PNG', 'WEBP') or im.width*im.height>20_000_000:
                raise ValueError('invalid image')
            im.load()
            im = ImageOps.exif_transpose(im)
            im.thumbnail((1200,1200))
            out = io.BytesIO()
            im.convert('RGB').save(out, format='JPEG', quality=80)
            data = out.getvalue()
    except Exception:
        raise HTTPException(422, '无法读取图片，请选择清晰的照片') from None
    digest = hashlib.sha256(data).hexdigest()
    asset = s.scalar(select(MediaAsset).where(MediaAsset.user_id==u.id, MediaAsset.digest==digest))
    if asset: return asset
    asset = MediaAsset(id=str(uuid4()), user_id=u.id, digest=digest, content=data)
    s.add(asset)
    try: s.commit()
    except IntegrityError:
        s.rollback()
        asset = s.scalar(select(MediaAsset).where(MediaAsset.user_id==u.id, MediaAsset.digest==digest))
    return asset

@router.post('/media')
async def upload(file: UploadFile=File(...), u=Depends(user), s=Depends(db)):
    asset = await save_upload(file,s,u)
    return {'id':asset.id, 'url':'/api/v1/media/'+asset.id, 'source':'user-upload'}

@router.get('/media/{image_id}')
def get_image(image_id: str, u=Depends(user), s=Depends(db)):
    return Response(owned_image(s,u,image_id).content, media_type='image/jpeg')

@router.delete('/media/{image_id}')
def delete_image(image_id: str, u=Depends(user), s=Depends(db)):
    from .db import CatalogFood, Record
    asset=owned_image(s,u,image_id)
    for row in s.scalars(select(CatalogFood).where(CatalogFood.user_id==u.id)):
        if row.data.get('image_id')==image_id:
            row.data={**row.data, 'image_id':None}
    for row in s.scalars(select(Record).where(Record.user_id==u.id, Record.kind.in_(['chat','vision']))):
        if row.data.get('image_id')==image_id:
            row.data={**row.data,'image_id':None}
    s.delete(asset);s.commit()
    return {'ok':True}
