"""OCR 결과(OcrPage)에서 개인정보 후보를 정규식으로 찾아 DetectedItem 리스트로 만든다.

CLOVA OCR은 텍스트를 단어 단위로 쪼개서 반환하기 때문에, 전화번호처럼 하이픈/공백을
포함한 값이 여러 필드로 나뉘어 올 수 있다. 그래서 필드 하나하나가 아니라
"같은 줄(라인)"로 묶은 뒤 그 줄 전체 문자열에 대해 정규식을 돌린다.
"""

import re
import uuid

from schemas import OcrPage, DetectedItem

# 하이픈(-)뿐 아니라 공백으로 구분된 경우도 잡도록 [-\s] 사용
PATTERNS = {
    "phone": re.compile(r"01[016789][-\s]\d{3,4}[-\s]\d{4}"),
    "business_no": re.compile(r"\d{3}[-\s]\d{2}[-\s]\d{5}"),
    "resident_no": re.compile(r"\d{6}[-\s]\d{7}"),
}


def _group_into_lines(fields):
    """bbox의 y좌표가 겹치는 필드끼리 같은 줄로 묶는다."""
    by_y = sorted(fields, key=lambda f: (f.bbox[1] + f.bbox[3]) / 2)
    lines = []
    for f in by_y:
        fy1, fy2 = f.bbox[1], f.bbox[3]
        placed = False
        for line in lines:
            ly1, ly2 = line["y1"], line["y2"]
            overlap = min(fy2, ly2) - max(fy1, ly1)
            min_height = min(fy2 - fy1, ly2 - ly1) or 1
            if overlap / min_height > 0.5:
                line["fields"].append(f)
                line["y1"] = min(ly1, fy1)
                line["y2"] = max(ly2, fy2)
                placed = True
                break
        if not placed:
            lines.append({"y1": fy1, "y2": fy2, "fields": [f]})

    for line in lines:
        line["fields"].sort(key=lambda f: f.bbox[0])  # 왼쪽 -> 오른쪽 순서로 정렬
    lines.sort(key=lambda l: l["y1"])
    return lines


def _build_line_text(line_fields):
    """줄 안의 필드들을 이어붙인 문자열과, 각 필드가 차지하는 문자 구간을 함께 만든다."""
    text = ""
    spans = []  # (start, end, field)
    for f in line_fields:
        start = len(text)
        text += f.text
        end = len(text)
        spans.append((start, end, f))
        text += " "
    return text, spans


def _bbox_union(fields):
    x1 = min(f.bbox[0] for f in fields)
    y1 = min(f.bbox[1] for f in fields)
    x2 = max(f.bbox[2] for f in fields)
    y2 = max(f.bbox[3] for f in fields)
    return [x1, y1, x2, y2]


def detect_pii(ocr_page: OcrPage) -> list[DetectedItem]:
    items = []
    lines = _group_into_lines(ocr_page.fields)

    for line in lines:
        text, spans = _build_line_text(line["fields"])

        for pii_type, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                m_start, m_end = match.start(), match.end()
                # 매칭된 구간(m_start~m_end)에 걸쳐있는 필드들만 모은다
                covering_fields = [
                    f for (s, e, f) in spans if s < m_end and e > m_start
                ]
                if not covering_fields:
                    continue

                items.append(DetectedItem(
                    id=str(uuid.uuid4()),
                    type=pii_type,
                    value=match.group(),
                    page=ocr_page.page,
                    bbox=_bbox_union(covering_fields),
                    source="regex",
                ))

    return items


if __name__ == "__main__":
    from PIL import Image
    from ocr import run_ocr_on_image

    image_path = "contract.jpg"
    width, height = Image.open(image_path).size

    ocr_page = run_ocr_on_image(image_path, page=1, width=width, height=height)
    detected = detect_pii(ocr_page)

    print(f"탐지된 개인정보 후보: {len(detected)}건")
    for item in detected:
        print(f" - [{item.type}] {item.value}  (bbox: {item.bbox})")