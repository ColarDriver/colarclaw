from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


def _utc_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


class SessionModel(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"s_{uuid.uuid4().hex}")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at_ms: Mapped[int] = mapped_column(BigInteger, default=_utc_ms)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger, default=_utc_ms)

    messages: Mapped[list["MessageModel"]] = relationship(back_populates="session", cascade="all,delete-orphan")


class MessageModel(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"m_{uuid.uuid4().hex}")
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_ms: Mapped[int] = mapped_column(BigInteger, default=_utc_ms)

    session: Mapped[SessionModel] = relationship(back_populates="messages")


class ToolRunModel(Base):
    __tablename__ = "tool_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"t_{uuid.uuid4().hex}")
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    args_json: Mapped[str] = mapped_column(Text, default="{}")
    result_text: Mapped[str] = mapped_column(Text, default="")
    created_at_ms: Mapped[int] = mapped_column(BigInteger, default=_utc_ms)


class GraphRunModel(Base):
    __tablename__ = "graph_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"g_{uuid.uuid4().hex}")
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    input_text: Mapped[str] = mapped_column(Text, default="")
    output_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="completed")
    created_at_ms: Mapped[int] = mapped_column(BigInteger, default=_utc_ms)
