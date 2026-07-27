# 백엔드 테스트

```bash
pip install pytest fastapi httpx python-multipart
cd backend
pytest
```

CLOVA OCR 키나 poppler 설치 없이 돌아간다. 외부 의존만 스텁으로 막고
나머지(PDF 변환 호출, OCR 응답 파싱, 정규식 탐지, bbox 매칭, 마스킹 렌더링,
FastAPI 라우팅)는 실제 코드를 그대로 태운다.

`fastapi`가 없으면 API 테스트만 건너뛰고 나머지는 정상 실행된다.

## 구성

| 파일 | 내용 |
|---|---|
| `fakes.py` | 가짜 문서 픽스처와 외부 의존 스텁 |
| `conftest.py` | 스텁 설치, 임시 출력 폴더, `api` 픽스처 |
| `test_pipeline.py` | `analyze_document` 전 과정 + 탐지/bbox/엣지 케이스 |
| `test_render.py` | 마스킹 그리기, PDF 생성, 한글 폰트 |
| `test_api.py` | `/health` `/analyze` `/mask` `/download` |

## 교차 오염을 잡는 방식

페이지 이미지마다 **고유한 색**을 칠해 두고, OCR 스텁이 그 색으로 "어느 문서의
몇 페이지인지"를 판별한다. 그래서 요청끼리 페이지 이미지를 덮어쓰면 OCR 결과가
다른 문서 내용으로 나오고 테스트가 반드시 깨진다.

동시 요청은 `fakes.barrier`로 두 스레드를 같은 시점에 저장 단계로 밀어넣어
재현한다. 실제로 이 방식으로 아래 두 버그를 잡았다.

- `analyze_document`가 공용 폴더를 쓰던 문제 (`page_1.png` 덮어쓰기)
- `render_analysis`의 `image_output_dir` 기본값이 공용 폴더이던 문제

## 테스트를 추가할 때

새 항목을 탐지 대상에 넣으면 `fakes.DOCS`(페이지 내용)와 `fakes.EXPECTED`
(기대 탐지 결과)를 같이 고쳐야 한다. `EXPECTED`는 집합 비교라 **누락과 오탐을
동시에** 잡는다.
