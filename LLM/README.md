# LLM Module

## Overview

LLM 모듈은 OCR 및 Regex를 통해 탐지된 개인정보에 대해
RAG 검색 결과와 LLM(HCX-007)을 이용하여 최종 마스킹 정책을 생성한다.

동작 순서는 다음과 같다.

```
OCR / Regex
      │
      ▼
DetectedItem
      │
      ▼
RAG 검색
      │
      ▼
HCX-007
      │
      ▼
MaskingPolicy 반환
```

---

## Directory

```
LLM/
├── llm_client.py      # HCX-007 API 호출
├── reasoning.py       # RAG + LLM 정책 생성
└── README.md
```

---

## Features

### 1. 개인정보 탐지 결과 기반 정책 생성

입력으로 전달된 `DetectedItem`과 문서 공개 대상을 기반으로
RAG에서 관련 정책을 검색한 후 LLM이 최종 마스킹 정책을 생성한다.

---

### 2. RAG 연동

`reasoning.py`

```python
rag_result = run_rag(
    pii_type=item.type,
    target=target,
)
```

검색된 정책을 LLM Prompt에 포함하여
조직 정책에 맞는 마스킹 방식을 결정한다.

---

### 3. LLM Policy Decision

LLM은 다음 정보를 기반으로 판단한다.

- 개인정보 종류
- 개인정보 값
- 문서 공개 대상
- RAG 검색 결과

출력은 `MaskingPolicy` 객체이다.

예시

```python
MaskingPolicy(
    item_id="1",
    action="remove",
    masked_value="",
    basis=Basis(...)
)
```

---

## Environment Variables

`.env`

```env
CLOVA_STUDIO_KEY=YOUR_API_KEY
```

---

## Main Functions

### detect_pii()

LLM을 이용하여 개인정보 유형을 판별한다.

```python
client.detect_pii(text)
```

---

### decide_policy()

RAG 결과를 포함하여
최종 마스킹 정책을 생성한다.

```python
client.decide_policy(
    target,
    detected_item,
    rag_results
)
```

---

### generate_policy()

RAG 검색과 LLM 호출을 하나의 함수로 수행한다.

```python
policy = generate_policy(item, target)
```

---

### generate_policies()

여러 개인정보 항목에 대해 정책을 생성한다.

```python
policies = generate_policies(items, target)
```

---

## Execution Flow

```
DetectedItem
      │
      ▼
generate_policy()
      │
      ▼
run_rag()
      │
      ▼
Embedding 생성
      │
      ▼
PostgreSQL(pgvector) 검색
      │
      ▼
관련 정책 반환
      │
      ▼
HCX-007 호출
      │
      ▼
MaskingPolicy 생성
```

---

## Test

### Policy Test

```bash
python3 test_policy.py
```

예시 출력

```
item_id='1'
action='partial'
masked_value='홍*'
```

---

### Reasoning Test

```bash
python3 test_reasoning.py
```

정상 동작 시

```
RAG 검색 시작
Embedding 생성 완료 (1024차원)

item_id='1'
action='remove'
masked_value=''
```

---

## Dependencies

- HCX-007
- CLOVA Embedding API
- PostgreSQL (pgvector)
- RAG Module

---

## Author

LLM Module
- 개인정보 마스킹 정책 생성
- HCX-007 연동
- RAG 기반 정책 결정