"""OCR 결과(OcrPage)에서 개인정보 후보를 정규식으로 찾아 DetectedItem 리스트로 만든다."""

import re
import uuid

from schemas import OcrPage, DetectedItem

# 값 형태로 바로 판별 가능한 것들 (문맥 없이 패턴만으로 탐지)
PATTERNS = {
    "phone": re.compile(r"01[016789]-\d{3,4}-\d{4}"),
    "business_no": re.compile(r"\d{3}-\d{2}-\d{5}"),
    "resident_no": re.compile(r"\d{6}-\d{7}"),
}


def detect_pii(ocr_page: OcrPage) -> list[DetectedItem]:
    items = []

    for field in ocr_page.fields:
        for pii_type, pattern in PATTERNS.items():
            match = pattern.search(field.text)
            if not match:
                continue

            items.append(DetectedItem(
                id=str(uuid.uuid4()),
                type=pii_type,
                value=match.group(),
                page=ocr_page.page,
                bbox=field.bbox,
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