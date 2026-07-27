"""render.py — 마스킹 그리기, PDF 생성, 한글 폰트."""

import glob
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

import app.render as render
import fakes
from app.schemas import Basis, DetectedItem, MaskingPolicy

BASIS = Basis(doc="개인정보보호법", clause="제17조", summary="테스트")


def _fixture(doc):
    items = [
        DetectedItem(id=f"{doc}-1", type="phone", value="010-1234-5678",
                     page=1, bbox=[100, 100, 400, 150], source="regex"),
        DetectedItem(id=f"{doc}-2", type="name", value="김민수",
                     page=2, bbox=[100, 200, 300, 250], source="llm"),
    ]
    policies = [
        MaskingPolicy(item_id=f"{doc}-1", action="remove", basis=BASIS),
        MaskingPolicy(item_id=f"{doc}-2", action="partial", masked_value="김*수", basis=BASIS),
    ]
    return items, policies


def _leftover_temp_dirs():
    return glob.glob(os.path.join(tempfile.gettempdir(), "garim_render_*"))


# ------------------------------------------------------- 동시 렌더링 교차 오염

def test_concurrent_render_keeps_pages_separate(tmp_path, monkeypatch):
    for doc in fakes.DOCS:
        (tmp_path / f"{doc}.pdf").write_bytes(b"%PDF-1.4 fake")

    seen = {}
    real_render_pages = render.render_masked_pages

    def spy(image_paths, items, policies, output_pdf_path):
        doc = items[0].id.split("-")[0]
        seen[doc] = [fakes.doc_of_image(p) for p in image_paths]
        return real_render_pages(image_paths, items, policies, output_pdf_path)

    monkeypatch.setattr(render, "render_masked_pages", spy)
    fakes.barrier = threading.Barrier(len(fakes.DOCS))

    errors = {}

    def run(doc):
        items, policies = _fixture(doc)
        try:
            render.render_analysis(str(tmp_path / f"{doc}.pdf"), items, policies,
                                   str(tmp_path / f"{doc}_masked.pdf"))
        except Exception as e:  # noqa: BLE001
            errors[doc] = e

    threads = [threading.Thread(target=run, args=(d,)) for d in fakes.DOCS]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    fakes.barrier = None

    assert not errors, errors
    for doc in fakes.DOCS:
        assert seen[doc] == [(doc, 1), (doc, 2)], f"{doc}가 다른 문서 페이지를 받음: {seen[doc]}"
        out = tmp_path / f"{doc}_masked.pdf"
        assert out.exists() and out.stat().st_size > 0


# ------------------------------------------------------------- 임시 폴더 정리

def test_temp_dir_is_cleaned_up(tmp_path):
    (tmp_path / "A.pdf").write_bytes(b"%PDF-1.4 fake")
    items, policies = _fixture("A")

    render.render_analysis(str(tmp_path / "A.pdf"), items, policies,
                           str(tmp_path / "out.pdf"))

    assert not _leftover_temp_dirs()


def test_temp_dir_is_cleaned_up_on_failure(tmp_path, monkeypatch):
    (tmp_path / "A.pdf").write_bytes(b"%PDF-1.4 fake")
    items, policies = _fixture("A")

    def boom(*a, **k):
        raise RuntimeError("렌더 실패 시뮬레이션")

    monkeypatch.setattr(render, "render_masked_pages", boom)

    with pytest.raises(RuntimeError):
        render.render_analysis(str(tmp_path / "A.pdf"), items, policies,
                               str(tmp_path / "out.pdf"))

    assert not _leftover_temp_dirs()


def test_explicit_output_dir_is_respected(tmp_path):
    (tmp_path / "A.pdf").write_bytes(b"%PDF-1.4 fake")
    items, policies = _fixture("A")
    explicit = tmp_path / "explicit"

    render.render_analysis(str(tmp_path / "A.pdf"), items, policies,
                           str(tmp_path / "out.pdf"), image_output_dir=str(explicit))

    assert (explicit / "page_1.png").exists()


def test_single_image_input(tmp_path):
    src = tmp_path / "single.png"
    fakes.page_image("B", 1).save(src)
    items = [DetectedItem(id="s", type="phone", value="010-1111-2222",
                          page=1, bbox=[50, 50, 250, 100], source="regex")]
    policies = [MaskingPolicy(item_id="s", action="remove", basis=BASIS)]

    render.render_analysis(str(src), items, policies, str(tmp_path / "out.pdf"))

    assert (tmp_path / "out.pdf").exists()
    # 원본 파일은 건드리지 않는다 (마스킹은 메모리 사본에만)
    assert Image.open(src).convert("RGB").getpixel((60, 60)) == fakes.color_of("B", 1)


def test_pdf_save_works_in_a_fresh_process(tmp_path):
    """PIL이 초기화되지 않은 상태에서도 PDF 저장이 되어야 한다.

    PIL은 RGB 이미지를 PDF로 저장할 때 JPEG 인코더를 쓰는데, 플러그인이 아직
    등록되기 전이면 KeyError('JPEG')로 실패한다. 서버를 새로 띄운 직후 첫
    /mask 요청이 정확히 이 상태다.

    pytest 프로세스는 이미 PIL이 초기화돼 있어 이 문제가 드러나지 않으므로,
    깨끗한 인터프리터를 따로 띄워서 확인한다.
    """
    page = tmp_path / "page.png"
    Image.new("RGB", (200, 120), "white").save(page)
    out = tmp_path / "masked.pdf"

    script = textwrap.dedent(f"""
        import sys, types
        sys.path.insert(0, {str(Path(__file__).resolve().parent.parent)!r})
        fake = types.ModuleType("pdf2image")
        fake.convert_from_path = lambda *a, **k: []
        sys.modules["pdf2image"] = fake

        from app.render import render_masked_pages
        from app.schemas import Basis, DetectedItem, MaskingPolicy

        items = [DetectedItem(id="i", type="phone", value="010-1234-5678",
                              page=1, bbox=[10, 10, 150, 60], source="regex")]
        policies = [MaskingPolicy(item_id="i", action="remove",
                                  basis=Basis(doc="d", clause="c", summary="s"))]

        render_masked_pages([{str(page)!r}], items, policies, {str(out)!r})
    """)

    result = subprocess.run([sys.executable, "-c", script],
                            capture_output=True, text=True)

    assert result.returncode == 0, result.stderr[-800:]
    assert out.exists() and out.read_bytes().startswith(b"%PDF")


# ------------------------------------------------------------- 마스킹 그리기

def test_remove_fills_bbox_black():
    img = Image.new("RGB", (500, 300), "white")
    item = DetectedItem(id="i", type="phone", value="010-1234-5678",
                        page=1, bbox=[100, 100, 400, 150], source="regex")
    render._draw_mask(ImageDraw.Draw(img), item,
                      MaskingPolicy(item_id="i", action="remove", basis=BASIS))

    assert img.getpixel((200, 120)) == (0, 0, 0)
    assert img.getpixel((450, 280)) == (255, 255, 255)  # bbox 밖은 원본 유지


def test_keep_draws_nothing():
    img = Image.new("RGB", (200, 200), "white")
    item = DetectedItem(id="k", type="name", value="홍길동",
                        page=1, bbox=[10, 10, 100, 60], source="llm")
    render._draw_mask(ImageDraw.Draw(img), item,
                      MaskingPolicy(item_id="k", action="keep", basis=BASIS))

    assert img.getpixel((50, 30)) == (255, 255, 255)


def test_partial_draws_white_box():
    img = Image.new("RGB", (500, 300), "black")
    item = DetectedItem(id="p", type="name", value="김민수",
                        page=1, bbox=[100, 50, 400, 100], source="llm")
    render._draw_mask(ImageDraw.Draw(img), item,
                      MaskingPolicy(item_id="p", action="partial",
                                    masked_value="김*수", basis=BASIS))

    assert img.getpixel((350, 60)) == (255, 255, 255)


# ------------------------------------------------------------------ 한글 폰트

BOX = [100, 50, 400, 100]


def _draw_partial(masked, bbox=BOX, canvas=(900, 200)):
    img = Image.new("RGB", canvas, "black")
    item = DetectedItem(id="i", type="name", value="김민수", page=1,
                        bbox=bbox, source="llm")
    render._draw_mask(ImageDraw.Draw(img), item,
                      MaskingPolicy(item_id="i", action="partial",
                                    masked_value=masked, basis=BASIS))
    return img


def _ink_columns(img, bbox):
    """박스 안에서 x열마다 검은 픽셀 수. 글리프인지 두부(□)인지 가르는 데 쓴다."""
    x1, y1, x2, y2 = bbox
    return [sum(1 for y in range(y1 + 3, y2 - 3) if sum(img.getpixel((x, y))) < 200)
            for x in range(x1 + 3, x2 - 3)]


def test_bundled_font_loads():
    assert render._FONT_PATH.exists(), f"번들 폰트 없음: {render._FONT_PATH}"
    font = render._load_font(30)
    assert isinstance(font, ImageFont.FreeTypeFont)
    assert font.getname()[0] == "NanumGothic"


def test_korean_renders_as_real_glyphs():
    """기본 PIL 폰트는 한글을 두부(□)로 그린다. 두부는 속 빈 사각형이라
    획 분포가 균일하므로, 열별 잉크량이 들쭉날쭉해야 진짜 글리프다."""
    img = _draw_partial("김*수")
    columns = [c for c in _ink_columns(img, BOX) if c]

    assert sum(_ink_columns(img, BOX)) > 100, "글자가 거의 안 그려짐"
    assert len(columns) > 30
    assert max(columns) > min(columns) + 2, "획 분포가 균일함 = 두부 상자 의심"


def test_font_size_follows_box_height():
    small = render._fit_font("김*수", 300, 20)
    big = render._fit_font("김*수", 300, 60)

    assert big.size > small.size
    assert big.size >= 40, f"60px 박스인데 글자가 {big.size}px"


def test_long_text_shrinks_to_fit_width():
    text = "서울특별시 강남구 테헤란로 123길 45, 6층 601호"
    font = render._fit_font(text, 200, 50)

    assert render._text_width(font, text) <= 200
    assert font.size >= render._MIN_FONT_SIZE


def test_text_does_not_overflow_box():
    img = _draw_partial("김*수")
    x1, y1, x2, y2 = BOX

    above_below = [(x, y) for y in (y1 - 5, y2 + 5) for x in range(x1, x2)
                   if img.getpixel((x, y)) != (0, 0, 0)]
    right = [(x, y) for x in range(x2 + 2, x2 + 30) for y in range(y1, y2)
             if img.getpixel((x, y)) != (0, 0, 0)]

    assert not above_below
    assert not right


def test_flat_box_does_not_crash():
    _draw_partial("김*수", bbox=[10, 10, 300, 16])


def test_falls_back_when_font_missing(monkeypatch):
    """폰트 파일이 없어도 마스킹 자체는 계속돼야 한다."""
    monkeypatch.setattr(render, "_FONT_PATH", Path("존재하지_않는_폰트.ttf"))
    monkeypatch.setattr(render, "_font_cache", {})

    img = _draw_partial("김*수")

    assert sum(_ink_columns(img, BOX)) > 0
