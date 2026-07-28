import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 300000,
});

// 백엔드 서버 상태 확인
export async function checkHealth() {
  const response = await api.get("/health");
  return response.data;
}

// 문서 분석 요청
export async function analyzeDocument(file, onUploadProgress) {
  const formData = new FormData();

  // 백엔드의 UploadFile 변수명이 file이라고 가정
  formData.append("file", file);

  const response = await api.post("/analyze", formData, {
    onUploadProgress: (event) => {
      if (!event.total) {
        return;
      }

      const percent = Math.round(
        (event.loaded * 100) / event.total
      );

      onUploadProgress?.(percent);
    },
  });

  return response.data;
}

export async function maskDocument(analysisId, target, excludeIds) {
  const response = await api.post("/mask", {
    analysis_id: analysisId,
    target,
    exclude_ids: excludeIds,
  });

  return response.data;
}

export async function downloadResult(resultId) {
  const response = await api.get(`/download/${resultId}`, {
    responseType: "blob",
  });

  return response.data;
}

export default api;
