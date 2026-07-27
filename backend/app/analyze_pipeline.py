"""OCR 파이프라인 전체를 하나로 묶는 진입점.
백엔드는 이 파일의 analyze_document() 함수 하나만 호출하면 된다.
"""

import uuid
from pathlib import Path

from pdf_to_image import pdf_to_images
from ocr import run_ocr_on_image
from detect import detect_pii
from schemas import AnalyzeResponse


def analyze_document(file_path: str, output_dir: str = "output_images") -> AnalyzeResponse:
    """PDF 또는 이미지 파일 경로를 받아 AnalyzeResponse를 반환한다."""

    ext = Path(file_path).suffix.lower()

    if ext == ".pdf":
        pages_info = pdf_to_images(file_path, output_dir)
    else:
        from PIL import Image
        width, height = Image.open(file_path).size
        pages_info = [{"page": 1, "image_path": file_path, "width": width, "height": height}]

    ocr_pages = []
    all_items = []

    for info in pages_info:
        ocr_page = run_ocr_on_image(info["image_path"], info["page"], info["width"], info["height"])
        ocr_pages.append(ocr_page)
        all_items.extend(detect_pii(ocr_page))

    return AnalyzeResponse(
        analysis_id=str(uuid.uuid4()),
        filename=Path(file_path).name,
        page_count=len(ocr_pages),
        items=all_items,
        pages=ocr_pages,
    )


def analyze_images(image_paths: list[str], filename: str = "contract") -> AnalyzeResponse:
    """이미지 여러 장을 "한 문서의 여러 페이지"로 취급해서 분석한다.
    예: page1.jpg, page2.jpg 두 장을 캡처해둔 경우 이 함수를 쓴다.
    """
    from PIL import Image

    ocr_pages = []
    all_items = []

    for page_number, image_path in enumerate(image_paths, start=1):
        width, height = Image.open(image_path).size
        ocr_page = run_ocr_on_image(image_path, page=page_number, width=width, height=height)
        ocr_pages.append(ocr_page)
        all_items.extend(detect_pii(ocr_page))
        print(f"[완료] {page_number}페이지({image_path}): 탐지 {len(detect_pii(ocr_page))}건")

    return AnalyzeResponse(
        analysis_id=str(uuid.uuid4()),
        filename=filename,
        page_count=len(ocr_pages),
        items=all_items,
        pages=ocr_pages,
    )


if __name__ == "__main__":
    result = analyze_images(["contract.jpg", "contract2.jpg"])
    print(f"\n총 페이지: {result.page_count}, 총 탐지 건수: {len(result.items)}")
    for item in result.items:
        print(f" - [{item.type}] {item.value}  (page {item.page}, bbox: {item.bbox})")