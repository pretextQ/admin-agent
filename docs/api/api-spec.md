# API 接口文档

> 版本：V1.1　|　更新日期：2026-09-15　|　软件版本：0.1.0
>
> 在线文档：http://localhost:8000/docs （Swagger UI）
>
> 设计与实现细节见 [技术方案设计](../architecture/行政智能系统-技术方案设计.md) §8。

---

## 一、接口概览

### 1.1 基础信息

| 项目 | 说明 |
|------|------|
| Base URL | `https://<domain>/api/v1` |
| 认证方式 | Bearer Token（JWT），`Authorization: Bearer <token>` |
| 数据格式 | JSON |
| 字符编码 | UTF-8 |
| 版本策略 | 路径带版本号；字段只增不删，删除前先标记 deprecated |

### 1.2 接口列表

| 模块 | 接口 | 方法 | 说明 |
|------|------|------|------|
| 认证 | `/auth/login` | POST | 账号密码登录 |
| 认证 | `/auth/sso/authorize` | GET | SSO 授权跳转 |
| 认证 | `/auth/sso/callback` | GET | SSO 回调 |
| 认证 | `/auth/logout` | POST | 登出 |
| 认证 | `/auth/refresh` | POST | 刷新令牌 |
| 认证 | `/auth/me` | GET | 当前用户信息 |
| 对话 | `/chat/send` | POST | 发送消息 |
| 对话 | `/chat/history/{conversation_id}` | GET | 获取会话历史 |
| 对话 | `/chat/confirm/{task_id}` | POST | 确认 / 取消高风险操作 |
| 对话 | `/chat/transfer/{conversation_id}` | POST | 转人工 |
| 对话 | `/chat/ws` | WS | WebSocket 实时对话 |
| 文件 | `/files` | POST | 上传附件 |
| 文件 | `/files/{file_id}` | GET | 文件元信息 |
| 任务 | `/tasks/my` | GET | 我的任务列表 |
| 任务 | `/tasks/pending-approval` | GET | 待我审批的任务 |
| 任务 | `/tasks/{task_id}` | GET | 任务详情 |
| 任务 | `/tasks/{task_id}/approve` | POST | 审批任务 |
| 任务 | `/tasks/{task_id}/cancel` | POST | 取消任务 |
| 任务 | `/tasks/{task_id}/timeline` | GET | 任务时间线 |
| 知识库 | `/knowledge/upload` | POST | 上传知识文档 |
| 知识库 | `/knowledge/search` | POST | 搜索知识库 |
| 知识库 | `/knowledge/list` | GET | 文档列表 |
| 知识库 | `/knowledge/{doc_id}` | DELETE | 删除文档 |
| 管理 | `/admin/dashboard` | GET | 仪表盘数据 |
| 管理 | `/admin/audit-logs` | GET | 审计日志 |
| 管理 | `/admin/tools` | GET | 工具列表 |
| 管理 | `/admin/tools/{tool_id}/config` | PUT | 更新工具配置 |
| 管理 | `/admin/metrics` | GET | 系统指标 |
| 系统 | `/health` | GET | 健康检查 |

---

## 二、通用说明

### 2.1 请求头

| 请求头 | 必填 | 说明 |
|--------|------|------|
| `Content-Type` | 是 | `application/json`（文件上传用 `multipart/form-data`） |
| `Authorization` | 是 | `Bearer <JWT>` |
| `X-Request-Id` | 否 | 链路追踪 ID，不传则服务端生成 |
| `Idempotency-Key` | 高风险写操作必填 | 幂等键，重复请求返回同一结果 |

### 2.2 响应格式

**成功：**

```json
{
    "code": 0,
    "message": "success",
    "data": { }
}
```

**失败：**

```json
{
    "code": 40001,
    "message": "参数错误",
    "details": { "field": "message" }
}
```

> 由全局异常处理器统一包装，HTTP 状态码同时保持语义化。

### 2.3 分页

请求参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | int | 1 | 页码，从 1 开始 |
| `page_size` | int | 20 | 每页数量，最大 100 |

分页响应放在 `data` 内：

```json
{
    "items": [],
    "total": 100,
    "page": 1,
    "page_size": 20
}
```

---

## 三、认证接口

### 3.1 账号密码登录

**POST** `/auth/login`

```json
{
    "employee_id": "EMP1001",
    "password": "******"
}
```

响应：

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "access_token": "eyJhbGciOiJIUzI1NiIs...",
        "token_type": "bearer",
        "expires_in": 3600
    }
}
```

### 3.2 SSO 登录

**GET** `/auth/sso/authorize`

重定向到企业 SSO 认证页面。用户授权后回调到 `/auth/sso/callback`。

**GET** `/auth/sso/callback`

SSO 回调端点，接收授权码并换取 Token。

| 参数 | 类型 | 说明 |
|------|------|------|
| `code` | string | SSO 授权码，必填 |
| `state` | string | 防 CSRF 状态码，必填 |

响应与 3.1 相同。

### 3.3 登出

**POST** `/auth/logout`

使当前 Token 失效。需携带 `Authorization: Bearer <token>`。

```json
{
    "code": 0,
    "message": "success",
    "data": null
}
```

### 3.4 刷新令牌

**POST** `/auth/refresh`（携带当前有效 Token）

### 3.5 当前用户

**GET** `/auth/me`

返回当前登录用户的基本信息与角色（用于前端展示与权限判断）。

---

## 四、对话接口

### 4.1 发送消息

**POST** `/chat/send`

```json
{
    "message": "我想请两天年假",
    "conversation_id": "conv_123",
    "attachments": ["file_001"]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `message` | string | 用户消息，必填 |
| `conversation_id` | string | 可选，为空则创建新会话 |
| `attachments` | string[] | 可选，由 `/files` 返回的文件 ID |

响应：

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "conversation_id": "conv_123",
        "message_id": "msg_456",
        "content": "请问您要请什么假？（年假/调休/事假/病假）",
        "content_type": "text",
        "card_data": null,
        "suggestions": ["年假", "调休", "事假"],
        "requires_action": true,
        "tool_calls": []
    }
}
```

### 4.2 获取会话历史

**GET** `/chat/history/{conversation_id}?limit=50&offset=0`

仅可访问本人会话；越权返回 `40003`。

### 4.3 确认高风险操作

**POST** `/chat/confirm/{task_id}`

```json
{
    "confirmed": true,
    "comment": "确认无误"
}
```

`confirmed=false` 表示取消。**注意**：该参数位于请求体中，不是查询参数。

### 4.4 转人工

**POST** `/chat/transfer/{conversation_id}`

```json
{
    "reason": "问题太复杂"
}
```

---

## 五、文件接口

### 5.1 上传附件

**POST** `/files`（`multipart/form-data`）

| 约束 | 值 |
|------|----|
| 单文件大小 | ≤ 20 MB |
| 允许类型 | pdf、docx、xlsx、png、jpg、jpeg |
| 校验 | 扩展名 + magic bytes 双重校验 |
| 处理 | UUID 重命名，落对象存储，返回 file_id |

响应：

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "file_id": "file_001",
        "filename": "发票.jpg",
        "content_type": "image/jpeg",
        "size": 204800,
        "url": "https://<domain>/files/file_001/download"
    }
}
```

### 5.2 文件元信息

**GET** `/files/{file_id}` —— 只返回元信息；文件内容通过带签名的临时地址下载。

---

## 六、任务 / 待办接口

### 6.1 我的任务

**GET** `/tasks/my`

查询参数：

| 参数 | 类型 | 说明 |
|------|------|------|
| `status` | string | 过滤：pending / processing / approving / completed / failed / cancelled |
| `type` | string | 过滤：leave / expense / travel / meeting_room / vehicle / material / asset / seal / certificate / onboarding |
| `page` / `page_size` | int | 分页 |

响应：

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "tasks": [
            {
                "id": "task_123",
                "type": "leave",
                "status": "approving",
                "title": "请假申请 - 年假 2 天",
                "risk_level": "medium",
                "created_at": "2026-09-15T10:00:00Z"
            }
        ],
        "total": 10,
        "page": 1,
        "page_size": 20,
        "pending_count": 3,
        "approving_count": 2
    }
}
```

### 6.2 待我审批

**GET** `/tasks/pending-approval` —— 返回结果结构与 6.1 相同。

### 6.3 任务详情

**GET** `/tasks/{task_id}` —— 含业务数据、当前审批人与审批链；越权返回 `40003`。

### 6.4 审批任务

**POST** `/tasks/{task_id}/approve`

```json
{
    "action": "approve",
    "comment": "同意",
    "add_sign_user_id": null
}
```

`action` 取值：`approve` / `reject` / `add_sign`。仅当前审批人可操作，否则返回 `40003`。

### 6.5 取消任务

**POST** `/tasks/{task_id}/cancel`

```json
{
    "reason": "不再需要"
}
```

### 6.6 任务时间线

**GET** `/tasks/{task_id}/timeline` —— 返回状态流转记录（提交、校验、发起审批、各审批节点、完成）。

---

## 七、知识库接口

### 7.1 上传知识文档

**POST** `/knowledge/upload`（管理员）

```json
{
    "title": "差旅报销管理办法",
    "category": "制度",
    "tags": ["差旅", "报销"],
    "content": null
}
```

同时可附带 `file`（PDF / Word / Markdown / 纯文本）。服务端自动切片、向量化、入库。

### 7.2 搜索知识库

**POST** `/knowledge/search`

```json
{
    "query": "酒店报销上限",
    "category": "制度",
    "top_k": 5
}
```

响应结果包含内容、来源、相关度（用于回答引用）。

### 7.3 文档列表 / 删除

- **GET** `/knowledge/list`（管理员，分页）
- **DELETE** `/knowledge/{doc_id}`（管理员，同时清理向量库切片）

---

## 八、管理后台接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/admin/dashboard` | GET | 今日对话数、任务数、转人工率、热门意图 |
| `/admin/audit-logs` | GET | 审计日志（按 user_id/action/日期过滤，分页） |
| `/admin/tools` | GET | 工具列表与启用状态 |
| `/admin/tools/{tool_id}/config` | PUT | 更新工具配置 |
| `/admin/metrics` | GET | LLM 调用次数、Token 成本、平均响应时间、完成率、转人工率 |

均要求管理员角色，否则返回 `40003`。

---

## 九、WebSocket 协议

### 9.1 连接

```text
GET /api/v1/chat/ws
Sec-WebSocket-Protocol: bearer,<JWT>
```

**禁止把 Token 放在 URL 查询串**（会进入网关访问日志）。

### 9.2 消息格式

客户端发送：

```json
{ "type": "message", "content": "你好", "conversation_id": "conv_123" }
{ "type": "ping" }
```

服务端推送：

```json
{ "type": "reply", "content": "你好，我是行政助手", "conversation_id": "conv_123" }
{ "type": "typing", "is_typing": true }
{ "type": "card", "card_data": { "type": "confirmation", "title": "请确认", "data": {} } }
{ "type": "error", "code": 50001, "message": "处理失败" }
{ "type": "pong" }
```

| 事件 | 方向 | 说明 |
|------|------|------|
| `message` | C→S | 用户消息 |
| `ping` / `pong` | 双向 | 心跳保活 |
| `typing` | S→C | 输入状态 |
| `reply` | S→C | 文本回复 |
| `card` | S→C | 卡片消息 |
| `error` | S→C | 错误（带错误码） |

---

## 十、消息卡片 Schema

`content_type=card` 时，`card_data` 结构如下：

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | `confirmation`（确认）/ `form`（表单）/ `status`（状态） |
| `title` | string | 卡片标题 |
| `fields` | array | 表单字段：`{name,label,field_type,required,options}` |
| `data` | object | 预填 / 展示数据 |
| `actions` | string[] | 可用操作，如 `["confirm","cancel"]` |
| `warning` | string | 风险提示文案 |

**确认卡片示例：**

```json
{
    "type": "confirmation",
    "title": "请确认以下操作（将发起盖章审批）",
    "data": { "合同名称": "XX 采购合同", "用印类型": "公章", "用印份数": 3 },
    "actions": ["confirm", "cancel"],
    "warning": "此操作将产生法律效力，请核对！"
}
```

**表单卡片示例：**

```json
{
    "type": "form",
    "title": "需要补全以下信息",
    "fields": [
        { "name": "leave_type", "label": "请假类型", "field_type": "select", "required": true, "options": ["年假", "调休", "事假"] },
        { "name": "start_date", "label": "开始时间", "field_type": "date", "required": true },
        { "name": "end_date", "label": "结束时间", "field_type": "date", "required": true }
    ],
    "actions": ["submit", "cancel"]
}
```

---

## 十一、错误码

| 错误码 | HTTP 状态码 | 说明 |
|--------|-------------|------|
| 0 | 200 | 成功 |
| 40001 | 400 | 参数错误 |
| 40002 | 401 | 未授权 |
| 40003 | 403 | 无权限 |
| 40004 | 404 | 资源不存在 |
| 40005 | 429 | 请求过于频繁 |
| 50001 | 500 | 内部错误 |
| 50002 | 502 | 外部服务错误 |
| 50003 | 503 | 服务不可用 |

---

## 十二、调用示例

### 12.1 cURL

```bash
# 登录
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"employee_id": "EMP1001", "password": "******"}'

# 发送消息
curl -X POST http://localhost:8000/api/v1/chat/send \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Request-Id: req-001" \
  -d '{"message": "年假有几天"}'

# 获取任务列表
curl "http://localhost:8000/api/v1/tasks/my?page=1&page_size=20" \
  -H "Authorization: Bearer $TOKEN"
```

### 12.2 Python

```python
import httpx

base_url = "http://localhost:8000/api/v1"
headers = {"Authorization": "Bearer your_token", "X-Request-Id": "req-001"}

# 发送消息
response = httpx.post(
    f"{base_url}/chat/send",
    json={"message": "年假有几天"},
    headers=headers,
)
print(response.json())

# 获取任务
response = httpx.get(f"{base_url}/tasks/my", headers=headers, params={"page": 1})
print(response.json())
```

### 12.3 高风险操作（幂等示例）

```bash
curl -X POST http://localhost:8000/api/v1/chat/confirm/task_123 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: 6f1b7c2e-9a3d-4f0e-8b21-2c5a7d9e0f11" \
  -d '{"confirmed": true, "comment": "确认无误"}'
```
