import os
import json

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
# RAG 정책 검색
# ============================================================

def search_policy(
    query,
    pii_type,
    target,
    official_top_k=2
):

    print()
    print("=" * 60)
    print("RAG 검색 시작")
    print("=" * 60)

    print(f"Query    : {query}")
    print(f"PII Type : {pii_type}")
    print(f"Target   : {target}")

    # --------------------------------------------------------
    # Query Embedding
    # --------------------------------------------------------

    print()
    print("Query Embedding 생성 중...")

    query_embedding = get_embedding(query)

    if query_embedding is None:

        print("Embedding 생성 실패")

        return {
            "internal_policy": None,
            "official_evidence": []
        }

    print(
        f"Embedding 생성 완료 "
        f"({len(query_embedding)}차원)"
    )

    conn = get_connection()
    cursor = conn.cursor()

    try:

        # ====================================================
        # 1. 사내정책 검색
        #
        # pii_type + target이 정확하게 일치하는 정책 검색
        # ====================================================

        cursor.execute(
            """
            SELECT
                chunk_id,
                source_type,
                document,
                page,
                content,
                pii_type,
                target,
                action

            FROM rag_chunks

            WHERE source_type = 'internal_policy'
              AND pii_type = %s
              AND target = %s

            LIMIT 1
            """,
            (
                pii_type,
                target
            )
        )

        internal_row = cursor.fetchone()

        internal_policy = None

        if internal_row:

            internal_policy = {
                "chunk_id": internal_row[0],
                "source_type": internal_row[1],
                "document": internal_row[2],
                "page": internal_row[3],
                "content": internal_row[4],
                "metadata": {
                    "pii_type": internal_row[5],
                    "target": internal_row[6],
                    "action": internal_row[7]
                }
            }

        # ====================================================
        # 2. 공식자료 Vector Search
        #
        # 공식 정책자료 중 관련 근거 검색
        # ====================================================

        cursor.execute(
            """
            SELECT
                chunk_id,
                source_type,
                document,
                page,
                content,
                1 - (embedding <=> %s::vector)
                    AS similarity

            FROM rag_chunks

            WHERE source_type = 'official'

            ORDER BY embedding <=> %s::vector

            LIMIT %s
            """,
            (
                query_embedding,
                query_embedding,
                official_top_k
            )
        )

        official_rows = cursor.fetchall()

        official_results = []

        for row in official_rows:

            official_results.append(
                {
                    "chunk_id": row[0],
                    "source_type": row[1],
                    "document": row[2],
                    "page": row[3],
                    "content": row[4],
                    "similarity": round(
                        float(row[5]),
                        4
                    )
                }
            )

        # ====================================================
        # 최종 RAG 결과
        # ====================================================

        return {
            "internal_policy": internal_policy,
            "official_evidence": official_results
        }

    finally:

        cursor.close()
        conn.close()


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":

    result = search_policy(
        query=(
            "협력사에 전화번호가 포함된 "
            "문서를 공유할 때 처리 방법"
        ),
        pii_type="phone",
        target="partner",
        official_top_k=2
    )

    print()
    print("=" * 60)
    print("최종 RAG 결과")
    print("=" * 60)

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        )
    )
