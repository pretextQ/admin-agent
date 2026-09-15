# API 接口文档

> 版本：V1.0　|　更新日期：2026-09-15
> 
> 在线文档：http://localhost:8000/docs (Swagger UI)

---

## 一、接口概览

### 1.1 基础信息

| 项目 | 说明 |
|------|------|
| Base URL | `https://your-domain.com/api/v1` |
| 认证方式 | Bearer Token (JWT) |
| 数据格式 | JSON |
| 字符编码 | UTF-8 |

### 1.2 接口列表

| 模块 | 接口 | 方法 | 说明 |
|------|------|------|------|
| 对话 | `/chat/send` | POST | 发送消息 |
| 对话 | `/chat/history/{id}` | GET | 获取会话历史 |
| 对话 | `/chat/confirm/{task_id}` | POST | 确认操作 |
| 对话 | `/chat/transfer/{id}` | POST | 转人工 |
| 对话 | `/chat/ws/{token}` | WS | WebSocket 对话 |
| 任务 | `/tasks/my` | GET | 我的任务列表 |
| 任务 | `/tasks/pending-approval` | GET | 待审批任务 |
| 任务 | `/tasks/{id}` | GET | 任务详情 |
| 任务 | `/tasks/{id}/approve` | POST | 审批任务 |
| 任务 | `/tasks/{id}/cancel` | POST | 取消任务 |
| 任务 | `/tasks/{id}/timeline` | GET | 任务时间线 |
| 知识库 | `/knowledge/upload` | POST | 上传知识文档 |
| 知识库 | `/knowledge/search` | POST | 搜索知识库 |
| 知识库 | `/knowledge/list` | GET | 文档列表 |
| 知识库 | `/knowledge/{id}` | DELETE | 删除文档 |
| 管理 | `/admin/dashboard` | GET | 仪表盘数据 |
| 管理 | `/admin/audit-logs` | GET | 审计日志 |
| 管理 | `/admin/tools` | GET | 工具列表 |
| 管理 | `/admin/metrics` | GET | 系统指标 |

---

## 二、通用说明

### 2.1 请求头

```
Content-Type: application/json
Authorization: Bearer <token>
```

### 2.2 响应格式

```json
// 成功
{
    "code": 0,
    "message": "success",
    "data": { ... }
}

// 失败
{
    "code": 40001,
    "message": "错误描述",
    "details": { ... }
}
```

### 2.3 分页参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| page | int | 1 | 页码 |
| page_size | int | 20 | 每页数量 |

### 2.4 分页响应

```json
{
    "items": [...],
    "total": 100,
    "page": 1,
    "page_size": 20
}
```

---

## 三、接口详情

### 3.1 发送消息

**POST** `/chat/send`

发送消息给智能体，创建或继续会话。

**请求参数：**

```json
{
    "message": "我想请两天年假",
    "conversation_id": "conv_123",  // 可选，为空则创建新会话
    "attachments": ["url1", "url2"]  // 可选，附件URL
}
```

**响应示例：**

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

### 3.2 确认操作

**POST** `/chat/confirm/{task_id}`

确认高风险操作（报销、用印等）。

**请求参数：**

```json
{
    "confirmed": true,  // true=确认, false=取消
    "comment": "确认无误"  // 可选
}
```

### 3.3 获取任务列表

**GET** `/tasks/my`

获取当前用户的任务列表。

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| status | string | 状态过滤: pending/approving/completed |
| type | string | 类型过滤: leave/expense/meeting_room |

**响应示例：**

```json
{
    "code": 0,
    "data": {
        "tasks": [
            {
                "id": "task_123",
                "type": "leave",
                "status": "approving",
                "title": "请假申请 - 年假 2天",
                "created_at": "2026-09-15T10:00:00Z"
            }
        ],
        "total": 10,
        "pending_count": 3,
        "approving_count": 2
    }
}
```

### 3.4 审批任务

**POST** `/tasks/{id}/approve`

审批待处理的任务。

**请求参数：**

```json
{
    "action": "approve",  // approve/reject/add_sign
    "comment": "同意",     // 可选
    "add_sign_user_id": "user_789"  // 加签时指定
}
```

---

## 四、WebSocket 协议

### 4.1 连接

```
ws://your-domain.com/api/v1/chat/ws/{token}
```

### 4.2 消息格式

**客户端发送：**
```json
{
    "type": "message",
    "content": "你好",
    "conversation_id": "conv_123"
}
```

**服务端推送：**
```json
// 普通消息
{
    "type": "reply",
    "content": "你好，我是行政助手",
    "conversation_id": "conv_123"
}

// 输入状态
{
    "type": "typing",
    "is_typing": true
}

// 卡片消息
{
    "type": "card",
    "card_data": {
        "type": "confirmation",
        "title": "请确认",
        "data": { ... }
    }
}
```

---

## 五、错误码

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

## 六、调用示例

### 6.1 cURL

```bash
# 发送消息
curl -X POST http://localhost:8000/api/v1/chat/send \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_token" \
  -d '{"message": "年假有几天"}'

# 获取任务列表
curl http://localhost:8000/api/v1/tasks/my \
  -H "Authorization: Bearer your_token"
```

### 6.2 Python

```python
import httpx

base_url = "http://localhost:8000/api/v1"
headers = {"Authorization": "Bearer your_token"}

# 发送消息
response = httpx.post(
    f"{base_url}/chat/send",
    json={"message": "年假有几天"},
    headers=headers
)
print(response.json())

# 获取任务
response = httpx.get(
    f"{base_url}/tasks/my",
    headers=headers
)
print(response.json())
```