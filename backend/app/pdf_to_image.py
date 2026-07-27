"""PDF를 페이지별 이미지로 변환한다. (CLOVA OCR은 이미지만 입력받으므로 필요한 전처리)

의존성:
- pip install pdf2image
- poppler 설치 필요 (Mac: brew install poppler / Windows: 별도 설치)
"""

from pathlib import Path
from pdf2image import convert_from_path


def pdf_to_images(pdf_path: str, output_dir: str, dpi: int = 200) -> list[dict]:
    """PDF를 페이지별 PNG로 저장하고 페이지 정보 리스트를 반환한다.

    주의: 파일명이 page_1.png, page_2.png ... 로 고정이므로 output_dir은
    "문서 한 건당 하나"여야 한다. 여러 요청이 같은 폴더를 공유하면 서로의
    페이지 이미지를 덮어써서 다른 문서의 내용이 섞인다.
    호출자(analyze_document)가 analysis_id별 폴더를 만들어 넘긴다.
    """
    # 출력 폴더 없으면 생성
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # PDF -> 페이지 수만큼의 이미지 리스트로 변환
    pil_images = convert_from_path(pdf_path, dpi=dpi)

    results = []
    for page_number, image in enumerate(pil_images, start=1):
        save_path = output_path / f"page_{page_number}.png"
        image.save(save_path, "PNG")
        width, height = image.size

        results.append({
            "page": page_number,
            "image_path": str(save_path),
            "width": width,
            "height": height,
        })
        print(f"[완료] {page_number}페이지 -> {save_path} ({width}x{height})")

    return results


if __name__ == "__main__":
    pages_info = pdf_to_images("contract.pdf", "output_images", dpi=200)
    print("\n=== 변환 결과 요약 ===")
    for info in pages_info:
        print(info)