"""Speech-to-Text service: FastAPI + SQLAlchemy.

Speech is captured in the browser (Web Speech API, streams interim results).
The server stores, lists, edits and deletes transcriptions.

Endpoints
---------
GET    /                              web app (recorder + history dashboard)
GET    /api/health
GET    /api/transcriptions?q=&limit=&offset=
POST   /api/transcriptions            {text, language}
GET    /api/transcriptions/{id}
PUT    /api/transcriptions/{id}       {text?, language?}
DELETE /api/transcriptions/{id}
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import DateTime, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
STATIC_DIR = BASE_DIR / "static"
MAX_TEXT_LENGTH = 10_000
LANGUAGE_PATTERN = r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$"  # BCP-47 style, e.g. hi-IN, en-US


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'transcriptions.db'}")
    # Hosts such as Render and Heroku hand out "postgres://" URLs, which SQLAlchemy 2 rejects.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix):]
    return url


DATABASE_URL = _database_url()
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Transcription(Base):
    __tablename__ = "transcriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(40), nullable=False, default="hi-IN")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


# ---------- Schemas ----------

def _strip_or_reject(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value


class TranscriptionCreate(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)
    language: str = Field(default="hi-IN", min_length=2, max_length=40, pattern=LANGUAGE_PATTERN)

    @field_validator("text")
    @classmethod
    def _check_text(cls, v: str) -> str:
        return _strip_or_reject(v)  # type: ignore[return-value]


class TranscriptionUpdate(BaseModel):
    text: Optional[str] = Field(default=None, min_length=1, max_length=MAX_TEXT_LENGTH)
    language: Optional[str] = Field(default=None, min_length=2, max_length=40, pattern=LANGUAGE_PATTERN)

    @field_validator("text")
    @classmethod
    def _check_text(cls, v: Optional[str]) -> Optional[str]:
        return _strip_or_reject(v)


class TranscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    language: str
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def _as_utc(cls, v: datetime) -> datetime:
        # SQLite returns naive datetimes; they were written in UTC.
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


# ---------- App ----------

@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Speech to Text", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_or_404(db: Session, transcription_id: int) -> Transcription:
    row = db.get(Transcription, transcription_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Transcription not found")
    return row


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/transcriptions", response_model=list[TranscriptionOut])
def list_transcriptions(
    q: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(Transcription)
    if q:
        # autoescape keeps user-supplied % and _ from acting as wildcards.
        stmt = stmt.where(
            func.lower(Transcription.text).contains(q.lower(), autoescape=True)
            | func.lower(Transcription.language).contains(q.lower(), autoescape=True)
        )
    stmt = stmt.order_by(Transcription.id.desc()).limit(limit).offset(offset)
    return db.scalars(stmt).all()


@app.post(
    "/api/transcriptions",
    response_model=TranscriptionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_transcription(payload: TranscriptionCreate, db: Session = Depends(get_db)):
    row = Transcription(text=payload.text, language=payload.language)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.get("/api/transcriptions/{transcription_id}", response_model=TranscriptionOut)
def get_transcription(transcription_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, transcription_id)


@app.put("/api/transcriptions/{transcription_id}", response_model=TranscriptionOut)
def update_transcription(
    transcription_id: int,
    payload: TranscriptionUpdate,
    db: Session = Depends(get_db),
):
    row = _get_or_404(db, transcription_id)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


@app.delete("/api/transcriptions/{transcription_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transcription(transcription_id: int, db: Session = Depends(get_db)):
    row = _get_or_404(db, transcription_id)
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
