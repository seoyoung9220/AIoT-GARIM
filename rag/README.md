# GARIM RAG Module

GARIM의 RAG 모듈은 문서에서 탐지된 개인정보를 LLM이 어떻게 처리할지 판단할 수 있도록  
**사내 보안정책과 개인정보보호 관련 공식자료를 검색하여 근거를 제공하는 모듈**입니다.

## 역할설명

전체 GARIM 처리 과정에서 RAG는 다음 위치를 담당합니다.

```text
문서 업로드
    ↓
OCR
    ↓
개인정보 탐지
    ↓
개인정보 유형 + 공유 대상
    ↓
[RAG]
관련 사내정책 및 공식자료 검색
    ↓
[LLM]
유지 / 부분 마스킹 / 제거 판단
    ↓
마스킹 처리
```

RAG 자체가 최종 마스킹을 수행하는 것은 아닙니다.

RAG는 LLM이 판단할 때 참고할 수 있도록  
**관련 정책과 공식 근거를 검색해서 전달하는 역할**을 합니다.

---

## 현재 사용 데이터

### 사내정책

GARIM 프로젝트에서 테스트하기 위해 제작한 가상의 사내 문서 공유 보안정책입니다.

위치:

```text
data/internal/garim_internal_policy_v1.json
```

개인정보 유형과 공유 대상에 따라 처리 정책을 정의합니다.

예:

```text
개인정보 유형: phone
공유 대상: partner
처리 방법: partial
```

즉, 협력사에 전화번호가 포함된 문서를 공유하는 경우  
전화번호를 부분 마스킹하도록 하는 정책입니다.

### 공식자료

개인정보보호 관련 공식 문서를 RAG 검색 근거로 사용합니다.

```text
data/official/
├── 개인정보_처리_통합안내서.pdf
└── 개인정보_처리방침_작성지침.pdf
```

PDF에서 텍스트를 추출하고 Chunk 단위로 분할한 뒤 Embedding하여 Vector DB에 저장합니다.

---

## RAG 검색 방식

RAG 검색은 크게 두 가지 방식으로 구성되어 있습니다.

### 1. 사내정책 검색

사내정책은 의미 유사도 검색보다 정확한 정책 적용이 중요하기 때문에

```text
pii_type + target
```

조건을 기준으로 검색합니다.

예:

```text
phone + partner
```

검색 결과:

```text
GARIM-PHONE-PARTNER
action = partial
```

### 2. 공식자료 검색

공식자료는 CLOVA Embedding과 pgvector를 이용하여 의미 기반 Vector Search를 수행합니다.

예를 들어

```text
pii_type = phone
target = partner
```

가 입력되면 검색용 Query를 다음과 같이 확장합니다.

```text
전화번호 연락처 개인정보를
협력사 제3자 제공 목적으로 제공하거나 공유할 때
개인정보 처리 보호 비식별화 마스킹 관련 기준
```

이 Query와 의미적으로 가까운 공식자료 Chunk를 검색하여 현재 **Top-5**를 반환합니다.

---

## 주요 파일

```text
rag/
├── embedding.py
├── retriever.py
├── rag_pipeline.py
│
├── data/
│   ├── internal/
│   │   └── garim_internal_policy_v1.json
│   │
│   └── official/
│       ├── 개인정보_처리_통합안내서.pdf
│       └── 개인정보_처리방침_작성지침.pdf
│
└── scripts/
    ├── chunk.py
    ├── vector_store.py
    ├── chunk_policy_guide.py
    ├── sample_policy_guide.py
    └── insert_policy_guide.py
```

각 파일의 역할은 다음과 같습니다.

| 파일 | 역할 |
|---|---|
| `rag_pipeline.py` | 다른 모듈에서 RAG를 호출하기 위한 메인 인터페이스 |
| `retriever.py` | 사내정책 및 공식자료 검색 |
| `embedding.py` | CLOVA Embedding API 연동 |
| `data/internal/` | GARIM 가상 사내정책 |
| `data/official/` | RAG에 사용한 공식 정책 자료 |
| `scripts/` | Chunk 생성 및 Vector DB 구축용 스크립트 |

---

## 사용 방법

프로젝트 루트에서 다음과 같이 호출합니다.

```python
from rag.rag_pipeline import run_rag

result = run_rag(
    pii_type="phone",
    target="partner"
)

rag_results = result["rag_results"]
```

현재 `target`은 문자열로 전달합니다.

```text
internal
partner
public
```

`pii_type` 역시 문자열을 사용합니다.

예:

```text
name
phone
address
resident_no
business_no
account
```

---

## 반환 데이터

예시:

```json
{
  "pii_type": "phone",
  "target": "partner",
  "rag_results": {
    "internal_policy": {
      "chunk_id": "GARIM-PHONE-PARTNER",
      "content": "...",
      "metadata": {
        "pii_type": "phone",
        "target": "partner",
        "action": "partial"
      }
    },
    "official_evidence": [
      {
        "document": "개인정보 처리 통합 안내서",
        "page": 70,
        "content": "...",
        "similarity": 0.9899
      }
    ]
  }
}
```

LLM에서는 주로 다음 데이터를 참고할 수 있습니다.

```text
internal_policy.metadata.action
→ 사내정책상 권장 처리 방법

internal_policy.content
→ 사내정책 근거

official_evidence[].content
→ 개인정보보호 관련 공식자료 근거
```

이를 바탕으로 LLM이 최종적으로 개인정보 항목별

```text
유지
부분 마스킹
제거
```

등의 처리 방법을 판단합니다.

---

## Vector DB

Embedding된 정책 Chunk는 PostgreSQL + pgvector를 이용하여 관리합니다.

```text
정책 PDF / 사내정책
        ↓
Chunking
        ↓
CLOVA Embedding
        ↓
PostgreSQL + pgvector
        ↓
관련 정책 검색
        ↓
LLM Context 제공
```

DB 접속 정보와 API Key 등 민감한 정보는 `.env`에서 관리하며 GitHub에는 업로드하지 않습니다.

---

## 현재 구현 상태

- 사내정책 데이터 구축
- 공식 정책자료 Chunking
- CLOVA Embedding 연동
- PostgreSQL + pgvector 저장
- 개인정보 유형 및 공유 대상 기반 사내정책 검색
- 공식자료 Vector Search
- 공식자료 Top-5 검색
- LLM 전달용 `run_rag()` 인터페이스 구현
- `phone + partner` 등의 검색 테스트 완료

현재 RAG 모듈은 **LLM의 마스킹 정책 판단을 위한 근거 검색 모듈**로 사용할 수 있습니다.
