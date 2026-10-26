"""합의한 지식 관계와 PostgreSQL 스키마 계약을 확인한다."""

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable


def test_수법은_대표예시를_보관하고_여러_수법이_기사를_공유한다():
    from app.db.models import Pattern, Source

    article = Source(title="가상 택배 사칭 사례", url="https://news.example/case-1")
    other_article = Source(title="가상 기관 사칭 사례", url="https://news.example/case-2")
    delivery = Pattern(
        name="택배 주소 정정 사칭",
        summary="주소 확인을 핑계로 정보 입력을 유도한다.",
        example_messages=["[가상 택배] 배송 주소를 확인해 주세요."],
        sources=[article, other_article],
    )
    institution = Pattern(
        name="공공기관 사칭",
        summary="가상 기관을 사칭해 정보 입력을 유도한다.",
        sources=[article],
    )

    assert delivery.example_messages == ["[가상 택배] 배송 주소를 확인해 주세요."]
    assert set(article.patterns) == {delivery, institution}
    assert set(delivery.sources) == {article, other_article}


def test_IOC는_수법없이_존재하거나_여러_수법에_연결되고_공식주소와_분리된다():
    from app.db.models import Indicator, OfficialLink, Pattern

    indicator = Indicator(type="domain", value_normalized="malicious.example")
    assert indicator.patterns == []

    delivery = Pattern(name="택배 사칭", summary="배송 확인으로 정보 입력 유도")
    bank = Pattern(name="금융사 사칭", summary="계정 확인으로 정보 입력 유도")
    indicator.patterns.extend([delivery, bank])
    official = OfficialLink(
        type="domain",
        value_normalized="official.example",
        institution="가상 은행",
        verification_reference="팀의 공식 기관 목록 확인",
    )

    assert delivery.indicators == [indicator]
    assert bank.indicators == [indicator]
    assert OfficialLink.__table__.name == "official_links"
    assert official.value_normalized == "official.example"


def test_PostgreSQL_스키마는_7개_테이블과_수법기반_판정기록을_생성한다():
    from app.db.models import Base

    assert set(Base.metadata.tables) == {
        "patterns", "sources", "indicators", "official_links", "verdict_logs",
        "pattern_sources", "pattern_indicators",
    }
    ddl = {
        name: str(CreateTable(table).compile(dialect=postgresql.dialect()))
        for name, table in Base.metadata.tables.items()
    }
    assert "embedding VECTOR" in ddl["patterns"]
    assert "example_messages TEXT[]" in ddl["patterns"]
    assert "is_active BOOLEAN DEFAULT true NOT NULL" in ddl["patterns"]
    assert "PRIMARY KEY (pattern_id, source_id)" in ddl["pattern_sources"]
    assert "FOREIGN KEY(source_id) REFERENCES sources (id)" in ddl["pattern_sources"]
    assert "PRIMARY KEY (pattern_id, indicator_id)" in ddl["pattern_indicators"]
    assert "FOREIGN KEY(indicator_id) REFERENCES indicators (id)" in ddl["pattern_indicators"]
    for name in ("indicators", "official_links"):
        assert "UNIQUE (type, value_normalized)" in ddl[name]
    assert "type IN ('domain', 'url')" in ddl["official_links"]
    assert "verified_at TIMESTAMP WITH TIME ZONE NOT NULL" in ddl["official_links"]
    assert "matched_pattern_ids BIGINT[]" in ddl["verdict_logs"]
    assert "matched_indicator_ids BIGINT[]" in ddl["verdict_logs"]
    assert "verdict IN ('RISK', 'SAFE', 'UNKNOWN')" in ddl["verdict_logs"]
    assert "created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in ddl["verdict_logs"]
    assert "review_status" not in ddl["patterns"]
    assert "matched_example_ids" not in ddl["verdict_logs"]
    assert "user_feedback" not in ddl["verdict_logs"]
