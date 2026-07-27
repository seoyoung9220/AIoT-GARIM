import json


INPUT_PATH = "output/policy_guide_chunks.json"
OUTPUT_PATH = "output/policy_guide_sampled.json"

SAMPLE_SIZE = 150


with open(INPUT_PATH, "r", encoding="utf-8") as f:
    chunks = json.load(f)


total = len(chunks)

print(f"전체 Chunk: {total}")


# 365개 이하라면 전부 사용
if total <= SAMPLE_SIZE:
    sampled = chunks

else:
    # 문서 처음부터 끝까지 균등하게 선택
    indices = [
        round(i * (total - 1) / (SAMPLE_SIZE - 1))
        for i in range(SAMPLE_SIZE)
    ]

    sampled = [
        chunks[index]
        for index in indices
    ]


with open(
    OUTPUT_PATH,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        sampled,
        f,
        ensure_ascii=False,
        indent=2
    )


print(f"선택 Chunk: {len(sampled)}")
print(f"저장 위치: {OUTPUT_PATH}")

print()
print("첫 Chunk:")
print(sampled[0]["chunk_id"], "page", sampled[0]["page"])

print()
print("마지막 Chunk:")
print(sampled[-1]["chunk_id"], "page", sampled[-1]["page"])
