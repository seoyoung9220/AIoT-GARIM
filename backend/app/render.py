"""DetectedItem + MaskingPolicy를 받아서, 이미지 위에 실제로 마스킹을 그리고 PDF로 저장한다.

analyze_pipeline.analyze_document()가 반환하는 AnalyzeResponse에는 원본 페이지
"이미지 파일 경로"가 남아있지 않다 (OcrPage는 텍스트+좌표만 가짐). 그래서 이 파일은
분석 시점의 파일 경로를 별도로 다시 받아서, PDF든 단일 이미지든 그 시점과 똑같은
방식으로 페이지 이미지를 준비한 뒤 마스킹을 그린다.
"""

from pathlib import Path

from PIL import Image, ImageDraw

from app.schemas import DetectedItem, MaskingPolicy
from app.pdf_to_image import pdf_to_images


def _draw_mask(draw: ImageDraw.ImageDraw, item: DetectedItem, policy: MaskingPolicy) -> None:
    x1, y1, x2, y2 = item.bbox

    if policy.action == "keep":
        return  # 아무것도 안 그림 (원본 그대로 노출)

    if policy.action == "remove":
        draw.rectangle([x1, y1, x2, y2], fill="black")
        return

    if policy.action == "partial":
        draw.rectangle([x1, y1, x2, y2], fill="white", outline="gray")
        text = policy.masked_value or "*" * len(item.value)
        draw.text((x1, y1), text, fill="black")


def render_masked_pages(
    image_paths: list[str],
    items: list[DetectedItem],
    policies: list[MaskingPolicy],
    output_pdf_path: str,
) -> str:
    """페이지 이미지들 + 탐지결과 + 마스킹정책 -> 마스킹된 PDF 한 개로 저장."""

    policy_by_item_id = {p.item_id: p for p in policies}
    items_by_page: dict[int, list[DetectedItem]] = {}
    for item in items:
        items_by_page.setdefault(item.page, []).append(item)

    processed_images = []

    for page_number, image_path in enumerate(image_paths, start=1):
        image = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(image)

        for item in items_by_page.get(page_number, []):
            policy = policy_by_item_id.get(item.id)
            if policy is None:
                continue  # 이 항목에 대한 정책이 없으면 건드리지 않음
            _draw_mask(draw, item, policy)

        processed_images.append(image)

    processed_images[0].save(
        output_pdf_path, save_all=True, append_images=processed_images[1:]
    )
    return output_pdf_path


def render_analysis(
    original_file_path: str,
    items: list[DetectedItem],
    policies: list[MaskingPolicy],
    output_pdf_path: str,
    image_output_dir: str = "output_images",
) -> str:
    """/mask가 호출할 최종 진입점.

    analyze_document()에 넣었던 원본 파일 경로(original_file_path)를 그대로 다시 받아서,
    그때와 똑같은 방식(PDF면 페이지 분리, 이미지면 그대로)으로 페이지 이미지를 준비한 뒤
    마스킹을 그린다. 이렇게 하면 원본 파일만 어딘가(ANALYSES 딕셔너리 등)에 저장해두면 되고,
    페이지 이미지를 별도로 영구 보관할 필요가 없다.
    """
    ext = Path(original_file_path).suffix.lower()

    if ext == ".pdf":
        pages_info = pdf_to_images(original_file_path, image_output_dir)
        image_paths = [p["image_path"] for p in pages_info]
    else:
        image_paths = [original_file_path]

    return render_masked_pages(image_paths, items, policies, output_pdf_path)