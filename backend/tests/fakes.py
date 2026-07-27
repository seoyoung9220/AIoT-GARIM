"""테스트용 가짜 외부 의존.

CLOVA OCR / HCX LLM / pdf2image(poppler)만 대체하고, 나머지(정규식 탐지, bbox 매칭,
마스킹 렌더링)는 실제 코드를 그대로 태운다.

핵심 장치: 페이지마다 고유한 색으로 칠한 이미지를 만들고, OCR 스텁이 그 색을 읽어
"어느 문서의 몇 페이지인지" 판별한다. 그래서 페이지 이미지가 서로 덮어써지면
OCR 결과가 다른 문서 내용으로 나오고 테스트가 반드시 깨진다.
"""

import types
from pathlib import Path

from PIL import Image

from app.schemas import DetectedItem

PAGE_W, PAGE_H = 1200, 1700

# 문서별 페이지 내용. CLOVA가 단어 단위로 쪼개 주는 것을 흉내내기 위해
# 전화번호는 "010" / "-" / "1234" 처럼 여러 조각으로 나눠 둔다.
DOCS = {
    "A": [
        [
            ["임대차", "계약서"],
            ["성명", "김민수"],
            ["연락처", "010", "-", "1234", "-", "5678"],
            ["주소", "서울특별시", "강남구", "테헤란로", "123"],
            ["주민등록번호", "900101-1234567"],
        ],
        [
            ["사업자등록번호", "123-45-67890"],
            ["대표자", "박지훈"],
            ["전화", "02-555-1234"],
        ],
    ],
    "B": [
        [
            ["용역", "계약서"],
            ["성명", "이서연"],
            ["연락처", "010", "-", "9876", "-", "5432"],
            ["주소", "부산광역시", "해운대구", "센텀중앙로", "99"],
            ["주민등록번호", "880505-2345678"],
        ],
        [
            ["사업자등록번호", "987-65-43210"],
            ["대표자", "최유진"],
            ["전화", "031-777-8888"],
        ],
    ],
}

# LLM이 찾아준다고 가정하는 이름/주소. 문서별로 값이 겹치지 않게 두어,
# 응답에 다른 문서 값이 섞이면 바로 드러나게 한다.
LLM_ITEMS = {
    "A": [("name", "김민수"), ("address", "서울특별시 강남구 테헤란로 123"), ("name", "박지훈")],
    "B": [("name", "이서연"), ("address", "부산광역시 해운대구 센텀중앙로 99"), ("name", "최유진")],
}

# 정규식 + LLM으로 문서당 탐지되어야 하는 전체 목록
EXPECTED = {
    "A": {("phone", "010-1234-5678"), ("resident_no", "900101-1234567"),
          ("business_no", "123-45-67890"), ("phone", "02-555-1234"),
          ("name", "김민수"), ("name", "박지훈"),
          ("address", "서울특별시 강남구 테헤란로 123")},
    "B": {("phone", "010-9876-5432"), ("resident_no", "880505-2345678"),
          ("business_no", "987-65-43210"), ("phone", "031-777-8888"),
          ("name", "이서연"), ("name", "최유진"),
          ("address", "부산광역시 해운대구 센텀중앙로 99")},
}

_DOC_INDEX = {doc: i for i, doc in enumerate(DOCS)}

# 두 렌더/분석을 같은 시점에 저장 단계로 밀어넣고 싶을 때 테스트가 채운다
barrier = None


def color_of(doc: str, page_no: int) -> tuple[int, int, int]:
    return (11 + _DOC_INDEX[doc] * 37, 23 + page_no * 41, 200)


_COLOR_TO_DOC = {color_of(doc, p): (doc, p)
                 for doc, pages in DOCS.items()
                 for p in range(1, len(pages) + 1)}


def page_image(doc: str, page_no: int) -> Image.Image:
    return Image.new("RGB", (PAGE_W, PAGE_H), color_of(doc, page_no))


def doc_of_image(image_path) -> tuple[str, int]:
    color = Image.open(image_path).convert("RGB").getpixel((0, 0))
    if color not in _COLOR_TO_DOC:
        raise AssertionError(f"알 수 없는 페이지 이미지: {image_path} (color={color})")
    return _COLOR_TO_DOC[color]


def doc_of_path(file_path) -> str:
    """'A.pdf' 와 업로드된 '<uuid>_A.pdf' 를 모두 'A'로 읽는다."""
    return Path(file_path).stem.rsplit("_", 1)[-1]


def fake_convert_from_path(pdf_path, dpi=200):
    doc = doc_of_path(pdf_path)
    images = [page_image(doc, i + 1) for i in range(len(DOCS[doc]))]
    if barrier is not None:
        barrier.wait()
    return images


def fake_call_clova_ocr(image_path):
    """페이지 이미지 색을 보고 그 문서/페이지의 CLOVA 응답 형태를 만들어 준다."""
    doc, page_no = doc_of_image(image_path)

    fields, y = [], 100
    for line in DOCS[doc][page_no - 1]:
        x = 100
        for word in line:
            w = 26 * len(word) + 14
            fields.append({
                "inferText": word,
                "boundingPoly": {"vertices": [
                    {"x": float(x), "y": float(y)},
                    {"x": float(x + w), "y": float(y)},
                    {"x": float(x + w), "y": float(y + 44)},
                    {"x": float(x), "y": float(y + 44)},
                ]},
            })
            x += w + 18
        y += 90

    return {"images": [{
        "inferResult": "SUCCESS",
        "convertedImageInfo": {"width": PAGE_W, "height": PAGE_H},
        "fields": fields,
    }]}


class FakeLLM:
    """이름/주소만 값으로 돌려준다 (실제 LLM처럼 bbox는 비워서 준다)."""

    def detect_pii_llm(self, page_text: str) -> list[DetectedItem]:
        norm = "".join(page_text.split())
        for doc, entries in LLM_ITEMS.items():
            hits = [(t, v) for t, v in entries if "".join(v.split()) in norm]
            if hits:
                return [
                    DetectedItem(id=f"llm-{doc}-{v}", type=t, value=v,
                                 page=1, bbox=[], source="llm")
                    for t, v in hits
                ]
        return []


def install():
    """poppler 없이 돌아가도록 가짜 pdf2image 모듈을 심는다.

    app.pdf_to_image 가 import 되기 전에 호출해야 한다.
    """
    import sys

    module = types.ModuleType("pdf2image")
    module.convert_from_path = fake_convert_from_path
    sys.modules["pdf2image"] = module
