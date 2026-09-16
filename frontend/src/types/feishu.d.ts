interface FeishuAuthCodeOptions {
  appId: string;
  success: (res: { code: string }) => void;
  fail: (err: unknown) => void;
}

interface FeishuSDK {
  requestAuthCode: (options: FeishuAuthCodeOptions) => void;
  openLink: (options: { url: string }) => void;
  share: (options: { url: string; title: string }) => void;
}

declare interface Window {
  tt?: FeishuSDK;
}
