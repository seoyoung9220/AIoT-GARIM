# AIoT-GARIM

문서에서 개인정보를 탐지하고, 공유 대상(사내/협력사/외부)에 따라 차등 마스킹한
문서를 만들어 주는 서비스.

## 백엔드 실행

```bash
pip install -r requirements.txt
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

### poppler (pip로 설치되지 않음)

PDF를 페이지 이미지로 바꾸는 데 필요하다. **없으면 PDF 업로드 시 `/analyze`가
500으로 떨어진다.**

```bash
sudo apt install poppler-utils     # Ubuntu/Debian
brew install poppler               # macOS
```

Windows는 poppler 바이너리를 받아 PATH에 추가한다.

### .env

저장소에 포함되지 않으므로(개인정보·비밀키) 배포 서버에도 **git pull로 따라가지
않는다.** 프로젝트 루트에 직접 만들어야 한다.

```
OCR_INVOKE_URL=      # CLOVA OCR 호출 URL
OCR_SECRET_KEY=      # CLOVA OCR 시크릿
CLOVA_STUDIO_KEY=    # HCX / 임베딩 API 키

DB_HOST=             # RAG 정책 검색용 pgvector DB
DB_PORT=5432
DB_NAME=
DB_USER=
DB_PASSWORD=
```

`.env`가 없어도 서버는 뜨지만, OCR 키가 없으면 `/analyze`가 실패하고 DB에 접속하지
못하면 `/mask`는 규칙 기반 정책으로 대체된다.

### 저장 경로

| 환경변수 | 기본값 | 내용 |
|---|---|---|
| `GARIM_OUTPUT_DIR` | `<프로젝트 루트>/output_images` | 페이지 이미지 |
| (하드코딩) | `/opt/garim/uploads` | 업로드 원본 |
| (하드코딩) | `/opt/garim/outputs` | 마스킹 결과 PDF |

셋 다 개인정보가 담기므로 저장소에 올라가지 않게 되어 있다. 쓰기 권한이 없으면
서버가 뜨지 않거나 분석이 실패한다.

## 프론트엔드 실행

```bash
cd frontend
npm install
npm run dev
```

백엔드 주소는 `.env`의 `VITE_API_BASE_URL`로 지정한다.

## 테스트

```bash
pip install -r requirements-dev.txt
cd backend
pytest
```

CLOVA 키나 poppler 없이 돌아간다. 자세한 내용은 [backend/tests/README.md](backend/tests/README.md).

## 구조

| 폴더 | 역할 |
|---|---|
| `backend/` | FastAPI 서버, OCR·탐지·마스킹 파이프라인 |
| `LLM/` | CLOVA HCX 호출 (이름·주소 탐지, 마스킹 정책 판단) |
| `rag/` | pgvector 기반 정책 근거 검색 |
| `frontend/` | React + Vite 웹 UI |
