import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, JSON, DateTime, ForeignKey, Float, LargeBinary, UniqueConstraint, inspect, text, select, update
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

def default_consents():
    return {'diet': True, 'health': True, 'external_ai': True}

class Base(DeclarativeBase): pass
class SchemaMigration(Base):
    __tablename__ = 'schema_migrations'
    version: Mapped[str] = mapped_column(String, primary_key=True)

class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True)
    password: Mapped[str] = mapped_column(String)
    token_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    token_expires: Mapped[float] = mapped_column(default=0)
    consents: Mapped[dict] = mapped_column(JSON, default=default_consents)
class CaptchaChallenge(Base):
    __tablename__ = 'captcha_challenges'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    answer_hash: Mapped[str] = mapped_column(String)
    binding_hash: Mapped[str] = mapped_column(String, index=True)
    expires_at: Mapped[float] = mapped_column(Float, index=True)

class Record(Base):
    __tablename__ = 'records'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    kind: Mapped[str] = mapped_column(String, index=True)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class MediaAsset(Base):
    __tablename__ = 'media_assets'
    __table_args__ = (UniqueConstraint('user_id', 'digest'),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    digest: Mapped[str] = mapped_column(String)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class CatalogFood(Base):
    __tablename__ = 'catalog_foods'
    __table_args__ = (UniqueConstraint('user_id', 'normalized_name'),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    normalized_name: Mapped[str] = mapped_column(String)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Conversation(Base):
    __tablename__ = 'conversations'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    title: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

url = os.getenv('DATABASE_URL', 'sqlite:///./lifeos.db')
engine = create_engine(url, connect_args={'check_same_thread': False} if url.startswith('sqlite') else {})
Session = sessionmaker(engine, expire_on_commit=False)
def db():
    with Session() as s: yield s


def initialize_schema(target_engine):
    """Upgrade v1 accounts in place before creating new tables. Preserve user IDs/data."""
    with target_engine.begin() as conn:
        if conn.dialect.name == 'postgresql':
            conn.execute(text('SELECT pg_advisory_xact_lock(71031003)'))
        inspector = inspect(conn)
        if 'users' in inspector.get_table_names():
            columns = {c['name'] for c in inspector.get_columns('users')}
            if 'email' in columns and 'username' not in columns:
                conn.execute(text('ALTER TABLE users RENAME COLUMN email TO username'))
        Base.metadata.create_all(conn)
        version = '003_default_consents_enabled'
        if not conn.execute(select(SchemaMigration.version).where(SchemaMigration.version == version)).scalar():
            conn.execute(update(User).values(consents=default_consents()))
            conn.execute(SchemaMigration.__table__.insert().values(version=version))
        version = '004_catalog_media_conversations'
        if not conn.execute(select(SchemaMigration.version).where(SchemaMigration.version == version)).scalar():
            from uuid import uuid5, NAMESPACE_URL
            chats = conn.execute(select(Record.__table__).where(Record.kind == 'chat')).mappings().all()
            grouped = {}
            for row in chats:
                cid = str(uuid5(NAMESPACE_URL, 'lifeos-legacy-chat:' + row['user_id']))
                grouped[row['user_id']] = cid
            for uid, cid in grouped.items():
                conn.execute(Conversation.__table__.insert().values(id=cid, user_id=uid, title='历史快捷对话'))
            for row in chats:
                conn.execute(update(Record).where(Record.id == row['id']).values(data={**row['data'], 'conversation_id': grouped[row['user_id']]}))
            conn.execute(SchemaMigration.__table__.insert().values(version=version))
