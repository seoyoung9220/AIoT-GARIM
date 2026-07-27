"""analyze_document 파이프라인 (PDF 변환 -> OCR -> 탐지 -> bbox 매칭)."""

import threading

import pytest

import fakes
from app.analyze_pipeline import analyze_document, page_image_path
from app.bbox_matcher import find_bbox
from app.detect import detect_pii
from app.pdf_to_image import pdf_to_images
from app.schemas import OcrField, OcrPage


@pytest.fixture(scope="module")
def analyzed(tmp_path_factory):
    """문서 A와 B를 동시에 분석한다. 페이지 이미지가 섞이면 여기서부터 깨진다."""
    tmp = tmp_path_factory.mktemp("docs")
    for doc in fakes.DOCS:
        (tmp / f"{doc}.pdf").write_bytes(b"%PDF-1.4 fake")

    results, errors = {}, {}
    fakes.barrier = threading.Barrier(len(fakes.DOCS))

    def run(doc):
        try:
            results[doc] = analyze_document(str(tmp / f"{doc}.pdf"))
        except Exception as e:  # noqa: BLE001
            errors[doc] = e

    threads = [threading.Thread(target=run, args=(d,)) for d in fakes.DOCS]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    fakes.barrier = None

    assert not errors, errors
    return results


def test_analysis_ids_are_distinct(analyzed):
    assert analyzed["A"].analysis_id != analyzed["B"].analysis_id


@pytest.mark.parametrize("doc", list(fakes.DOCS))
def test_page_count(analyzed, doc):
    assert analyzed[doc].page_count == len(fakes.DOCS[doc])


@pytest.mark.parametrize("doc", list(fakes.DOCS))
def test_ocr_text_belongs_to_own_document(analyzed, doc):
    """동시 분석 시 다른 문서의 페이지를 읽어오지 않았는지 (교차 오염 검증)."""
    for page in analyzed[doc].pages:
        text = " ".join(f.text for f in page.fields)
        for word in (w for line in fakes.DOCS[doc][page.page - 1] for w in line):
            assert word in text, f"{doc} {page.page}p 에 '{word}' 없음: {text[:80]}"


@pytest.mark.parametrize("doc", list(fakes.DOCS))
def test_page_images_saved_per_analysis(analyzed, doc):
    res = analyzed[doc]
    for page_no in range(1, res.page_count + 1):
        assert page_image_path(res.analysis_id, page_no).exists()


def test_page_image_dirs_are_separate(analyzed):
    a = page_image_path(analyzed["A"].analysis_id, 1).parent
    b = page_image_path(analyzed["B"].analysis_id, 1).parent
    assert a != b and a.exists() and b.exists()


def test_shared_output_dir_would_overwrite(tmp_path):
    """pdf_to_images는 page_N.png 고정 이름을 쓴다는 전제를 못박아 둔다.

    analyze_document가 문서별 폴더를 넘기지 않으면 이렇게 덮어써진다.
    """
    for doc in ("A", "B"):
        (tmp_path / f"{doc}.pdf").write_bytes(b"%PDF-1.4 fake")

    shared = tmp_path / "shared"
    pdf_to_images(str(tmp_path / "A.pdf"), str(shared))
    pdf_to_images(str(tmp_path / "B.pdf"), str(shared))

    assert fakes.doc_of_image(shared / "page_1.png")[0] == "B"


@pytest.mark.parametrize("doc", list(fakes.DOCS))
def test_detected_items_exact(analyzed, doc):
    got = {(i.type, i.value) for i in analyzed[doc].items}
    assert got == fakes.EXPECTED[doc]


@pytest.mark.parametrize("doc", list(fakes.DOCS))
def test_item_ids_unique(analyzed, doc):
    items = analyzed[doc].items
    assert len({i.id for i in items}) == len(items)


@pytest.mark.parametrize("doc", list(fakes.DOCS))
def test_bboxes_are_sane(analyzed, doc):
    res = analyzed[doc]
    for item in res.items:
        x1, y1, x2, y2 = item.bbox
        page = next(p for p in res.pages if p.page == item.page)
        assert x1 < x2 and y1 < y2, f"{item.type} bbox 면적 0: {item.bbox}"
        assert 0 <= x1 and 0 <= y1, f"{item.type} bbox 음수 좌표: {item.bbox}"
        assert x2 <= page.width and y2 <= page.height, \
            f"{item.type} bbox가 페이지 밖: {item.bbox} vs {page.width}x{page.height}"


@pytest.mark.parametrize("doc", list(fakes.DOCS))
def test_phone_bbox_excludes_label(analyzed, doc):
    """'연락처 010-1234-5678' 에서 라벨이 값 bbox에 섞이지 않아야 한다."""
    res = analyzed[doc]
    phone = next(i for i in res.items if i.type == "phone" and i.value.startswith("010"))
    page = next(p for p in res.pages if p.page == phone.page)
    label = next(f for f in page.fields if f.text == "연락처")
    assert phone.bbox[0] > label.bbox[2]


@pytest.mark.parametrize("doc", list(fakes.DOCS))
def test_address_bbox_merged_across_fields(analyzed, doc):
    """주소는 4개 필드에 걸쳐 있으므로 bbox가 하나로 합쳐져야 한다."""
    addr = next(i for i in analyzed[doc].items if i.type == "address")
    assert addr.bbox[2] - addr.bbox[0] > 400


def test_single_image_upload(tmp_path, output_root):
    path = tmp_path / "single.png"
    fakes.page_image("A", 1).save(path)

    res = analyze_document(str(path))

    assert res.page_count == 1
    assert res.filename == "single.png"
    assert any(i.type == "phone" for i in res.items)
    # 이미지 업로드는 페이지 이미지를 따로 만들지 않는다
    assert not (output_root / res.analysis_id).exists()


# --------------------------------------------------------------- 엣지 케이스

def test_empty_page_detects_nothing():
    assert detect_pii(OcrPage(page=1, width=10, height=10, fields=[])) == []


def test_same_value_twice_gets_different_bbox():
    page = OcrPage(page=1, width=1000, height=500, fields=[
        OcrField(text="성명", bbox=[10, 10, 60, 40]),
        OcrField(text="김민수", bbox=[70, 10, 160, 40]),
        OcrField(text="확인자", bbox=[10, 60, 70, 90]),
        OcrField(text="김민수", bbox=[80, 60, 170, 90]),
    ])

    first, used = find_bbox("김민수", page, set())
    second, used = find_bbox("김민수", page, used)
    third, _ = find_bbox("김민수", page, used)

    assert first == [70, 10, 160, 40]
    assert second == [80, 60, 170, 90]
    assert third is None


def test_find_bbox_returns_none_when_missing():
    page = OcrPage(page=1, width=100, height=100,
                   fields=[OcrField(text="성명", bbox=[0, 0, 10, 10])])
    assert find_bbox("없는값", page, set())[0] is None


def test_slightly_skewed_line_is_merged():
    page = OcrPage(page=1, width=1000, height=500, fields=[
        OcrField(text="연락처", bbox=[10, 100, 80, 144]),
        OcrField(text="010-1111-2222", bbox=[90, 103, 300, 147]),
    ])
    assert len(detect_pii(page)) == 1


def test_different_lines_are_not_joined():
    """줄이 다른 숫자끼리 이어붙어 오탐되지 않아야 한다."""
    page = OcrPage(page=1, width=1000, height=900, fields=[
        OcrField(text="010", bbox=[10, 100, 80, 144]),
        OcrField(text="1234-5678", bbox=[10, 400, 200, 444]),
    ])
    assert detect_pii(page) == []
