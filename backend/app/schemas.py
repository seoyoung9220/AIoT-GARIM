"""팀 공용 타입 계약 (Pydantic 모델).
모든 모듈(ocr/detect/rag/judge/render)의 입출력은 이 스키마를 따른다.
이 파일을 바꾸면 전 모듈에 영향이 가므로, 변경 시 팀 전체 합의 필요.
docs/api-spec.md 와 항상 일치해야 한다.
"""
from typing import Literal, Optional
from pydantic import BaseModel

PiiType = Literal["name", "phone", "address", "account", "business_no", "resident_no"]
Target = Literal["internal", "partner", "public"]
Action = Literal["keep", "partial", "remove"]
Source = Literal["regex", "llm"]


class HealthResponse(BaseModel):
    """헬스체크 응답. 배포 검증·모니터링이 이 형태를 파싱한다."""
    status: str
    service: str


class OcrField(BaseModel):
    """OCR로 읽은 텍스트 한 조각과 그 위치."""
    text: str
    bbox: list[int]  # [x1, y1, x2, y2] (픽셀 좌표, 좌상단 원점)


class OcrPage(BaseModel):
    """한 페이지의 OCR 결과.

    CLOVA OCR 응답(JSON)을 이 형태로 변환하는 책임은 ocr.py에 있다.
    detect/render는 OcrPage만 알고, CLOVA 응답 구조는 몰라야 한다.
    """
    page: int  # 1부터 시작
    width: int
    height: int
    fields: list[OcrField]


class DetectedItem(BaseModel):
    """탐지된 개인정보 항목 하나."""
    id: str
    type: PiiType
    value: str
    page: int
    bbox: list[int]  # [x1, y1, x2, y2]
    source: Source


class Basis(BaseModel):
    """마스킹 판단의 정책 근거 (RAG 검색 결과)."""
    doc: str  # 근거 문서명 (예: 개인정보보호법)
    clause: str  # 조항 (예: 제17조(개인정보의 제공))
    summary: str  # 근거 요약 한 줄


class MaskingPolicy(BaseModel):
    """항목 하나에 대한 마스킹 정책."""
    item_id: str
    action: Action
    masked_value: Optional[str] = None  # action == "partial"일 때만 값 존재
    basis: Basis


class AnalyzeResponse(BaseModel):
    analysis_id: str
    filename: str
    page_count: int
    items: list[DetectedItem]
    pages: list[OcrPage]  # 프론트 문서 미리보기(워크스페이스) 렌더링용


class MaskRequest(BaseModel):
    analysis_id: str
    target: Target
    exclude_ids: list[str] = []  # 사용자가 체크 해제해 마스킹 대상에서 제외한 항목 id


class MaskResponse(BaseModel):
    result_id: str
    target: Target
    policies: list[MaskingPolicy]
    summary: str  # 예: "public 기준 총 6건: partial 1건, remove 5건"