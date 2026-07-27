# LLM Module

## Overview

LLM 모듈은 OCR 및 정규식 탐지를 통해 식별된 개인정보와 문서 공개 대상(Target), RAG 검색 결과를 기반으로 최종 개인정보 마스킹 정책을 생성한다.

CLOVA Studio HCX-007 모델을 사용하여 조직의 보안 정책에 맞는 마스킹 방식을 결정하고, `MaskingPolicy` 객체를 반환한다.

---

## Directory Structure

```text
LLM/
├── __init__.py
├── llm_client.py         # HCX-007 API Client
├── prompts.py            # LLM Prompt 생성
├── reasoning.py          # RAG + LLM 연동
├── llm_prompt_spec.md    # Prompt 설계 문서
└── README.md
```

---

## Module Description

### `llm_client.py`

HCX-007 API를 호출하는 모듈이다.

#### 주요 기능

- CLOVA Studio HCX API 호출
- JSON 응답 파싱
- Markdown 코드블록(```json`) 제거
- Pydantic 모델 검증

#### 제공 함수

- `detect_pii_llm()`
- `decide_policy()`

---

### `prompts.py`

LLM Prompt를 생성하는 모듈이다.

Prompt에는 다음 정보가 포함된다.

- 문서 공개 대상(Target)
- 개인정보 정보(DetectedItem)
- RAG 검색 결과

---

### `reasoning.py`

RAG 검색과 LLM 정책 생성을 연결하는 모듈이다.

#### 제공 함수

- `generate_policy()`
- `generate_policies()`

동작 과정

```text
DetectedItem
      │
      ▼
run_rag()
      │
      ▼
HCX-007
      │
      ▼
MaskingPolicy 반환
```

---

## Processing Flow

```text
OCR
      │
      ▼
Regex
      │
      ▼
DetectedItem
      │
      ▼
generate_policy()
      │
      ▼
run_rag()
      │
      ▼
정책 검색
      │
      ▼
HCX-007
      │
      ▼
MaskingPolicy
```

---

## Output

LLM은 최종적으로 `MaskingPolicy` 객체를 반환한다.

```python
MaskingPolicy(
    item_id="1",
    action="partial",
    masked_value="홍*",
    basis=Basis(
        doc="GARIM 개인정보 처리 기준",
        clause="이름",
        summary="외부 공개 문서에서는 이름을 부분 마스킹한다."
    )
)
```

### Action

| 값 | 설명 |
|----|------|
| keep | 원본 유지 |
| partial | 부분 마스킹 |
| remove | 완전 삭제 |

---

## Environment Variables

`.env`

```env
CLOVA_STUDIO_KEY=<YOUR_API_KEY>
```

---

## Dependencies

- Python 3.10+
- requests
- python-dotenv
- pydantic

외부 모듈

- CLOVA Studio HCX-007
- RAG Module

---

## Usage

### 개인정보 1건 정책 생성

```python
from LLM.reasoning import generate_policy

policy = generate_policy(item, target)
```

### 여러 개인정보 정책 생성

```python
from LLM.reasoning import generate_policies

policies = generate_policies(items, target)
```

---

## Integration Flow

```text
OCR
   │
   ▼
Regex
   │
   ▼
DetectedItem
   │
   ▼
RAG
   │
   ▼
LLM
   │
   ▼
MaskingPolicy
   │
   ▼
Backend Response
```

---

## Notes

- 모든 LLM 응답은 JSON 형식으로 반환된다.
- Markdown 코드블록은 제거 후 JSON으로 파싱한다.
- RAG 검색 결과를 기반으로 개인정보 처리 정책을 생성한다.
- 정책 생성 결과는 `MaskingPolicy` Pydantic 모델로 검증한다.
- `LLM/__init__.py`를 포함하여 패키지 형태로 관리한다.