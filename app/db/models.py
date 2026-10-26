"""수집과 판정이 공유하는 PostgreSQL 모델.

임베딩 모델과 차원은 아직 미정이므로 ``Vector()``에 차원을 고정하지 않는다.
실제 적재·검색 전에 수집 담당자와 모델·차원을 합의해야 한다.
이 모듈은 연결이나 테이블 생성을 수행하지 않는다.
"""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    REAL,
    SmallInteger,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """마이그레이션에서 사용하는 공통 메타데이터."""


pattern_sources = Table(
    "pattern_sources",
    Base.metadata,
    Column("pattern_id", BigInteger, ForeignKey("patterns.id"), primary_key=True),
    Column(
        "source_id", BigInteger, ForeignKey("sources.id"), primary_key=True, index=True
    ),
)

pattern_indicators = Table(
    "pattern_indicators",
    Base.metadata,
    Column("pattern_id", BigInteger, ForeignKey("patterns.id"), primary_key=True),
    Column(
        "indicator_id",
        BigInteger,
        ForeignKey("indicators.id"),
        primary_key=True,
        index=True,
    ),
)


class Pattern(Base):
    """설명과 대표 예시를 묶어서 검색하는 수법 카드."""

    __tablename__ = "patterns"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    impersonation: Mapped[str | None] = mapped_column(Text)
    lure_action: Mapped[str | None] = mapped_column(Text)
    triggers: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(ARRAY(Text)),
        default=list,
        server_default=text("'{}'::text[]"),
    )
    example_messages: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(ARRAY(Text)),
        default=list,
        server_default=text("'{}'::text[]"),
    )
    # 단계와 산정 기준이 미정이므로 임의의 범위나 기본값을 부여하지 않는다.
    risk_level: Mapped[int | None] = mapped_column(SmallInteger)
    embedding: Mapped[list[float] | None] = mapped_column(Vector())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sources: Mapped[list[Source]] = relationship(
        secondary=pattern_sources, back_populates="patterns"
    )
    indicators: Mapped[list[Indicator]] = relationship(
        secondary=pattern_indicators, back_populates="patterns"
    )


class Source(Base):
    """수법을 확인한 기사 출처. 한 기사를 여러 수법이 공유할 수 있다."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, unique=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    patterns: Mapped[list[Pattern]] = relationship(
        secondary=pattern_sources, back_populates="sources"
    )


class Indicator(Base):
    """정규화된 악성 단서. 기사 출처와 직접 연결하지 않는다."""

    __tablename__ = "indicators"
    __table_args__ = (
        UniqueConstraint("type", "value_normalized", name="uq_indicators_type_value"),
        CheckConstraint(
            "type IN ('domain', 'url', 'phone', 'app_name')",
            name="ck_indicators_type",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    type: Mapped[str] = mapped_column(Text)
    value_normalized: Mapped[str] = mapped_column(Text)

    patterns: Mapped[list[Pattern]] = relationship(
        secondary=pattern_indicators, back_populates="indicators"
    )


class OfficialLink(Base):
    """팀이 확인한 공식 주소. 문자 전체의 안전 판정을 뜻하지 않는다."""

    __tablename__ = "official_links"
    __table_args__ = (
        UniqueConstraint("type", "value_normalized", name="uq_official_links_type_value"),
        CheckConstraint("type IN ('domain', 'url')", name="ck_official_links_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    type: Mapped[str] = mapped_column(Text)
    value_normalized: Mapped[str] = mapped_column(Text)
    institution: Mapped[str] = mapped_column(Text)
    verification_reference: Mapped[str] = mapped_column(Text)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VerdictLog(Base):
    """판정 기록. 입력 문자와 reasoning의 마스킹은 저장 호출자가 수행한다.

    근거 ID 배열은 검색 결과의 기록이며 외래 키로 강제되지 않는다.
    score의 산정 기준은 판정 담당자와 합의하며, 없을 때 0으로 대체하지 않는다.
    """

    __tablename__ = "verdict_logs"
    __table_args__ = (
        CheckConstraint("verdict IN ('RISK', 'SAFE', 'UNKNOWN')", name="ck_verdict_logs_verdict"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    message_masked: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(Text)
    score: Mapped[float | None] = mapped_column(REAL)
    matched_pattern_ids: Mapped[list[int]] = mapped_column(
        MutableList.as_mutable(ARRAY(BigInteger)),
        default=list,
        server_default=text("'{}'::bigint[]"),
    )
    matched_indicator_ids: Mapped[list[int]] = mapped_column(
        MutableList.as_mutable(ARRAY(BigInteger)),
        default=list,
        server_default=text("'{}'::bigint[]"),
    )
    reasoning: Mapped[str] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
