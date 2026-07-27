import json

from pathlib import Path

import fitz  # PyMuPDF

# ============================================================

# 설정

# ============================================================

BASE_DIR = Path(__file__).resolve().parent

OFFICIAL_DIR = BASE_DIR / "data" / "official"

INTERNAL_DIR = BASE_DIR / "data" / "internal"

OUTPUT_DIR = BASE_DIR / "output"

OUTPUT_FILE = OUTPUT_DIR / "chunks.json"

# 처음에는 이 값으로 시작

CHUNK_SIZE = 500

CHUNK_OVERLAP = 50

# ============================================================

# 1. PDF 읽기

# ============================================================

def read_pdf(pdf_path):

    """

    PDF 파일을 읽어서 페이지별 텍스트를 반환합니다.

    반환 예시:

    [

        {

            "page": 1,

            "text": "첫 번째 페이지 내용..."

        },

        {

            "page": 2,

            "text": "두 번째 페이지 내용..."

        }

    ]

    """

    print(f"[PDF 읽기] {pdf_path.name}")

    doc = fitz.open(pdf_path)

    pages = []

    for page_number, page in enumerate(doc, start=1):

        text = page.get_text("text").strip()

        # 텍스트가 없는 페이지는 건너뜀

        if not text:

            continue

        pages.append({

            "page": page_number,

            "text": text

        })

    doc.close()

    print(f"  → 전체 PDF 페이지: {len(doc) if False else '처리 완료'}")

    print(f"  → 텍스트 추출 페이지: {len(pages)}")

    return pages

# ============================================================

# 2. 텍스트 Chunking

# ============================================================

def split_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):

    """

    긴 텍스트를 일정한 크기로 나눕니다.

    예:

    chunk_size = 800

    overlap = 100

    Chunk 1 : 0 ~ 800

    Chunk 2 : 700 ~ 1500

    Chunk 3 : 1400 ~ 2200

    앞뒤 Chunk가 100자씩 겹칩니다.

    """

    chunks = []

    start = 0

    while start < len(text):

        end = start + chunk_size

        chunk = text[start:end].strip()

        if chunk:

            chunks.append(chunk)

        # 마지막 chunk면 종료

        if end >= len(text):

            break

        start += chunk_size - overlap

    return chunks

# ============================================================

# 3. PDF → RAG Chunk 변환

# ============================================================

def create_pdf_chunks(

    pdf_path,

    document_name,

    document_id

):

    """

    PDF를 읽고 RAG에서 사용할 Chunk 형태로 변환합니다.

    """

    pages = read_pdf(pdf_path)

    results = []

    chunk_count = 0

    for page in pages:

        page_number = page["page"]

        page_text = page["text"]

        text_chunks = split_text(page_text)

        for text in text_chunks:

            chunk_count += 1

            chunk = {

                "chunk_id": f"{document_id}_{chunk_count}",

                "source_type": "official",

                "document": document_name,

                "page": page_number,

                "content": text

            }

            results.append(chunk)

    print(f"  → 생성된 Chunk: {len(results)}개\n")

    return results

# ============================================================

# 4. GARIM 사내정책 JSON 읽기

# ============================================================

def create_internal_policy_chunks(json_path):

    """

    GARIM 가상 사내정책 JSON을 읽어서

    RAG Chunk 형태로 변환합니다.

    사내정책은 이미

    개인정보 유형 × 공유 대상

    단위로 나뉘어 있으므로 추가로 800자씩 자르지 않습니다.

    """

    print(f"[사내정책 읽기] {json_path.name}")

    with open(json_path, "r", encoding="utf-8") as f:

        data = json.load(f)

    results = []

    policies = data.get("policies", [])

    for policy in policies:

        policy_id = policy["policy_id"]

        pii_type = policy["pii_type"]

        target = policy["target"]

        action = policy["action"]

        reason = policy["reason"]

        # Vector Search할 때 의미가 잘 전달되도록

        # 검색 대상이 되는 자연어 content를 생성

        content = (

            f"GARIM 사내 문서 공유 정책. "

            f"개인정보 유형은 {pii_type}이다. "

            f"공유 대상은 {target}이다. "

            f"처리 방법은 {action}이다. "

            f"처리 근거는 다음과 같다. {reason}"

        )

        chunk = {

            "chunk_id": policy_id,

            "source_type": "internal_policy",

            "document": "GARIM 가상 사내 문서 공유 보안정책",

            "page": None,

            "content": content,

            "metadata": {

                "pii_type": pii_type,

                "target": target,

                "action": action

            }

        }

        # partial 정책에 예시값이 있다면 같이 저장

        if "masked_value_example" in policy:

            chunk["metadata"]["masked_value_example"] = (

                policy["masked_value_example"]

            )

        results.append(chunk)

    print(f"  → 생성된 Chunk: {len(results)}개\n")

    return results

# ============================================================

# 5. 모든 데이터 Chunking

# ============================================================

def build_chunks():

    print("=" * 60)

    print("GARIM RAG Chunk 생성 시작")

    print("=" * 60)

    all_chunks = []

    # --------------------------------------------------------

    # 공식자료 1

    # 개인정보 처리 통합 안내서

    # --------------------------------------------------------

    pdf1 = OFFICIAL_DIR / "개인정보_처리_통합안내서.pdf"

    if pdf1.exists():

        chunks = create_pdf_chunks(

            pdf_path=pdf1,

            document_name="개인정보 처리 통합 안내서",

            document_id="official_integrated"

        )

        all_chunks.extend(chunks)

    else:

        print(f"[경고] 파일 없음: {pdf1}\n")

    # --------------------------------------------------------

    # 공식자료 2

    # 개인정보 처리방침 작성지침

    # --------------------------------------------------------

    pdf2 = OFFICIAL_DIR / "개인정보_처리방침_작성지침.pdf"

    if pdf2.exists():

        chunks = create_pdf_chunks(

            pdf_path=pdf2,

            document_name="개인정보 처리방침 작성지침",

            document_id="official_privacy_policy"

        )

        all_chunks.extend(chunks)

    else:

        print(f"[경고] 파일 없음: {pdf2}\n")

    # --------------------------------------------------------

    # 공식자료 3

    # 가명정보 처리 가이드라인

    # --------------------------------------------------------

    pdf3 = OFFICIAL_DIR / "가명정보_처리_가이드라인.pdf"

    if pdf3.exists():

        chunks = create_pdf_chunks(

            pdf_path=pdf3,

            document_name="가명정보 처리 가이드라인",

            document_id="official_pseudonym"

        )

        all_chunks.extend(chunks)

    else:

        print(f"[경고] 파일 없음: {pdf3}\n")

    # --------------------------------------------------------

    # GARIM 가상 사내정책

    # --------------------------------------------------------

    internal_policy = (

        INTERNAL_DIR / "garim_internal_policy_v1.json"

    )

    if internal_policy.exists():

        chunks = create_internal_policy_chunks(

            internal_policy

        )

        all_chunks.extend(chunks)

    else:

        print(

            f"[경고] 사내정책 파일 없음: "

            f"{internal_policy}\n"

        )

    # --------------------------------------------------------

    # output 폴더 생성

    # --------------------------------------------------------

    OUTPUT_DIR.mkdir(

        parents=True,

        exist_ok=True

    )

    # --------------------------------------------------------

    # chunks.json 저장

    # --------------------------------------------------------

    with open(

        OUTPUT_FILE,

        "w",

        encoding="utf-8"

    ) as f:

        json.dump(

            all_chunks,

            f,

            ensure_ascii=False,

            indent=2

        )

    # --------------------------------------------------------

    # 결과 출력

    # --------------------------------------------------------

    official_count = sum(

        1

        for chunk in all_chunks

        if chunk["source_type"] == "official"

    )

    internal_count = sum(

        1

        for chunk in all_chunks

        if chunk["source_type"] == "internal_policy"

    )

    print("=" * 60)

    print("Chunk 생성 완료")

    print("=" * 60)

    print(f"공식자료 Chunk : {official_count}개")

    print(f"사내정책 Chunk : {internal_count}개")

    print(f"전체 Chunk     : {len(all_chunks)}개")

    print()

    print(f"저장 위치:")

    print(OUTPUT_FILE)

# ============================================================

# 프로그램 시작

# ============================================================

if __name__ == "__main__":

    build_chunks()
