import logging, os, shutil, uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.schemas import DetectedItem, MaskRequest, MaskResponse, MaskingPolicy, Basis
from app.render import render_analysis

logger = logging.getLogger("garim")

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

UPLOAD_DIR = "/opt/garim/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

OUTPUT_DIR = "/opt/garim/outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 분석 결과 저장소 (MVP: 메모리)
ANALYSES: dict = {}

# 마스킹 결과 저장소. ANALYSES와 반드시 분리한다.
# 같은 문서를 대상만 바꿔 여러 번 마스킹할 수 있는데, 두 저장소를 섞으면
# 나중 마스킹이 앞선 result_id의 결과 파일까지 덮어써서, 공개용으로 받아간
# 다운로드 링크가 내부용(개인정보가 덜 가려진) 파일을 내려주게 된다.
MASK_RESULTS: dict = {}

# 공유 대상별 기본 정책 (LLM 호출 실패 시 폴백으로 사용)
DEFAULT_RULES = {
    "internal":  {"name": "keep",   "phone": "keep",    "address": "keep",
                  "account": "keep", "business_no": "keep", "resident_no": "partial"},
    "partner":   {"name": "keep",   "phone": "partial", "address": "partial",
                  "account": "remove", "business_no": "keep", "resident_no": "remove"},
    "public":    {"name": "remove", "phone": "remove",  "address": "remove",
                  "account": "remove", "business_no": "remove", "resident_no": "remove"},
}

def mask_value(pii_type: str, value: str) -> str:
    if pii_type == "phone":
        parts = value.split("-")
        return f"{parts[0]}-****-{parts[-1]}" if len(parts) == 3 else value[:3] + "****"
    if pii_type == "resident_no":
        return value.split("-")[0] + "-*******" if "-" in value else value[:6] + "*******"
    if pii_type == "name":
        return value[0] + "*" * (len(value) - 1)
    return value[:2] + "*" * max(len(value) - 2, 1)

@app.get("/health")
def health():
    return {"status": "ok", "service": "garim"}

@app.post("/analyze")
def analyze(file: UploadFile = File(...)):
    """OCR/LLM 호출이 전부 동기라서 async가 아닌 일반 함수로 둔다.

    async def 안에서 await 없이 동기 호출을 하면 그 시간 동안 이벤트 루프가
    통째로 멈춰서, 분석이 끝날 때까지 /health 같은 다른 요청도 응답하지 못한다.
    일반 def로 두면 FastAPI가 스레드풀에서 돌려주므로 다른 요청이 계속 처리된다.
    """
    from app.analyze_pipeline import analyze_document
    path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{file.filename}")
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    result = analyze_document(path)
    data = result.model_dump() if hasattr(result, "model_dump") else result
    ANALYSES[data["analysis_id"]] = {"result": data, "file_path": path}
    return data

def rule_based_policy(item: dict, target: str) -> MaskingPolicy:
    """LLM을 못 쓸 때 사용하는 규칙 기반 정책."""
    action = DEFAULT_RULES[target].get(item["type"], "remove")
    return MaskingPolicy(
        item_id=item["id"],
        action=action,
        masked_value=mask_value(item["type"], item["value"]) if action == "partial" else None,
        basis=Basis(
            doc="개인정보보호법",
            clause="제17조(개인정보의 제공)",
            summary=f"{target} 공유 기준에 따라 {item['type']} 항목을 {action} 처리",
        ),
    )

@app.post("/mask", response_model=MaskResponse)
def mask(req: MaskRequest):
    saved = ANALYSES.get(req.analysis_id)
    if not saved:
        raise HTTPException(status_code=404, detail="analysis_id not found")

    # LLM/RAG는 외부 API와 DB에 의존한다. 최상단에서 import하면 그쪽 장애가
    # 서비스 기동 자체를 막으므로 analyze와 같이 요청 시점에 가져온다.
    try:
        from LLM.reasoning import generate_policy
    except Exception as e:
        logger.warning("LLM 모듈 로드 실패, 규칙 기반으로 대체: %s", e)
        generate_policy = None

    policies, counts = [], {"keep": 0, "partial": 0, "remove": 0}
    fallback_count = 0
    included_items = []  # 마스킹 렌더링에 쓸, exclude 안 된 항목들

    for item in saved["result"]["items"]:
        if item["id"] in req.exclude_ids:
            continue

        policy = None
        if generate_policy is not None:
            try:
                policy = generate_policy(DetectedItem.model_validate(item), req.target)
                # LLM이 item_id를 잘못 채우면 프론트의 항목 매칭이 조용히 깨진다
                policy.item_id = item["id"]
            except Exception as e:
                logger.warning("item %s 정책 생성 실패, 규칙 기반으로 대체: %s", item["id"], e)

        if policy is None:
            policy = rule_based_policy(item, req.target)
            fallback_count += 1

        counts[policy.action] += 1
        policies.append(policy)
        included_items.append(DetectedItem.model_validate(item))

    result_id = str(uuid.uuid4())

    # 실제 마스킹 파일 생성. 실패해도 정책 응답 자체는 정상 반환한다.
    output_path = os.path.join(OUTPUT_DIR, f"{result_id}.pdf")
    try:
        render_analysis(
            original_file_path=saved["file_path"],
            items=included_items,
            policies=policies,
            output_pdf_path=output_path,
        )
    except Exception as e:
        logger.warning("마스킹 파일 생성 실패: %s", e)
        output_path = None

    # ANALYSES(분석 결과)는 읽기만 하고, 마스킹 결과는 별도 저장소에 담는다.
    MASK_RESULTS[result_id] = {
        "analysis_id": req.analysis_id,
        "target": req.target,
        "policies": policies,
        "output_path": output_path,
    }

    summary = (f"{req.target} 기준 총 {len(policies)}건: "
               f"keep {counts['keep']}건, partial {counts['partial']}건, remove {counts['remove']}건")
    if fallback_count:
        summary += f" (LLM 실패 {fallback_count}건은 기본 규칙 적용)"
    return MaskResponse(result_id=result_id, target=req.target,
                        policies=policies, summary=summary)


@app.get("/download/{result_id}")
def download(result_id: str):
    saved = MASK_RESULTS.get(result_id)
    if not saved or not saved["output_path"] or not os.path.exists(saved["output_path"]):
        raise HTTPException(status_code=404, detail="마스킹된 파일을 찾을 수 없습니다")
    return FileResponse(saved["output_path"], media_type="application/pdf",
                        filename="masked_result.pdf")