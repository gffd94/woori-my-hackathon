"""SPEC 2.5·2.11에 정의된 값 목록

DB에는 문자열과 CHECK 제약으로 저장하고, 코드에서는 이 Enum으로 비교한다.
entities의 kind·classification은 ERD 확정 후 추가한다.
"""

from enum import Enum


class CaseStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class Category(str, Enum):
    FINANCE = "finance"
    DELIVERY = "delivery"
    PUBLIC_AGENCY = "public_agency"
    JOB = "job"
    OTHER = "other"
