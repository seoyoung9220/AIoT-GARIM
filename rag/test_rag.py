from .rag_pipeline import run_rag


# ============================================================
# RAG 테스트 케이스
# ============================================================

TEST_CASES = [
    {
        "pii_type": "phone",
        "target": "partner"
    },
    {
        "pii_type": "resident_no",
        "target": "public"
    },
    {
        "pii_type": "name",
        "target": "internal"
    },
    {
        "pii_type": "address",
        "target": "partner"
    },
    {
        "pii_type": "business_no",
        "target": "public"
    }
]


# ============================================================
# 테스트 실행
# ============================================================

def run_tests():

    print("=" * 70)
    print("GARIM RAG TEST")
    print("=" * 70)

    success = 0
    failed = 0

    for index, case in enumerate(TEST_CASES, start=1):

        pii_type = case["pii_type"]
        target = case["target"]

        print()
        print("=" * 70)
        print(
            f"[TEST {index}/{len(TEST_CASES)}] "
            f"{pii_type} + {target}"
        )
        print("=" * 70)

        try:

            result = run_rag(
                pii_type=pii_type,
                target=target
            )

            rag_results = result.get(
                "rag_results",
                {}
            )

            # ------------------------------------------------
            # 사내정책
            # ------------------------------------------------

            internal = rag_results.get(
                "internal_policy"
            )

            print()
            print("[사내정책]")

            if internal:

                print(
                    "chunk_id :",
                    internal.get("chunk_id")
                )

                metadata = internal.get(
                    "metadata",
                    {}
                )

                print(
                    "action   :",
                    metadata.get("action")
                )

                print(
                    "content  :",
                    internal.get("content")
                )

            else:

                print("검색 결과 없음")

            # ------------------------------------------------
            # 공식자료
            # ------------------------------------------------

            official = rag_results.get(
                "official_evidence",
                []
            )

            print()
            print(
                f"[공식자료 검색 결과: {len(official)}개]"
            )

            for rank, item in enumerate(
                official,
                start=1
            ):

                print()
                print(f"TOP {rank}")

                print(
                    "document   :",
                    item.get("document")
                )

                print(
                    "page       :",
                    item.get("page")
                )

                print(
                    "similarity :",
                    item.get("similarity")
                )

                content = item.get(
                    "content",
                    ""
                )

                # 너무 길게 출력되는 것을 방지
                if len(content) > 200:
                    content = content[:200] + "..."

                print(
                    "content    :",
                    content
                )

            # ------------------------------------------------
            # 기본 성공 여부
            # ------------------------------------------------

            if internal and official:

                print()
                print("RESULT: PASS")
                success += 1

            else:

                print()
                print("RESULT: CHECK")
                failed += 1

        except Exception as e:

            print()
            print("RESULT: ERROR")
            print("ERROR :", e)

            failed += 1

    # ========================================================
    # 최종 결과
    # ========================================================

    print()
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    print("전체 :", len(TEST_CASES))
    print("PASS :", success)
    print("CHECK/ERROR :", failed)

    print("=" * 70)


if __name__ == "__main__":
    run_tests()
