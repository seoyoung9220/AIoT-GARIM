"""DetectedItem + MaskingPolicy를 받아서, 이미지 위에 실제로 마스킹을 그리고 PDF로 저장한다.

analyze_pipeline.analyze_document()가 반환하는 AnalyzeResponse에는 원본 페이지
"이미지 파일 경로"가 남아있지 않다 (OcrPage는 텍스트+좌표만 가짐). 그래서 이 파일은
분석 시점의 파일 경로를 별도로 다시 받아서, PDF든 단일 이미지든 그 시점과 똑같은
방식으로 페이지 이미지를 준비한 뒤 마스킹을 그린다.
"""

import shutil
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.schemas import DetectedItem, MaskingPolicy
from app.pdf_to_image import pdf_to_images

# PIL 기본 폰트는 한글 글리프가 없어서 "김*수"가 두부(□*□)로 찍힌다.
# partial 마스킹 값은 대부분 이름이라 한글 폰트가 사실상 필수다.
_FONT_PATH = Path(__file__).resolve().parent.parent / "assets" / "NanumGothic-Regular.ttf"
_MIN_FONT_SIZE = 8
_font_cache: dict[int, ImageFont.ImageFont] = {}


def _load_font(size: int) -> ImageFont.ImageFont:
    size = max(size, _MIN_FONT_SIZE)
    if size not in _font_cache:
        try:
            _font_cache[size] = ImageFont.truetype(str(_FONT_PATH), size)
        except OSError:
            # 폰트 파일이 없어도 마스킹 자체는 계속돼야 한다 (한글은 깨진 채로 나감).
            try:
                _font_cache[size] = ImageFont.load_default(size)
            except TypeError:  # 구버전 Pillow는 크기 지정을 지원하지 않음
                _font_cache[size] = ImageFont.load_default()
    return _font_cache[size]


def _text_width(font: ImageFont.ImageFont, text: str) -> int:
    left, _, right, _ = font.getbbox(text)
    return right - left


def _fit_font(text: str, box_width: int, box_height: int) -> ImageFont.ImageFont:
    """마스킹 값이 bbox 안에 들어가도록 글자 크기를 맞춘다.

    기본 폰트를 그대로 쓰면 크기가 약 11px로 고정돼서, OCR 글자 높이(보통 40px 이상)
    대비 지나치게 작게 찍힌다. 박스 높이에 맞춰 키우되 가로로 넘치면 줄인다.
    """
    size = int(box_height * 0.8)
    font = _load_font(size)
    width = _text_width(font, text)

    if width > box_width and width > 0:
        font = _load_font(int(size * box_width / width))

    return font


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

        font = _fit_font(text, x2 - x1, y2 - y1)

        if isinstance(font, ImageFont.FreeTypeFont):
            # anchor="lm" = 왼쪽 기준 세로 중앙. TrueType에서만 지원된다.
            draw.text((x1 + 2, (y1 + y2) // 2), text, fill="black", font=font, anchor="lm")
        else:
            draw.text((x1 + 2, y1), text, fill="black", font=font)


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
    image_output_dir: str | None = None,
) -> str:
    """/mask가 호출할 최종 진입점.

    analyze_document()에 넣었던 원본 파일 경로(original_file_path)를 그대로 다시 받아서,
    그때와 똑같은 방식(PDF면 페이지 분리, 이미지면 그대로)으로 페이지 이미지를 준비한 뒤
    마스킹을 그린다. 이렇게 하면 원본 파일만 어딘가(ANALYSES 딕셔너리 등)에 저장해두면 된다.

    image_output_dir: 페이지 이미지를 풀어놓을 폴더. pdf_to_images가 page_1.png 라는
        고정 이름을 쓰기 때문에 "문서 한 건당 하나"여야 한다. 여러 요청이 같은 폴더를
        공유하면 서로의 페이지를 덮어써서, 남의 계약서 페이지가 섞인 PDF가 나간다.
        생략하면 이번 호출 전용 임시 폴더를 만들어 쓰고 끝나면 지운다.
    """
    ext = Path(original_file_path).suffix.lower()

    if ext != ".pdf":
        return render_masked_pages([original_file_path], items, policies, output_pdf_path)

    # 페이지 이미지는 PDF를 만들기 위한 중간 산출물이라 남길 이유가 없다.
    # 개인정보가 담긴 이미지를 디스크에 방치하지 않도록 다 쓰면 지운다.
    temp_dir = tempfile.mkdtemp(prefix="garim_render_") if image_output_dir is None else None

    try:
        pages_info = pdf_to_images(original_file_path, temp_dir or image_output_dir)
        image_paths = [p["image_path"] for p in pages_info]
        return render_masked_pages(image_paths, items, policies, output_pdf_path)
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)