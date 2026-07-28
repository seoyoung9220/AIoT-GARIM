import { useEffect, useRef, useState } from "react";
import { analyzeDocument, downloadResult, maskDocument } from "./api";
import "./App.css";

const ALLOWED_MIME_TYPES = [
  "application/pdf",
  "image/png",
  "image/jpeg",
];

const ALLOWED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg"];

const MAX_FILE_SIZE = 20 * 1024 * 1024;

const PII_LABELS = {
  name: "이름",
  phone: "전화번호",
  address: "주소",
  account: "계좌번호",
  business_no: "사업자등록번호",
  resident_no: "주민등록번호",
};

const SOURCE_LABELS = {
  regex: "정규식",
  llm: "LLM",
};

const ACTION_LABELS = {
  keep: "유지",
  partial: "부분 마스킹",
  remove: "제거",
};

function hideSensitiveValue(type, value) {
  if (type === "resident_no") {
    return value.replace(/(\d{6})-\d{7}/, "$1-*******");
  }
  if (type === "account") {
    return value.replace(/\d(?=\d{4})/g, "*");
  }
  return value;
}

function App() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [target, setTarget] = useState("internal");
  const [error, setError] = useState("");
  const [isDragging, setIsDragging] = useState(false);

  // 실제 분석 관련 상태
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [excludedIds, setExcludedIds] = useState([]);
  const [maskResult, setMaskResult] = useState(null);
  const [isMasking, setIsMasking] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [previewUrl, setPreviewUrl] = useState("");

  const fileInputRef = useRef(null);
  const dragDepthRef = useRef(0);

  useEffect(() => {
    if (!selectedFile) {
      setPreviewUrl("");
      return;
    }

    const url = URL.createObjectURL(selectedFile);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [selectedFile]);

  function isAllowedFile(file) {
    const lowerName = file.name.toLowerCase();

    const hasAllowedExtension = ALLOWED_EXTENSIONS.some((extension) =>
      lowerName.endsWith(extension)
    );

    const hasAllowedMimeType = ALLOWED_MIME_TYPES.includes(file.type);

    return hasAllowedExtension || hasAllowedMimeType;
  }

  function processFile(file) {
    if (!file) {
      return;
    }

    if (!isAllowedFile(file)) {
      setSelectedFile(null);
      setAnalysisResult(null);
      setError("PDF, PNG, JPG 파일만 업로드할 수 있습니다.");

      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }

      return;
    }

    if (file.size > MAX_FILE_SIZE) {
      setSelectedFile(null);
      setAnalysisResult(null);
      setError("파일 크기는 20MB 이하여야 합니다.");

      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }

      return;
    }

    setSelectedFile(file);
    setAnalysisResult(null);
    setExcludedIds([]);
    setMaskResult(null);
    setUploadProgress(0);
    setError("");
  }

  function handleFileChange(event) {
    const file = event.target.files?.[0];
    processFile(file);
  }

  function handleSelectButtonClick() {
    fileInputRef.current?.click();
  }

  function handleRemoveFile() {
    setSelectedFile(null);
    setAnalysisResult(null);
    setExcludedIds([]);
    setMaskResult(null);
    setUploadProgress(0);
    setError("");

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  function handleDragEnter(event) {
    event.preventDefault();
    event.stopPropagation();

    dragDepthRef.current += 1;
    setIsDragging(true);
  }

  function handleDragOver(event) {
    event.preventDefault();
    event.stopPropagation();

    event.dataTransfer.dropEffect = "copy";
  }

  function handleDragLeave(event) {
    event.preventDefault();
    event.stopPropagation();

    dragDepthRef.current -= 1;

    if (dragDepthRef.current <= 0) {
      dragDepthRef.current = 0;
      setIsDragging(false);
    }
  }

  function handleDrop(event) {
    event.preventDefault();
    event.stopPropagation();

    dragDepthRef.current = 0;
    setIsDragging(false);

    const files = event.dataTransfer.files;

    if (!files || files.length === 0) {
      return;
    }

    if (files.length > 1) {
      setError("파일은 한 번에 하나만 업로드할 수 있습니다.");
      return;
    }

    processFile(files[0]);
  }

  function getRequestErrorMessage(requestError) {
    const detail = requestError.response?.data?.detail;

    if (typeof detail === "string") {
      return detail;
    }

    if (Array.isArray(detail)) {
      return detail
        .map((item) => item.msg || JSON.stringify(item))
        .join(", ");
    }

    if (requestError.code === "ERR_NETWORK") {
      return "백엔드 서버에 연결할 수 없습니다. 서버 실행 상태와 CORS 설정을 확인해주세요.";
    }

    return "문서 분석 중 오류가 발생했습니다.";
  }

  async function handleAnalyze() {
    if (!selectedFile) {
      setError("분석할 파일을 먼저 선택해주세요.");
      return;
    }

    try {
      setError("");
      setAnalysisResult(null);
      // 이전 마스킹 결과는 방금 지운 분석 결과에 딸린 것이라 같이 비운다.
      // 남겨두면 분석이 끝나기 전까지 "분석 결과는 없는데 마스킹 결과만 있는"
      // 상태가 되어, 결과 표가 사라진 항목을 참조하다 화면이 통째로 죽는다.
      setMaskResult(null);
      setExcludedIds([]);
      setUploadProgress(0);
      setIsAnalyzing(true);

      const result = await analyzeDocument(
        selectedFile,
        setUploadProgress
      );

      setAnalysisResult(result);
      setExcludedIds([]);
    } catch (requestError) {
      console.error("문서 분석 오류:", requestError);
      setError(getRequestErrorMessage(requestError));
    } finally {
      setIsAnalyzing(false);
    }
  }

  function toggleItem(id) {
    setExcludedIds((ids) =>
      ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id]
    );
  }

  function toggleAllItems() {
    const items = analysisResult.items || [];
    setExcludedIds(excludedIds.length ? [] : items.map((item) => item.id));
  }

  async function handleMask() {
    try {
      setError("");
      setIsMasking(true);
      setMaskResult(
        await maskDocument(analysisResult.analysis_id, target, excludedIds)
      );
    } catch (requestError) {
      setError(getRequestErrorMessage(requestError));
    } finally {
      setIsMasking(false);
    }
  }

  async function handleDownload() {
    try {
      setError("");
      setIsDownloading(true);
      const blob = await downloadResult(maskResult.result_id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `garim-${maskResult.result_id}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (requestError) {
      setError(getRequestErrorMessage(requestError));
    } finally {
      setIsDownloading(false);
    }
  }

  return (
    <main className="app">
      <header className="service-header">
        <img
          className="service-logo"
          src="/Garim.png"
          alt="GARIM 로고"
        />

        <h1>AI 문서 보안 및 차등 마스킹</h1>

        <p>
          문서를 업로드하고 공유 대상을 선택하면 개인정보를 탐지하여 안전한
          공유 문서를 생성합니다.
        </p>
      </header>

      <section className="card">
        <div className="step-title">
          <span className="step-number">1</span>

          <div>
            <h2>문서 업로드</h2>
            <p>분석할 PDF 또는 이미지 파일을 선택해주세요.</p>
          </div>
        </div>

        <div
          className={`upload-box ${isDragging ? "dragging" : ""}`}
          onDragEnter={handleDragEnter}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <div className="upload-icon">↑</div>

          <strong>
            {isDragging
              ? "이곳에 파일을 놓으세요"
              : "파일을 이 영역으로 드래그하세요"}
          </strong>

          <small>PDF, PNG, JPG / 최대 20MB</small>

          <button
            type="button"
            className="select-file-button"
            onClick={handleSelectButtonClick}
            disabled={isAnalyzing}
          >
            파일 선택
          </button>

          <input
            ref={fileInputRef}
            className="hidden-file-input"
            type="file"
            accept=".pdf,.png,.jpg,.jpeg"
            onChange={handleFileChange}
          />
        </div>

        {selectedFile && (
          <div className="file-info">
            <div className="file-name-area">
              <strong>선택된 파일</strong>
              <p title={selectedFile.name}>{selectedFile.name}</p>
            </div>

            <div className="file-action-area">
              <span>
                {(selectedFile.size / 1024 / 1024).toFixed(2)}MB
              </span>

              <button
                type="button"
                className="remove-file-button"
                onClick={handleRemoveFile}
                disabled={isAnalyzing}
              >
                선택 삭제
              </button>
            </div>
          </div>
        )}

        {isAnalyzing && (
          <div className="progress-area">
            <div className="progress-header">
              <strong>문서를 분석하고 있습니다.</strong>
              <span>{uploadProgress}%</span>
            </div>

            <progress value={uploadProgress} max="100" />

            <p>
              파일 업로드 후 OCR 및 개인정보 탐지에 시간이 걸릴 수 있습니다.
            </p>
          </div>
        )}

        {error && <div className="error-message">{error}</div>}
      </section>

      <section className="card">
        <div className="step-title">
          <span className="step-number">2</span>

          <div>
            <h2>공유 대상 선택</h2>
            <p>문서를 누구에게 공유할 것인지 선택해주세요.</p>
          </div>
        </div>

        <div className="target-list">
          <label
            className={`target-card ${
              target === "internal" ? "selected" : ""
            }`}
          >
            <input
              type="radio"
              name="target"
              value="internal"
              checked={target === "internal"}
              onChange={(event) => setTarget(event.target.value)}
              disabled={isAnalyzing}
            />

            <div>
              <strong>내부 공유</strong>
              <p>회사 내부 업무 목적으로 공유합니다.</p>
            </div>
          </label>

          <label
            className={`target-card ${
              target === "partner" ? "selected" : ""
            }`}
          >
            <input
              type="radio"
              name="target"
              value="partner"
              checked={target === "partner"}
              onChange={(event) => setTarget(event.target.value)}
              disabled={isAnalyzing}
            />

            <div>
              <strong>협력사 공유</strong>
              <p>협력사에 불필요한 개인정보를 마스킹합니다.</p>
            </div>
          </label>

          <label
            className={`target-card ${
              target === "public" ? "selected" : ""
            }`}
          >
            <input
              type="radio"
              name="target"
              value="public"
              checked={target === "public"}
              onChange={(event) => setTarget(event.target.value)}
              disabled={isAnalyzing}
            />

            <div>
              <strong>공개 배포</strong>
              <p>개인을 식별할 수 있는 정보를 적극적으로 제거합니다.</p>
            </div>
          </label>
        </div>

        <button
          type="button"
          className="analyze-button"
          onClick={handleAnalyze}
          disabled={!selectedFile || isAnalyzing}
        >
          {isAnalyzing ? "문서 분석 중..." : "AI 문서 분석 시작"}
        </button>
      </section>

      {analysisResult && (
        <section className="card result-card">
          <div className="step-title">
            <span className="step-number">3</span>

            <div>
              <h2>개인정보 탐지 결과</h2>
              <p>OCR과 개인정보 탐지가 완료되었습니다.</p>
            </div>
          </div>

          <div className="result-summary">
            <p>
              <strong>파일명</strong>
              <span>{analysisResult.filename}</span>
            </p>

            <p>
              <strong>페이지 수</strong>
              <span>{analysisResult.page_count}페이지</span>
            </p>

            <p>
              <strong>탐지 결과</strong>
              <span>{analysisResult.items?.length || 0}건</span>
            </p>
          </div>

          {previewUrl && (
            <object
              className="document-preview"
              data={previewUrl}
              type={selectedFile.type}
              aria-label="원본 문서 미리보기"
            >
              원본 문서를 미리 볼 수 없습니다.
            </object>
          )}

          {!analysisResult.items ||
          analysisResult.items.length === 0 ? (
            <div className="empty-result">
              탐지된 개인정보가 없습니다.
            </div>
          ) : (
            <>
              <div className="selection-toolbar">
                <span>
                  전체 {analysisResult.items.length}건 중{" "}
                  {analysisResult.items.length - excludedIds.length}건 선택
                </span>
                <button type="button" onClick={toggleAllItems}>
                  {excludedIds.length ? "전체 선택" : "전체 해제"}
                </button>
              </div>
              <div className="result-table-wrapper">
                <table className="result-table">
                  <thead>
                    <tr>
                      <th>선택</th>
                      <th>종류</th>
                      <th>탐지된 값</th>
                      <th>페이지</th>
                      <th>탐지 방식</th>
                    </tr>
                  </thead>

                  <tbody>
                    {analysisResult.items.map((item) => (
                      <tr key={item.id}>
                        <td>
                          <input
                            type="checkbox"
                            checked={!excludedIds.includes(item.id)}
                            onChange={() => toggleItem(item.id)}
                            aria-label={`${PII_LABELS[item.type] || item.type} 마스킹 대상`}
                          />
                        </td>
                        <td>{PII_LABELS[item.type] || item.type}</td>
                        <td>{hideSensitiveValue(item.type, item.value)}</td>
                        <td>{item.page}</td>
                        <td>{SOURCE_LABELS[item.source] || item.source}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          <button
            type="button"
            className="analyze-button"
            onClick={handleMask}
            disabled={isMasking}
          >
            {isMasking ? "마스킹 중..." : "선택한 기준으로 마스킹"}
          </button>
        </section>
      )}

      {/* 아래에서 analysisResult.items를 참조하므로 둘 다 있을 때만 그린다 */}
      {maskResult && analysisResult && (
        <section className="card">
          <h2>마스킹 결과</h2>
          <p>{maskResult.summary}</p>
          <div className="result-table-wrapper">
            <table className="result-table">
              <thead>
                <tr>
                  <th>종류</th>
                  <th>원본</th>
                  <th>처리</th>
                  <th>결과</th>
                  <th>근거 문서</th>
                  <th>근거 설명</th>
                </tr>
              </thead>
              <tbody>
                {maskResult.policies.map((policy) => {
                  const item = analysisResult.items?.find(
                    ({ id }) => id === policy.item_id
                  );
                  return (
                    <tr key={policy.item_id}>
                      <td>{PII_LABELS[item?.type] || item?.type || "-"}</td>
                      <td>
                        {item
                          ? hideSensitiveValue(item.type, item.value)
                          : "-"}
                      </td>
                      <td>{ACTION_LABELS[policy.action] || policy.action}</td>
                      <td>{policy.masked_value || "-"}</td>
                      <td>
                        {[policy.basis?.doc, policy.basis?.clause]
                          .filter(Boolean)
                          .join(" · ") || "-"}
                      </td>
                      <td>{policy.basis?.summary || "-"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <button
            type="button"
            className="analyze-button"
            onClick={handleDownload}
            disabled={isDownloading}
          >
            {isDownloading ? "다운로드 중..." : "마스킹 PDF 다운로드"}
          </button>
        </section>
      )}
    </main>
  );
}

export default App;
