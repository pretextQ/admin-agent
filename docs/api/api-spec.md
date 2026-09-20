# API 接口文档

> 版本：V1.3　|　更新日期：2026-09-16　|　软件版本：0.1.0
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
| 认证 | `/auth/feishu/login-url` | GET | 获取飞书授权跳转地址 |
| 认证 | `/auth/feishu/callback` | GET | 飞书 OAuth 回调（换 token + 签发 JWT） |
| 认证 | `/auth/dev-login` | GET | 开发环境登录（仅 development） |
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
| 系统 | `/api/health` | GET | 健康检查（不含 `/api/v1` 前缀） |

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

### 3.1 获取飞书授权地址

**GET** `/auth/feishu/login-url`

生成飞书 OAuth 授权跳转地址，前端拿到后引导用户跳转。

响应：

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "login_url": "https://open.feishu.cn/open-apis/authen/v1/index?app_id=...&redirect_uri=...&state=...",
        "state": "random_csrf_token"
    }
}
```

### 3.2 飞书 OAuth 回调

**GET** `/auth/feishu/callback`

飞书授权完成后的回调端点。服务端用授权码换取 `user_access_token`，拉取用户信息，签发本地 JWT。

| 参数 | 类型 | 说明 |
|------|------|------|
| `code` | string | 飞书授权码，必填 |
| `state` | string | 防 CSRF 状态码，必填 |

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

错误：

| 场景 | 错误码 | HTTP 状态码 |
|------|--------|-------------|
| state 无效 | 40001 | 400 |
| 换取飞书 token 失败 | 50002 | 502 |
| 获取飞书用户信息失败 | 50002 | 502 |

### 3.3 开发环境登录

**GET** `/auth/dev-login`

仅 `ENVIRONMENT=development` 时可用，生产环境返回 `40003`。

| 参数 | 类型 | 说明 |
|------|------|------|
| `employee_id` | string | 可选，默认 `admin001` |

响应与 3.2 相同。

### 3.4 当前用户

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

**GET** `/chat/history/{conversation_id}`

无分页参数，一次返回该会话全部消息（按时间正序）。

响应：

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "conversation_id": "conv_001",
        "messages": [
            {"id": "msg_001", "role": "user", "content": "你好", "card_data": null, "requires_action": false, "created_at": "..."},
            {"id": "msg_002", "role": "assistant", "content": "您好", "card_data": null, "requires_action": false, "created_at": "..."}
        ],
        "total": 2
    }
}
```

`card_data` / `requires_action` 从消息 `meta` 还原，供前端直接渲染确认卡片。
会话不存在返回 `40004`；仅可访问本人会话，越权返回 `40003`。

### 4.3 确认高风险操作

**POST** `/chat/confirm/{task_id}`

```json
{
    "confirmed": true,
    "comment": "确认无误"
}
```

`confirmed=false` 表示取消。**注意**：该参数位于请求体中，不是查询参数。

> **实现说明（D-01 待定项）**：当前实现以 `conversation_id` 定位待确认操作
> （从会话状态恢复槽位，路径为 `/chat/confirm/{conversation_id}`），规格中的
> `task_id` 为目标形态（落 TaskModel 后切换）。仅会话属主可操作，越权返回 `40003`。

### 4.4 转人工

**POST** `/chat/transfer/{conversation_id}`

```json
{
    "reason": "问题太复杂"
}
```

响应 `data` 与 `/chat/send` 同构（`conversation_id` / `message_id` / `content`）。

> **实现说明（2026-09-20 落地）**：端点会
> ① 校验会话存在（不存在返回 `40004`）与操作者为会话属主（越权返回 `40003`）；
> ② 置 `conversations.status = transferred`；
> ③ 写入一条 assistant 历史消息，`meta` 含 `transfer_to_human: true` 与 `reason`；
> ④ 清除该会话的待确认状态（人工介入期间不允许再通过 `/chat/confirm` 自动执行高风险操作）；
> ⑤ 调用通知服务提醒人工客服（当前 `NotificationService` 仅打日志，真实推送待接）。
>
> 另有一条**自动转人工**路径：编排器识别不出意图时（`intent=other`）会直接转人工，
> 该路径同样标记会话状态与消息，但**尚未调用通知服务**（已知小缺口）。

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
| `scope` | string | 数据归属范围（SECURITY §4.3）：`my` 本人（默认）/ `dept` 本部门及子部门（限部门主管）/ `all` 全量（限 admin·finance·hr）。越权取值返回 `40003`，非法取值返回 `40001`；`dept`/`all` 每次访问写审计（`action=task_scope_query`，只记范围不记单据内容） |
| `page` / `page_size` | int | 分页 |

响应（分页字段统一为 `items/total/page/page_size`）：

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "items": [
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
        "scope": "my",
        "pending_count": 3,
        "approving_count": 2
    }
}
```

### 6.2 待我审批

**GET** `/tasks/pending-approval` —— 返回结果结构与 6.1 相同。

### 6.3 任务详情

**GET** `/tasks/{task_id}` —— 含业务数据、当前审批人与审批链。

响应在基础字段外包含：

| 字段 | 类型 | 说明 |
|------|------|------|
| `can_approve` | bool | 当前用户是否为该任务的待审批人 |
| `is_owner` | bool | 当前用户是否为任务属主 |
| `approvals[]` | array | 审批链（含 `add_sign_user_id`） |

访问权限：任务属主或当前待审批人可见；其他用户返回 `40003`。

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

- `add_sign`：原审批记录关闭（`status=done`），并生成被加签人的新 `pending` 记录；禁止加签给自己（`40001`）
- 全部审批节点通过后任务置 `completed`；`reject` 置 `failed`

### 6.5 取消任务

**POST** `/tasks/{task_id}/cancel`

仅任务属主可取消，且任务需处于 `pending` / `processing` / `approving` 状态；
终态任务（completed/failed/cancelled）取消返回 `40001`。

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
| `/admin/departments` | GET | 部门树（含主管与上游 `external_id`，用于核对组织数据完整性） |
| `/admin/approval-rules` | GET / POST | 审批路由规则：查询 / 新增或更新（带 `id` 为更新）；校验 `approver_type`、`approval_mode`、金额区间、`step_order` 与 `condition`（按槽位分支的条件，算子 eq/ne/gt/gte/lt/lte/in/not_in） |
| `/admin/approval-rules/{rule_id}` | DELETE | 删除规则（在途审批不受影响，步骤模式在生成审批链时已快照） |
| `/admin/approval-delegations` | GET / POST | 代理审批委派：查询 / 新增（`delegator_id ≠ delegate_id`、`end_at > start_at`） |
| `/admin/org/sync` | POST | 手动触发组织同步；失败不修改组织数据，返回 `ok=false` 与原因 |

均要求管理员角色，否则返回 `40003`。

> 审批规则与委派的字段语义、路由算法与兜底行为见
> [组织架构与审批路由设计](../architecture/组织架构与审批路由设计.md)；
> 首期维护入口为「脚本 + API」（`scripts/manage_approval_rules.py`），管理后台 UI 随评审 I-3 决策另排。

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
# 获取飞书授权地址
curl http://localhost:8000/api/v1/auth/feishu/login-url

# 开发环境登录
curl http://localhost:8000/api/v1/auth/dev-login?employee_id=admin001

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
