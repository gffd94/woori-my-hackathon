"""팀 ERD에 맞춘 지식 관계와 PostgreSQL 스키마 계약을 확인한다."""

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable


def test_수법은_대표예시를_보관하고_여러_수법이_출처를_공유한다():
    from app.db.models import Pattern, Source

    article = Source(
        site="boho_security_notice", post_id="1001",
        title="가상 택배 사칭 사례", url="https://notice.example/1001",
    )
    other_article = Source(
        site="boho_security_notice", post_id="1002",
        title="가상 기관 사칭 사례", url="https://notice.example/1002",
    )
    example = {"text": "[가상 택배] 배송 주소를 확인해 주세요.", "type": "sms", "source_post_id": "1001"}
    delivery = Pattern(
        name="택배 주소 정정 사칭",
        summary="주소 확인을 핑계로 정보 입력을 유도한다.",
        example_messages=[example],
        sources=[article, other_article],
    )
    institution = Pattern(
        name="공공기관 사칭",
        summary="가상 기관을 사칭해 정보 입력을 유도한다.",
        sources=[article],
    )

    assert delivery.example_messages == [example]
    assert set(article.patterns) == {delivery, institution}
    assert set(delivery.sources) == {article, other_article}


def test_IOC는_수법과_독립적으로_존재하고_공식주소와_분리된다():
    from app.db.models import Indicator, OfficialLink, Pattern

    indicator = Indicator(type="domain", value_normalized="malicious.example")
    assert "patterns" not in Indicator.__mapper__.relationships
    assert "indicators" not in Pattern.__mapper__.relationships

    official = OfficialLink(domain="official.example", organization="가상 은행", category="bank")

    assert indicator.value_normalized == "malicious.example"
    assert OfficialLink.__table__.name == "official_links"
    assert official.domain == "official.example"
    assert official.verification_reference is None
    assert official.verified_at is None


def test_PostgreSQL_스키마는_ERD의_6개_테이블과_수법기반_판정기록을_생성한다():
    from app.db.models import Base

    assert set(Base.metadata.tables) == {
        "patterns", "sources", "indicators", "official_links", "verdict_logs", "pattern_sources",
    }
    ddl = {
        name: str(CreateTable(table).compile(dialect=postgresql.dialect()))
        for name, table in Base.metadata.tables.items()
    }
    assert "embedding VECTOR" in ddl["patterns"]
    assert "triggers TEXT[]" in ddl["patterns"]
    assert "example_messages JSONB" in ddl["patterns"]
    assert "is_active BOOLEAN DEFAULT true NOT NULL" in ddl["patterns"]
    for removed in ("risk_level", "first_seen_at", "last_seen_at", "review_status"):
        assert removed not in ddl["patterns"]
    assert "PRIMARY KEY (pattern_id, source_id)" in ddl["pattern_sources"]
    assert "FOREIGN KEY(source_id) REFERENCES sources (id)" in ddl["pattern_sources"]
    assert "UNIQUE (site, post_id)" in ddl["sources"]
    assert "posted_date DATE" in ddl["sources"]
    assert "attachments JSONB" in ddl["sources"]
    assert "UNIQUE (type, value_normalized)" in ddl["indicators"]
    assert "type IN ('domain', 'url', 'phone', 'app_name')" in ddl["indicators"]
    assert "UNIQUE (domain)" in ddl["official_links"]
    assert "verified_at TIMESTAMP WITH TIME ZONE NOT NULL" not in ddl["official_links"]
    assert "matched_pattern_ids BIGINT[]" in ddl["verdict_logs"]
    assert "matched_indicator_ids BIGINT[]" in ddl["verdict_logs"]
    assert "verdict IN ('RISK', 'SAFE', 'UNKNOWN')" in ddl["verdict_logs"]
    assert "created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in ddl["verdict_logs"]
    assert "matched_example_ids" not in ddl["verdict_logs"]
    assert "user_feedback" not in ddl["verdict_logs"]
