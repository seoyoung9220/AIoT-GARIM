"""OCR 파이프라인 전체를 하나로 묶는 진입점.
백엔드는 이 파일의 analyze_document() 함수 하나만 호출하면 된다.
"""

import sys
import uuid
from pathlib import Path

# LLM/, rag/ 폴더는 backend/ 밖에 있어서, 서버의 PYTHONPATH 설정과 무관하게
# 항상 import가 되도록 프로젝트 루트를 직접 sys.path에 추가한다.
# (파일 위치: backend/app/analyze_pipeline.py -> 부모의 부모의 부모 = 프로젝트 루트)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.pdf_to_image import pdf_to_images
from app.ocr import run_ocr_on_image
from app.detect import detect_pii
from app.bbox_matcher import find_bbox
from app.schemas import AnalyzeResponse, DetectedItem

try:
    from LLM.llm_client import ClovaClient
    _llm_client = ClovaClient()
except Exception as e:  # noqa: BLE001
    # LLM 모듈이 아직 준비 안 됐거나 키가 없어도, 정규식 탐지만으로는 서비스가 죽지 않게 한다.
    print(f"[경고] LLM 모듈 로드 실패, 이름/주소 탐지는 건너뜁니다: {e}")
    _llm_client = None


def _detect_llm_items(ocr_page) -> list[DetectedItem]:
    """LLM으로 이름/주소를 탐지하고, bbox_matcher로 실제 좌표를 채워 넣는다."""
    if _llm_client is None:
        return []

    page_text = " ".join(f.text for f in ocr_page.fields)

    try:
        raw_items = _llm_client.detect_pii_llm(page_text)
    except Exception as e:  # noqa: BLE001
        print(f"[경고] LLM 탐지 호출 실패, 이 페이지는 이름/주소 없이 진행합니다: {e}")
        return []

    used = set()
    filled = []
    for raw in raw_items:
        bbox, used = find_bbox(raw.value, ocr_page, used)
        if bbox is None:
            print(f"[bbox 매칭 실패] {raw.type}={raw.value} (건너뜀)")
            continue
        raw.bbox = bbox
        raw.page = ocr_page.page
        # LLM이 스스로 매긴 id(예: "1","2")는 페이지마다 다시 1부터 매겨져서
        # 서로 다른 항목끼리 같은 id를 갖는 충돌이 생긴다. 신뢰하지 않고 새로 발급한다.
        raw.id = str(uuid.uuid4())
        filled.append(raw)

    return filled


def _detect_all(ocr_page) -> list[DetectedItem]:
    """정규식(전화번호/사업자번호/주민번호) + LLM(이름/주소) 탐지 결과를 합친다."""
    items = detect_pii(ocr_page)
    items.extend(_detect_llm_items(ocr_page))
    return items


def analyze_document(file_path: str, output_dir: str = "output_images") -> AnalyzeResponse:
    """PDF 또는 이미지 파일 경로를 받아 AnalyzeResponse를 반환한다."""

    ext = Path(file_path).suffix.lower()

    if ext == ".pdf":
        pages_info = pdf_to_images(file_path, output_dir)
    else:
        # 이미지 파일 하나짜리 문서는 1페이지로 취급
        from PIL import Image
        width, height = Image.open(file_path).size
        pages_info = [{"page": 1, "image_path": file_path, "width": width, "height": height}]

    ocr_pages = []
    all_items = []

    for info in pages_info:
        ocr_page = run_ocr_on_image(info["image_path"], info["page"], info["width"], info["height"])
        ocr_pages.append(ocr_page)
        all_items.extend(_detect_all(ocr_page))

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
        detected = _detect_all(ocr_page)
        all_items.extend(detected)
        print(f"[완료] {page_number}페이지({image_path}): 탐지 {len(detected)}건")

    return AnalyzeResponse(
        analysis_id=str(uuid.uuid4()),
        filename=filename,
        page_count=len(ocr_pages),
        items=all_items,
        pages=ocr_pages,
    )


if __name__ == "__main__":
    result = analyze_images(["app/contract.jpg", "app/contract2.jpg"])
    print(f"\n총 페이지: {result.page_count}, 총 탐지 건수: {len(result.items)}")
    for item in result.items:
        print(f" - [{item.type}] {item.value}  (page {item.page}, bbox: {item.bbox}, source: {item.source})")