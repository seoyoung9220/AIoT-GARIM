"""테스트 공통 설정.

외부 의존(CLOVA OCR, HCX, poppler)만 스텁으로 막고 나머지는 실제 코드를 태운다.
실행: backend/ 에서  pytest
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# analyze_pipeline이 import 시점에 읽으므로, app.* 를 부르기 전에 정해야 한다.
_OUTPUT_ROOT = tempfile.mkdtemp(prefix="garim_test_out_")
os.environ["GARIM_OUTPUT_DIR"] = _OUTPUT_ROOT

import fakes  # noqa: E402

fakes.install()  # 가짜 pdf2image를 app.pdf_to_image import 전에 심는다

import app.analyze_pipeline as pipeline  # noqa: E402
import app.ocr as ocr_mod  # noqa: E402

ocr_mod.call_clova_ocr = fakes.fake_call_clova_ocr
pipeline._llm_client = fakes.FakeLLM()


@pytest.fixture(scope="session", autouse=True)
def _cleanup_output_root():
    yield
    shutil.rmtree(_OUTPUT_ROOT, ignore_errors=True)


@pytest.fixture
def output_root() -> Path:
    return Path(_OUTPUT_ROOT)


@pytest.fixture
def make_pdf(tmp_path):
    """가짜 PDF 파일을 만든다. 내용은 스텁이 파일명으로 문서를 판별하므로 무의미하다."""

    def _make(doc: str) -> Path:
        path = tmp_path / f"{doc}.pdf"
        path.write_bytes(b"%PDF-1.4 fake")
        return path

    return _make


@pytest.fixture(scope="session")
def api(tmp_path_factory):
    """main.py를 띄운 TestClient. 업로드/출력 경로는 임시 폴더로 돌린다."""
    pytest.importorskip("fastapi", reason="pip install fastapi httpx python-multipart")

    uploads = tmp_path_factory.mktemp("uploads")
    outputs = tmp_path_factory.mktemp("outputs")

    # main.py가 import 시점에 /opt/garim/... 을 만들려고 하므로 잠시 막는다.
    real_makedirs = os.makedirs
    os.makedirs = lambda *a, **k: None
    try:
        import main
    finally:
        os.makedirs = real_makedirs

    main.UPLOAD_DIR = str(uploads)
    main.OUTPUT_DIR = str(outputs)

    from fastapi.testclient import TestClient

    return SimpleNamespace(main=main, client=TestClient(main.app),
                           uploads=uploads, outputs=outputs)
