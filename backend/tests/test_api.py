"""FastAPI 엔드포인트 (/health, /analyze, /mask, /download)."""

import sys
import threading
import types

import pytest

import fakes
from app.analyze_pipeline import page_image_path
from app.schemas import Basis, MaskingPolicy


@pytest.fixture(scope="module")
def analyzed(api):
    """문서 A, B를 동시에 업로드 분석한다."""
    responses = {}
    fakes.barrier = threading.Barrier(len(fakes.DOCS))

    def post(doc):
        responses[doc] = api.client.post(
            "/analyze",
            files={"file": (f"{doc}.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )

    threads = [threading.Thread(target=post, args=(d,)) for d in fakes.DOCS]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    fakes.barrier = None

    for doc, r in responses.items():
        assert r.status_code == 200, f"{doc}: {r.text[:300]}"
    return {doc: r.json() for doc, r in responses.items()}


@pytest.fixture
def rule_based_only(monkeypatch):
    """LLM 모듈 import를 실패시켜 규칙 기반 폴백 경로로 고정한다."""
    monkeypatch.setitem(sys.modules, "LLM.reasoning", None)


def test_health(api):
    r = api.client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# --------------------------------------------------------------- /analyze

@pytest.mark.parametrize("doc", list(fakes.DOCS))
def test_analyze_returns_own_document_only(analyzed, doc):
    values = {i["value"] for i in analyzed[doc]["items"]}
    others = {v for other, entries in fakes.LLM_ITEMS.items() if other != doc
              for _, v in entries}

    assert others.isdisjoint(values), f"{doc} 응답에 다른 문서 값이 섞임: {values}"
    assert analyzed[doc]["page_count"] == 2
    assert len(analyzed[doc]["pages"]) == 2


@pytest.mark.parametrize("doc", list(fakes.DOCS))
def test_analyze_saves_page_images(analyzed, doc):
    for page in (1, 2):
        assert page_image_path(analyzed[doc]["analysis_id"], page).exists()


def test_uploads_are_stored(api, analyzed):
    assert len(list(api.uploads.glob("*.pdf"))) >= len(fakes.DOCS)


# ------------------------------------------------------------------ /mask

def test_mask_rule_based_fallback(api, analyzed, rule_based_only):
    aid = analyzed["A"]["analysis_id"]

    r = api.client.post("/mask", json={"analysis_id": aid, "target": "public",
                                       "exclude_ids": []})

    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert len(body["policies"]) == len(analyzed["A"]["items"])
    assert all(p["basis"]["doc"] for p in body["policies"])
    assert "LLM 실패" in body["summary"]


def test_mask_excludes_requested_items(api, analyzed, rule_based_only):
    aid = analyzed["A"]["analysis_id"]
    item_ids = [i["id"] for i in analyzed["A"]["items"]]

    r = api.client.post("/mask", json={"analysis_id": aid, "target": "partner",
                                       "exclude_ids": item_ids[:1]})

    assert len(r.json()["policies"]) == len(item_ids) - 1


def test_mask_unknown_analysis_id(api):
    r = api.client.post("/mask", json={"analysis_id": "없는-id", "target": "public",
                                       "exclude_ids": []})
    assert r.status_code == 404


def test_mask_invalid_target(api, analyzed):
    r = api.client.post("/mask", json={"analysis_id": analyzed["A"]["analysis_id"],
                                       "target": "wrong", "exclude_ids": []})
    assert r.status_code == 422


def test_mask_repairs_wrong_item_id_from_llm(api, analyzed, monkeypatch):
    """LLM이 item_id를 엉뚱하게 채워도 서버가 실제 항목 id로 교정해야 한다."""
    calls = {"n": 0}

    def fake_generate_policy(item, target):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("HCX 타임아웃 시뮬레이션")
        return MaskingPolicy(item_id="LLM이-엉뚱하게-채운-id", action="partial",
                             masked_value="010-****-5678",
                             basis=Basis(doc="사내 지침", clause="제5조", summary="테스트"))

    module = types.ModuleType("LLM.reasoning")
    module.generate_policy = fake_generate_policy
    monkeypatch.setitem(sys.modules, "LLM.reasoning", module)

    aid = analyzed["A"]["analysis_id"]
    item_ids = {i["id"] for i in analyzed["A"]["items"]}

    r = api.client.post("/mask", json={"analysis_id": aid, "target": "partner",
                                       "exclude_ids": []})

    assert r.status_code == 200, r.text[:300]
    returned = {p["item_id"] for p in r.json()["policies"]}
    assert "LLM이-엉뚱하게-채운-id" not in returned
    assert returned <= item_ids
    assert "LLM 실패 1건" in r.json()["summary"]


# -------------------------------------------------------------- /download

@pytest.fixture
def two_maskings(api, analyzed, rule_based_only):
    """같은 문서를 public / internal 두 번 마스킹한다."""
    aid = analyzed["A"]["analysis_id"]
    first = api.client.post("/mask", json={"analysis_id": aid, "target": "public",
                                          "exclude_ids": []}).json()
    second = api.client.post("/mask", json={"analysis_id": aid, "target": "internal",
                                           "exclude_ids": []}).json()
    return first, second


def test_download_returns_pdf(api, two_maskings):
    first, _ = two_maskings

    r = api.client.get(f"/download/{first['result_id']}")

    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    # 프론트가 그대로 파일로 저장하므로 실제 PDF여야 한다
    assert r.content.startswith(b"%PDF"), r.content[:20]


def test_download_keeps_serving_its_own_result(api, two_maskings):
    """나중 마스킹이 앞선 result_id의 결과 파일을 덮어쓰면 안 된다.

    덮어쓰면 공개용으로 나눠준 링크가 내부용(개인정보가 덜 가려진) 파일을 준다.
    """
    first, second = two_maskings

    public_pdf = api.client.get(f"/download/{first['result_id']}").content
    internal_pdf = api.client.get(f"/download/{second['result_id']}").content
    public_again = api.client.get(f"/download/{first['result_id']}").content

    assert public_pdf != internal_pdf, "public과 internal 결과가 동일 - 마스킹 차이가 없음"
    assert public_again == public_pdf


def test_mask_results_are_independent(api, two_maskings):
    first, second = two_maskings
    results = api.main.MASK_RESULTS

    assert results[first["result_id"]] is not results[second["result_id"]]
    assert results[first["result_id"]]["target"] == "public"
    assert results[first["result_id"]]["output_path"] != results[second["result_id"]]["output_path"]


def test_stores_do_not_leak_into_each_other(api, analyzed, two_maskings):
    first, _ = two_maskings

    assert first["result_id"] not in api.main.ANALYSES
    assert analyzed["A"]["analysis_id"] not in api.main.MASK_RESULTS
    # 마스킹을 여러 번 해도 원본 분석 결과는 그대로 남아 있어야 한다
    assert api.main.ANALYSES[analyzed["A"]["analysis_id"]]["result"]["analysis_id"] \
        == analyzed["A"]["analysis_id"]


def test_download_rejects_analysis_id(api, analyzed):
    r = api.client.get(f"/download/{analyzed['A']['analysis_id']}")
    assert r.status_code == 404


def test_download_unknown_id(api):
    assert api.client.get("/download/존재하지-않는-id").status_code == 404
