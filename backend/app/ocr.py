"""이미지를 CLOVA OCR로 인식하고, 결과를 schemas.OcrPage로 변환한다.
CLOVA 원본 응답 구조는 이 파일 밖으로 나가지 않는다 (detect/render는 OcrPage만 안다).

의존성: pip install requests python-dotenv pydantic pillow
"""

import json
import os
import time
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv

from app.schemas import OcrField, OcrPage

load_dotenv()
OCR_URL = os.getenv("OCR_INVOKE_URL")
OCR_SECRET = os.getenv("OCR_SECRET_KEY")


def call_clova_ocr(image_path: str) -> dict:
    if not OCR_URL or not OCR_SECRET:
        raise RuntimeError(".env에서 OCR_INVOKE_URL / OCR_SECRET_KEY를 못 찾았습니다.")

    image_format = Path(image_path).suffix.lstrip(".").lower()

    payload = {
        "version": "V2",
        "requestId": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "images": [{"format": image_format, "name": "contract"}],
    }
    headers = {"X-OCR-SECRET": OCR_SECRET}

    with open(image_path, "rb") as f:
        response = requests.post(
            OCR_URL,
            headers=headers,
            data={"message": json.dumps(payload)},
            files=[("file", f)],
            timeout=30,
        )

    if response.status_code != 200:
        raise RuntimeError(f"CLOVA OCR 호출 실패: {response.status_code} {response.text}")

    return response.json()


def _vertices_to_bbox(vertices: list[dict]) -> list[int]:
    # CLOVA는 꼭짓점 4개(소수점 좌표)를 준다 -> [x1, y1, x2, y2] 정수로 변환
    xs = [v["x"] for v in vertices]
    ys = [v["y"] for v in vertices]
    return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]


def _parse_clova_response(clova_json: dict, page: int, fallback_width: int, fallback_height: int) -> OcrPage:
    image_result = clova_json["images"][0]

    if image_result["inferResult"] != "SUCCESS":
        raise RuntimeError(f"OCR 인식 실패: {image_result.get('message')}")

    converted_info = image_result.get("convertedImageInfo", {})
    width = converted_info.get("width", fallback_width)
    height = converted_info.get("height", fallback_height)

    fields = [
        OcrField(text=f["inferText"], bbox=_vertices_to_bbox(f["boundingPoly"]["vertices"]))
        for f in image_result["fields"]
    ]

    return OcrPage(page=page, width=width, height=height, fields=fields)


def run_ocr_on_image(image_path: str, page: int, width: int, height: int) -> OcrPage:
    clova_json = call_clova_ocr(image_path)
    return _parse_clova_response(clova_json, page=page, fallback_width=width, fallback_height=height)


def run_ocr_on_pdf(pdf_path: str, image_output_dir: str) -> list[OcrPage]:
    from pdf_to_image import pdf_to_images

    pages_info = pdf_to_images(pdf_path, image_output_dir)

    ocr_pages = []
    for info in pages_info:
        ocr_page = run_ocr_on_image(info["image_path"], info["page"], info["width"], info["height"])
        ocr_pages.append(ocr_page)
        print(f"[OCR 완료] {info['page']}페이지: 텍스트 조각 {len(ocr_page.fields)}개 인식")

    return ocr_pages


if __name__ == "__main__":
    from PIL import Image

    image_path = "contract.jpg"
    width, height = Image.open(image_path).size  # 이미지 실제 크기를 자동으로 구함

    ocr_page = run_ocr_on_image(image_path, page=1, width=width, height=height)

    print(f"인식된 텍스트 조각 수: {len(ocr_page.fields)}")
    for field in ocr_page.fields:
        print(f" - {field.text}  (bbox: {field.bbox})")