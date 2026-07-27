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

INPUT_PATH = "output/policy_guide_sampled.json"


# ============================================================
# DB 연결
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
# DB 저장
# ============================================================

def save_chunk(cursor, chunk, embedding):

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
            embedding = EXCLUDED.embedding
        """,
        (
            chunk["chunk_id"],
            chunk["source_type"],
            chunk["document"],
            chunk.get("page"),
            chunk["content"],
            None,
            None,
            None,
            embedding
        )
    )


# ============================================================
# 작성지침 150개 저장
# ============================================================

def insert_policy_guide():

    with open(
        INPUT_PATH,
        "r",
        encoding="utf-8"
    ) as f:
        chunks = json.load(f)

    total = len(chunks)

    print()
    print("=" * 60)
    print("개인정보 처리방침 작성지침 DB 추가")
    print(f"대상 Chunk: {total}")
    print("=" * 60)
    print()

    conn = get_connection()
    cursor = conn.cursor()

    success = 0
    skipped = 0
    failed = 0

    try:

        for index, chunk in enumerate(chunks, start=1):

            chunk_id = chunk["chunk_id"]

            print(f"[{index}/{total}] {chunk_id}")

            # 이미 DB에 있으면 건너뛰기
            if chunk_exists(cursor, chunk_id):

                print("  이미 저장됨 -> SKIP")
                skipped += 1
                continue

            embedding = None

            # 최대 5번 재시도
            for attempt in range(1, 6):

                print(
                    f"  Embedding 요청 "
                    f"({attempt}/5)"
                )

                embedding = get_embedding(
                    chunk["content"]
                )

                if embedding is not None:
                    break

                wait_time = attempt * 10

                print(
                    f"  실패 -> {wait_time}초 대기"
                )

                time.sleep(wait_time)

            if embedding is None:

                print("  최종 실패")
                failed += 1
                continue

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

            # Rate Limit 방지
            time.sleep(1)

    except KeyboardInterrupt:

        print()
        print("작업 중단")

        conn.commit()

    except Exception as e:

        conn.rollback()

        print()
        print("오류 발생:")
        print(e)

    finally:

        cursor.close()
        conn.close()

    print()
    print("=" * 60)
    print("완료")
    print(f"대상 : {total}")
    print(f"성공 : {success}")
    print(f"SKIP : {skipped}")
    print(f"실패 : {failed}")
    print("=" * 60)


if __name__ == "__main__":
    insert_policy_guide()
