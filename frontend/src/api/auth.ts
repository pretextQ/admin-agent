import client from "./client";

export interface LoginUrlResponse {
  login_url: string;
  state: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserInfo {
  user_id: string;
  employee_id: string;
  role: string;
}

export const authApi = {
  getLoginUrl: () =>
    client.get("/auth/feishu/login-url") as Promise<LoginUrlResponse>,

  devLogin: (employeeId: string) =>
    client.get(`/auth/dev-login?employee_id=${employeeId}`) as Promise<TokenResponse>,

  getMe: () =>
    client.get("/auth/me") as Promise<UserInfo>,
};
