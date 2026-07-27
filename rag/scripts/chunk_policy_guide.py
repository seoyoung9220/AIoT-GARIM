import json
import fitz
from pathlib import Path


# ============================================================
# 설정
# ============================================================

PDF_PATH = Path(
    "data/official/개인정보_처리방침_작성지침.pdf"
)

OUTPUT_PATH = Path(
    "output/policy_guide_chunks.json"
)

DOCUMENT_NAME = "개인정보 처리방침 작성지침"

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


# ============================================================
# 텍스트 정리
# ============================================================

def clean_text(text):
    """
    PDF에서 추출한 텍스트의 불필요한 공백을 정리한다.
    """

    text = text.replace("\x00", "")
    text = text.replace("\r", "\n")

    lines = []

    for line in text.split("\n"):
        line = line.strip()

        if line:
            lines.append(line)

    return "\n".join(lines)


# ============================================================
# 텍스트 Chunking
# ============================================================

def split_text(text):
    """
    CHUNK_SIZE 기준으로 텍스트를 나눈다.
    이전 Chunk의 일부를 CHUNK_OVERLAP만큼 겹친다.
    """

    chunks = []

    start = 0
    text_length = len(text)

    while start < text_length:

        end = start + CHUNK_SIZE

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= text_length:
            break

        start = end - CHUNK_OVERLAP

    return chunks


# ============================================================
# PDF → Chunk
# ============================================================

def create_chunks():

    if not PDF_PATH.exists():
        print(f"PDF 파일을 찾을 수 없습니다: {PDF_PATH}")
        return []

    print("=" * 60)
    print("개인정보 처리방침 작성지침 Chunk 생성")
    print("=" * 60)
    print()
    print(f"PDF: {PDF_PATH}")
    print(f"Chunk Size: {CHUNK_SIZE}")
    print(f"Overlap: {CHUNK_OVERLAP}")
    print()

    pdf = fitz.open(PDF_PATH)

    results = []

    chunk_number = 1

    for page_index in range(len(pdf)):

        page = pdf[page_index]

        text = page.get_text("text")

        text = clean_text(text)

        # 텍스트가 없는 페이지는 건너뜀
        if not text:
            continue

        page_chunks = split_text(text)

        for content in page_chunks:

            chunk = {
                "chunk_id": (
                    f"official_policy_guide_{chunk_number}"
                ),
                "source_type": "official",
                "document": DOCUMENT_NAME,
                "page": page_index + 1,
                "content": content,
                "metadata": {}
            }

            results.append(chunk)

            chunk_number += 1

    pdf.close()

    return results


# ============================================================
# JSON 저장
# ============================================================

def save_chunks(chunks):

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            chunks,
            f,
            ensure_ascii=False,
            indent=2
        )

    print()
    print("=" * 60)
    print("Chunk 생성 완료")
    print("=" * 60)

    print(f"문서: {DOCUMENT_NAME}")
    print(f"생성 Chunk: {len(chunks)}")
    print(f"저장 위치: {OUTPUT_PATH}")


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":

    chunks = create_chunks()

    if chunks:
        save_chunks(chunks)
