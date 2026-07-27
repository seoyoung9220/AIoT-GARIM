import os
import json
import time

import psycopg2
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector

from embedding import get_embedding


# ============================================================
# 환경변수
# ============================================================

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")


# ============================================================
# PostgreSQL 연결
# ============================================================

def get_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

    register_vector(conn)

    return conn


# ============================================================
# 이미 저장된 Chunk인지 확인
# ============================================================

def chunk_exists(cursor, chunk_id):
    cursor.execute(
        """
        SELECT 1
        FROM rag_chunks
        WHERE chunk_id = %s
        """,
        (chunk_id,)
    )

    return cursor.fetchone() is not None


# ============================================================
# Chunk 저장
# ============================================================

def save_chunk(cursor, chunk, embedding):
    metadata = chunk.get("metadata", {})

    cursor.execute(
        """
        INSERT INTO rag_chunks (
            chunk_id,
            source_type,
            document,
            page,
            content,
            pii_type,
            target,
            action,
            embedding
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s
        )

        ON CONFLICT (chunk_id)
        DO UPDATE SET
            source_type = EXCLUDED.source_type,
            document = EXCLUDED.document,
            page = EXCLUDED.page,
            content = EXCLUDED.content,
            pii_type = EXCLUDED.pii_type,
            target = EXCLUDED.target,
            action = EXCLUDED.action,
            embedding = EXCLUDED.embedding
        """,
        (
            chunk["chunk_id"],
            chunk["source_type"],
            chunk["document"],
            chunk.get("page"),
            chunk["content"],
            metadata.get("pii_type"),
            metadata.get("target"),
            metadata.get("action"),
            embedding
        )
    )


# ============================================================
# 사내정책 18개만 저장
# ============================================================

def ingest_chunks():

    # chunks.json 불러오기
    with open(
        "output/chunks.json",
        "r",
        encoding="utf-8"
    ) as f:
        chunks = json.load(f)

    # ------------------------------------------
    # 사내정책만 선택
    # ------------------------------------------

    target_chunks = [
        chunk
        for chunk in chunks
        if chunk["source_type"] == "internal_policy"
    ]

    total = len(target_chunks)

    print()
    print("=" * 60)
    print(f"전체 Chunk 수: {len(chunks)}")
    print(f"사내정책 Chunk 수: {total}")
    print("=" * 60)
    print()

    # DB 연결
    conn = get_connection()
    cursor = conn.cursor()

    success = 0
    skipped = 0
    failed = 0

    try:

        for index, chunk in enumerate(
            target_chunks,
            start=1
        ):

            chunk_id = chunk["chunk_id"]

            print(
                f"[{index}/{total}] {chunk_id}"
            )

            # ------------------------------------------
            # 이미 DB에 있으면 SKIP
            # ------------------------------------------

            if chunk_exists(cursor, chunk_id):

                print("  이미 저장됨 → SKIP")
                print()

                skipped += 1

                continue

            # ------------------------------------------
            # CLOVA Embedding 요청
            # ------------------------------------------

            embedding = None

            for attempt in range(1, 6):

                print(
                    f"  CLOVA Embedding 요청 "
                    f"(시도 {attempt}/5)..."
                )

                embedding = get_embedding(
                    chunk["content"]
                )

                if embedding is not None:
                    break

                # 실패 시 재시도 대기
                wait_time = attempt * 10

                print(
                    f"  요청 실패 → "
                    f"{wait_time}초 대기"
                )

                time.sleep(wait_time)

            # ------------------------------------------
            # 5회 모두 실패
            # ------------------------------------------

            if embedding is None:

                print("  최종 실패")
                print()

                failed += 1

                continue

            # ------------------------------------------
            # DB 저장
            # ------------------------------------------

            save_chunk(
                cursor,
                chunk,
                embedding
            )

            conn.commit()

            success += 1

            print(
                f"  DB 저장 완료 "
                f"({len(embedding)}차원)"
            )

            print()

            # Rate Limit 방지
            time.sleep(1)

    except KeyboardInterrupt:

        print()
        print("작업이 중단되었습니다.")

        conn.commit()

    except Exception as e:

        conn.rollback()

        print()
        print("오류 발생:")
        print(e)

    finally:

        cursor.close()
        conn.close()

    # ------------------------------------------
    # 결과
    # ------------------------------------------

    print()
    print("=" * 60)
    print("작업 완료")
    print(f"대상     : {total}")
    print(f"새로 저장: {success}")
    print(f"SKIP     : {skipped}")
    print(f"실패     : {failed}")
    print("=" * 60)


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":
    ingest_chunks()
