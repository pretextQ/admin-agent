# Admin AI Agent 前端

企业行政智能系统的 Web 前端（飞书 H5 / 浏览器双端），React 19 + TypeScript + Semi Design。

## 技术栈

| 层级 | 选型 | 说明 |
|------|------|------|
| 框架 | React 19 + TypeScript 6 | `tsc -b` 项目引用模式，严格选项 |
| 构建 | Vite 8（Rolldown） | dev 端口 3000，`/api` 代理到后端 8000 |
| UI | Semi Design 2 | 字节出品，配套 `@douyinfe/semi-icons` |
| 状态 | Zustand 5 | auth（persist 到 localStorage）/ chat / app 三个 store |
| HTTP | Axios 1 | 统一信封解包 + Bearer 注入 + 401 处理 |
| 路由 | React Router 7 | 嵌套路由 + 受保护路由 |
| 测试 | Vitest 5 + Testing Library | 仅声明依赖，暂无用例和 test 脚本 |
| Lint | oxlint | `pnpm lint` |

## 页面结构

| 路由 | 页面 | 说明 |
|------|------|------|
| `/login` | 登录 | 飞书授权登录入口（DEV 走 dev-login 直登） |
| `/callback` | OAuth 回调 | 支持 `?jwt=` 直登与 `code+state` 换 token 两种形态 |
| `/` | 对话 | 消息收发、确认卡片（高风险操作）、历史恢复（进入时拉取） |
| `/tasks` | 任务列表 | 我的任务 / 待我审批两个维度，状态/类型筛选 |
| `/tasks/:id` | 任务详情 | 审批链、时间线、同意/驳回（审批人）、取消（属主） |

## 本地开发

```bash
pnpm install
pnpm dev        # http://localhost:3000，/api 代理到 http://localhost:8000
pnpm build      # 生产构建
pnpm lint       # oxlint
```

后端未启动时页面可渲染但数据请求失败；完整环境（PG/Redis/开发桩/API）见根目录
[README](../README.md) 与 [部署与运维](../docs/guides/部署与运维.md)。

## 与后端的约定

- 响应统一信封 `{code, message, data}`，`code !== 0` 视为业务错误抛出
- 认证：`Authorization: Bearer <JWT>`，token 存于 localStorage `auth-storage`
- 连续 3 次 401 清除本地登录态并跳转 `/login`
- 确认卡片结构见 [api-spec 第 10 节](../docs/api/api-spec.md)：`{type, title, data, actions, warning}`
