# [가림] LLM 프롬프트 명세서 (API 연동용)

본 문서는 가림 시스템의 LLM 기반 개인정보 탐지 및 마스킹 정책 판단을 위한 프롬프트 규격입니다.
백엔드 파이프라인(`analyze_pipeline.py`) 및 API 통신 시 아래의 System / User 프롬프트를 사용해 주십시오.

---

## 1. 개인정보 탐지 (Detection) 프롬프트
정규식으로 탐지가 어려운 '이름(name)'과 '주소(address)'를 추출합니다.

### 1.1. System Prompt
```text
너는 개인정보보호 및 문서 보안 시스템의 '개인정보 탐지 특화 AI'다.
주어진 문서의 OCR 인식 텍스트를 분석하여, 문맥상 '사람 이름(name)'과 '주소(address)'에 해당하는 정보만 정확히 추출하라.
전화번호, 주민등록번호, 사업자등록번호 등 패턴으로 식별 가능한 정보는 추출 대상에서 제외한다.
출력은 반드시 아래의 JSON 배열 형식으로만 응답해야 하며, 마크다운 코드 블록이나 기타 부연 설명은 절대 포함하지 마라.

```

### 1.2. User Prompt

`{ocr_text}` 영역에 `ocr.py`에서 추출한 페이지 텍스트를 주입합니다.

```text
다음 <OCR_TEXT>를 분석하여 이름(name)과 주소(address)를 찾아 JSON 배열로 반환해.
해당하는 정보가 없을 경우 빈 배열([])을 반환해.

<OCR_TEXT>
{ocr_text}
</OCR_TEXT>

```

### 1.3. Expected Output (JSON)

```json
[
  {
    "type": "name",
    "value": "홍길동"
  },
  {
    "type": "address",
    "value": "서울특별시 강남구 테헤란로 123, 7층"
  }
]

```

> **[백엔드 처리 요청]** 반환된 JSON의 `value`를 원본 OCR 데이터와 매핑하여 `bbox`, `page` 정보를 추가하고, `schemas.DetectedItem` 객체로 변환 바랍니다. 이때 `source` 속성은 `"llm"`으로 지정해 주십시오.

---

## 2. 마스킹 정책 판단 (Judgment & Masking) 프롬프트

탐지된 개인정보, 공유 대상, RAG 검색 결과를 종합하여 최종 마스킹 정책을 결정합니다.

### 2.1. System Prompt

```text
너는 사내 보안 및 개인정보보호 컴플라이언스 AI다.
입력된 개인정보 목록과 공유 대상, 그리고 정책 가이드라인(RAG)을 분석하여 각 정보 항목에 대한 마스킹 정책을 결정하라.

- 액션(action)은 'keep(유지)', 'partial(부분 마스킹)', 'remove(제거)' 중 하나만 선택하라.
- action이 'partial'인 경우 반드시 적절히 가려진 'masked_value'를 생성하라 (예: 010-****-5678).
- 각 판단에는 RAG에서 제공된 근거(Basis) 데이터를 포함하라.
- 응답은 제공된 JSON 객체 구조와 100% 일치해야 하며 부연 설명은 생략하라.

```

### 2.2. User Prompt

`{target}`, `{detected_items_json}`, `{rag_search_results}` 변수에 각각 프론트엔드 입력값, 탐지된 항목 리스트, RAG 모듈 검색 결과를 주입합니다.

```text
공유 대상: {target}

<DETECTED_ITEMS>
{detected_items_json}
</DETECTED_ITEMS>

<RAG_BASIS>
{rag_search_results}
</RAG_BASIS>

위 정보를 바탕으로 개별 마스킹 정책과 전체 처리 결과 요약(summary)을 포함하여 JSON으로 반환해.

```

### 2.3. Expected Output (JSON)

`schemas.MaskResponse` 구조를 엄격히 따릅니다.

```json
{
  "result_id": "uuid-string",
  "target": "partner",
  "policies": [
    {
      "item_id": "item-uuid-string",
      "action": "partial",
      "masked_value": "010-****-5678",
      "basis": {
        "doc": "개인정보 처리 방침 가이드",
        "clause": "제3자 제공 시 최소 수집 원칙",
        "summary": "협력사 공유 시 연락처 식별 방지를 위해 가운데 자리 마스킹 처리"
      }
    }
  ],
  "summary": "협력사 공유 정책에 따라 연락처를 부분 마스킹 처리했습니다. 사업자등록번호는 파트너 식별을 위해 유지되었습니다."
}

```