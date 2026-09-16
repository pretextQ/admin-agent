import axios, { type InternalAxiosRequestConfig } from "axios";
import type { ApiResponse } from "@/types";

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api/v1",
  timeout: 30000,
});

function getToken(): string | null {
  try {
    const stored = localStorage.getItem("auth-storage");
    if (stored) {
      const parsed = JSON.parse(stored);
      return parsed?.state?.token ?? null;
    }
  } catch {
    // ignore
  }
  return null;
}

client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

let authFailCount = 0;
const MAX_AUTH_FAIL = 3;

client.interceptors.response.use(
  (response) => {
    const body: ApiResponse = response.data;
    if (body.code !== 0) {
      const error = new Error(body.message) as Error & { code: number };
      error.code = body.code;
      return Promise.reject(error);
    }
    // 解包：将 data 字段放到 response.data 上
    response.data = body.data;
    return response;
  },
  (error) => {
    if (error.response?.status === 401) {
      authFailCount++;
      localStorage.removeItem("auth-storage");
      if (authFailCount >= MAX_AUTH_FAIL) {
        alert("登录状态异常，请重新打开应用");
        authFailCount = 0;
      } else {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error.response?.data || error);
  }
);

export default client;
