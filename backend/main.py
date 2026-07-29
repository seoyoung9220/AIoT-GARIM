import logging, os, shutil, time, uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.log_safe import exc_label
from app.schemas import (AnalyzeResponse, Basis, DetectedItem, HealthResponse,
                         MaskRequest, MaskResponse, MaskingPolicy)
from app.render import render_analysis

logger = logging.getLogger("garim")

UPLOAD_DIR = "/opt/garim/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

OUTPUT_DIR = "/opt/garim/outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 페이지 이미지에도 문서 원본이 그대로 담기므로 정리 대상에 포함한다.
# analyze_pipeline을 import하면 기동 시점에 LLM 클라이언트까지 끌려오므로
# (지연 import 설계가 깨진다) 같은 규칙으로 경로만 다시 계산한다.
PAGE_IMAGE_DIR = os.getenv("GARIM_OUTPUT_DIR") or str(
    Path(__file__).resolve().parent.parent / "output_images")

# --- 업로드 제한 ---
# 프론트에서도 검사하지만 브라우저 단이라 우회가 가능하다. 서버에서 다시 막는다.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
_UPLOAD_CHUNK = 1024 * 1024

# 업로드 원본·마스킹 결과·페이지 이미지를 보관하는 기한
MAX_FILE_AGE_HOURS = 24


def cleanup_old_files(dirs: list[str], max_age_hours: int = MAX_FILE_AGE_HOURS) -> int:
    """지정한 폴더에서 max_age_hours가 지난 파일·폴더를 지우고 삭제 건수를 반환한다.

    세 폴더 모두 개인정보가 담긴 원본을 들고 있는데 보관 기한이 없어 무기한 쌓인다.
    정리 실패가 서비스 기동을 막아서는 안 되므로 오류는 삼키고 로그만 남긴다.
    """
    cutoff = time.time() - max_age_hours * 3600
    removed = 0

    for directory in dirs:
        try:
            entries = list(os.scandir(directory))
        except OSError as e:
            logger.warning("정리 대상 폴더를 열 수 없습니다 (%s): %s", directory, exc_label(e))
            continue

        for entry in entries:
            try:
                if entry.stat().st_mtime >= cutoff:
                    continue
                if entry.is_dir():
                    shutil.rmtree(entry.path, ignore_errors=True)
                else:
                    os.remove(entry.path)
                removed += 1
            except OSError as e:
                # 업로드 파일명에는 사람 이름이 들어있을 수 있어 폴더 경로만 남긴다
                logger.warning("파일 정리 실패 (%s): %s", directory, exc_label(e))

    return removed


@asynccontextmanager
async def lifespan(app: FastAPI):
    removed = cleanup_old_files([UPLOAD_DIR, OUTPUT_DIR, PAGE_IMAGE_DIR])
    logger.info("기동 정리 완료: %d시간 경과분 %d건 삭제", MAX_FILE_AGE_HOURS, removed)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

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

@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", service="garim")

@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(file: UploadFile = File(...)):
    """OCR/LLM 호출이 전부 동기라서 async가 아닌 일반 함수로 둔다.

    async def 안에서 await 없이 동기 호출을 하면 그 시간 동안 이벤트 루프가
    통째로 멈춰서, 분석이 끝날 때까지 /health 같은 다른 요청도 응답하지 못한다.
    일반 def로 두면 FastAPI가 스레드풀에서 돌려주므로 다른 요청이 계속 처리된다.
    """
    from app.analyze_pipeline import analyze_document

    # 파일명은 사용자가 정하므로 경로 구분자가 섞여 들어올 수 있다. basename으로
    # 잘라내 저장 경로가 UPLOAD_DIR 밖을 가리킬 여지를 없앤다.
    original_name = os.path.basename(file.filename or "")
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"지원하지 않는 형식입니다. 허용: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{original_name}")

    # 전부 읽어 들인 뒤 크기를 재면 제한이 있으나 마나다 (그 시점에 이미 메모리를
    # 다 썼다). 조각으로 쓰면서 누적 크기를 확인한다.
    size = 0
    try:
        with open(path, "wb") as f:
            while chunk := file.file.read(_UPLOAD_CHUNK):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"파일이 너무 큽니다. 최대 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB",
                    )
                f.write(chunk)
    except HTTPException:
        # 중간까지 쓰인 파일에도 개인정보가 들어있으므로 남기지 않는다
        try:
            os.remove(path)
        except OSError:
            pass
        raise

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
                # str(e)를 찍으면 안 된다. 응답 파싱 실패 예외에는 LLM이 뱉은
                # masked_value 등 항목 값이 그대로 들어있다.
                logger.warning("item %s 정책 생성 실패, 규칙 기반으로 대체: %s",
                               item["id"], exc_label(e))

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
        # 파일 관련 예외 메시지에는 업로드 원본 경로가 들어있고, 그 파일명에는
        # 사람 이름이 들어있는 경우가 많다 (예: 홍길동_근로계약서.pdf).
        logger.warning("마스킹 파일 생성 실패: %s", exc_label(e))
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


@app.get("/download/{result_id}", response_class=FileResponse)
def download(result_id: str):
    saved = MASK_RESULTS.get(result_id)
    if not saved or not saved["output_path"] or not os.path.exists(saved["output_path"]):
        raise HTTPException(status_code=404, detail="마스킹된 파일을 찾을 수 없습니다")
    return FileResponse(saved["output_path"], media_type="application/pdf",
                        filename="masked_result.pdf")