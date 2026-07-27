import os, shutil, uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import MaskRequest, MaskResponse, MaskingPolicy, Basis

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

UPLOAD_DIR = "/opt/garim/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 분석 결과 저장소 (MVP: 메모리)
ANALYSES: dict = {}

# 공유 대상별 기본 정책 (LLM 붙기 전 임시 규칙)
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
async def analyze(file: UploadFile = File(...)):
    from app.analyze_pipeline import analyze_document
    path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{file.filename}")
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    result = analyze_document(path)
    data = result.model_dump() if hasattr(result, "model_dump") else result
    ANALYSES[data["analysis_id"]] = {"result": data, "file_path": path}
    return data

@app.post("/mask", response_model=MaskResponse)
def mask(req: MaskRequest):
    saved = ANALYSES.get(req.analysis_id)
    if not saved:
        raise HTTPException(status_code=404, detail="analysis_id not found")

    rules = DEFAULT_RULES[req.target]
    policies, counts = [], {"keep": 0, "partial": 0, "remove": 0}

    for item in saved["result"]["items"]:
        if item["id"] in req.exclude_ids:
            continue
        action = rules.get(item["type"], "remove")
        counts[action] += 1
        policies.append(MaskingPolicy(
            item_id=item["id"],
            action=action,
            masked_value=mask_value(item["type"], item["value"]) if action == "partial" else None,
            basis=Basis(
                doc="개인정보보호법",
                clause="제17조(개인정보의 제공)",
                summary=f"{req.target} 공유 기준에 따라 {item['type']} 항목을 {action} 처리",
            ),
        ))

    result_id = str(uuid.uuid4())
    saved["policies"] = policies
    saved["target"] = req.target
    ANALYSES[result_id] = saved

    summary = (f"{req.target} 기준 총 {len(policies)}건: "
               f"keep {counts['keep']}건, partial {counts['partial']}건, remove {counts['remove']}건")
    return MaskResponse(result_id=result_id, target=req.target,
                        policies=policies, summary=summary)