# Admin AI Agent

> 企业行政智能系统 - AI 行政数字员工
>
> "员工动嘴，系统办事"

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 项目简介

Admin AI Agent 是一套面向企业内部员工的 **AI 行政智能助理**。员工通过自然语言提出行政诉求，智能体理解意图并自动完成事务办理，支持多轮对话澄清与全流程状态跟踪。

**核心能力：**

- 🤖 自然语言理解：识别 11 类行政意图
- 🔄 多轮对话：信息不全时智能反问
- 🔧 工具调用：对接 OA、审批、物资等系统
- 📚 知识检索：RAG 检索制度文档
- 🔐 分级授权：低/中/高风险场景不同处理
- 📋 全流程审计：操作留痕可追溯

**支持场景：**

| 场景 | 自动化程度 | 说明 |
|------|-----------|------|
| 制度问答 | ✅ 全自动 | "年假有几天""报销标准是什么" |
| 会议室预定 | ✅ 全自动 | "明天下午订个10人会议室" |
| 请假申请 | ✅ 全自动 | 校验余额/冲突，发起审批 |
| 物资领用 | ✅ 全自动 | 检查库存/限额，自动扣减 |
| 报销申请 | ⚠️ 半自动 | 草拟+校验，人工确认后提交 |
| 差旅申请 | ⚠️ 半自动 | 生成行程+按标准预订 |
| 用印/盖章 | ⚠️ 半自动 | 校验+发起审批，人工确认 |

---

## 技术栈

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| 后端框架 | FastAPI | 异步高性能，自动文档 |
| 数据库 | PostgreSQL | 主数据存储 |
| 缓存 | Redis | 会话管理、限流 |
| 向量库 | ChromaDB | RAG 知识检索 |
| LLM | OpenAI API | 意图识别、对话生成 |
| 任务队列 | Celery | 异步任务处理 |
| 部署 | Docker + Nginx | 容器化部署 |

---

## 项目结构

```
admin-ai-agent/
├── README.md                           # 项目说明
├── LICENSE                             # 开源协议
├── CHANGELOG.md                        # 版本历史
├── CONTRIBUTING.md                     # 贡献指南
├── .gitignore                          # Git 忽略配置
├── .env.example                        # 环境变量示例
├── requirements.txt                    # Python 依赖
├── pyproject.toml                      # 项目配置
├── docker-compose.yml                  # Docker 编排
├── Dockerfile                          # Docker 镜像
├── alembic.ini                         # 数据库迁移配置
│
├── app/                                # 应用代码
│   ├── __init__.py
│   ├── main.py                         # FastAPI 入口
│   ├── config.py                       # 配置管理
│   ├── dependencies.py                 # 依赖注入
│   │
│   ├── api/                            # API 路由层
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── router.py              # v1 路由汇总
│   │   │   ├── chat.py                # 对话接口
│   │   │   ├── task.py                # 任务接口
│   │   │   ├── knowledge.py           # 知识库接口
│   │   │   └── admin.py               # 管理后台接口
│   │   └── websocket/
│   │       └── chat_ws.py             # WebSocket 对话
│   │
│   ├── core/                           # 核心业务逻辑
│   │   ├── __init__.py
│   │   ├── agent/                      # 智能体模块
│   │   │   ├── __init__.py
│   │   │   ├── orchestrator.py        # 智能体编排器
│   │   │   ├── intent.py              # 意图识别
│   │   │   ├── slot.py                # 槽位抽取
│   │   │   ├── dialog.py              # 多轮对话管理
│   │   │   └── prompt.py              # Prompt 模板
│   │   │
│   │   ├── rag/                        # RAG 知识检索
│   │   │   ├── __init__.py
│   │   │   ├── retriever.py           # 检索器
│   │   │   ├── embedder.py            # 向量化
│   │   │   └── splitter.py            # 文档切片
│   │   │
│   │   ├── tools/                      # 工具调用层
│   │   │   ├── __init__.py
│   │   │   ├── registry.py            # 工具注册中心
│   │   │   ├── gateway.py             # 统一网关
│   │   │   ├── base.py                # 工具基类
│   │   │   ├── oa_tool.py             # OA 工具
│   │   │   ├── approval_tool.py       # 审批流工具
│   │   │   ├── material_tool.py       # 物资工具
│   │   │   └── calendar_tool.py       # 日程工具
│   │   │
│   │   ├── rules/                      # 规则引擎
│   │   │   ├── __init__.py
│   │   │   ├── engine.py              # 规则引擎
│   │   │   └── validators.py          # 校验器
│   │   │
│   │   └── auth/                       # 认证鉴权
│   │       ├── __init__.py
│   │       ├── sso.py                 # SSO 集成
│   │       └── rbac.py                # 权限控制
│   │
│   ├── models/                         # 数据模型
│   │   ├── __init__.py
│   │   ├── user.py                    # 用户模型
│   │   ├── conversation.py            # 会话模型
│   │   ├── message.py                 # 消息模型
│   │   ├── task.py                    # 任务模型
│   │   └── audit.py                   # 审计模型
│   │
│   ├── schemas/                        # Pydantic Schema
│   │   ├── __init__.py
│   │   ├── chat.py
│   │   ├── task.py
│   │   └── common.py
│   │
│   ├── services/                       # 服务层
│   │   ├── __init__.py
│   │   ├── chat_service.py            # 对话服务
│   │   ├── task_service.py            # 任务服务
│   │   └── knowledge_service.py       # 知识库服务
│   │
│   ├── db/                             # 数据库
│   │   ├── __init__.py
│   │   ├── session.py                 # 数据库会话
│   │   ├── redis.py                   # Redis 连接
│   │   └── migrations/                # Alembic 迁移
│   │
│   ├── middleware/                      # 中间件
│   │   ├── __init__.py
│   │   ├── audit.py                   # 审计中间件
│   │   └── rate_limit.py              # 限流中间件
│   │
│   └── utils/                          # 工具函数
│       ├── __init__.py
│       ├── logger.py
│       └── exceptions.py
│
├── tests/                              # 测试代码
│   ├── conftest.py                    # 测试配置
│   ├── test_api/                      # API 测试
│   ├── test_core/                     # 单元测试
│   └── test_services/                 # 集成测试
│
├── scripts/                            # 脚本工具
│   ├── init_db.py                     # 数据库初始化
│   └── seed_data.py                   # 测试数据
│
└── docs/                               # 项目文档
    ├── 行政智能系统需求文档.md
    ├── architecture/
    │   └── 行政智能系统-技术方案设计.md
    ├── api/
    │   └── api-spec.md
    └── guides/
        ├── 设计计划与里程碑.md
        ├── 开发规范.md
        └── 测试计划.md
```

---

## 环境要求

| 环境 | 版本要求 |
|------|----------|
| Python | 3.11+ |
| PostgreSQL | 15+ |
| Redis | 7+ |
| Docker | 24+ |
| Node.js | 18+ (前端开发) |

---

## 快速开始

### 1. 克隆项目

```bash
git clone https://gitee.com/qiulongfei4408/admin-ai-agent.git
cd admin-ai-agent
```

### 2. 环境配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入配置
# 必须配置：
# - DATABASE_URL: PostgreSQL 连接
# - REDIS_URL: Redis 连接
# - OPENAI_API_KEY: OpenAI API Key
```

### 3. Docker 启动（推荐）

```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f api
```

### 4. 本地开发

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 初始化数据库
alembic upgrade head

# 启动开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. 访问服务

| 服务 | 地址 |
|------|------|
| API 服务 | http://localhost:8000 |
| Swagger 文档 | http://localhost:8000/docs |
| ReDoc 文档 | http://localhost:8000/redoc |
| Flower (Celery) | http://localhost:5555 |

---

## 开发指南

### 代码规范

```bash
# 代码格式化
black app/ tests/

# 导入排序
isort app/ tests/

# 代码检查
flake8 app/ tests/

# 类型检查
mypy app/
```

### 测试

```bash
# 运行所有测试
pytest

# 运行带覆盖率
pytest --cov=app --cov-report=html

# 运行特定测试
pytest tests/test_core/test_intent.py
```

### 数据库迁移

```bash
# 创建迁移
alembic revision --autogenerate -m "描述"

# 执行迁移
alembic upgrade head

# 回滚迁移
alembic downgrade -1
```

---

## 部署

### 生产环境部署

```bash
# 构建镜像
docker build -t admin-ai-agent .

# 启动生产环境
docker-compose -f docker-compose.prod.yml up -d

# 数据库迁移
docker-compose exec api alembic upgrade head
```

### 环境变量说明

| 变量 | 说明 | 默认值 |
|------|------|--------|
| DATABASE_URL | PostgreSQL 连接 | - |
| REDIS_URL | Redis 连接 | redis://localhost:6379/0 |
| OPENAI_API_KEY | OpenAI API Key | - |
| OPENAI_BASE_URL | OpenAI API 地址 | https://api.openai.com/v1 |
| LLM_MODEL | 模型名称 | gpt-4o-mini |
| SECRET_KEY | JWT 密钥 | - |
| DEBUG | 调试模式 | false |

---

## 文档

| 文档 | 说明 |
|------|------|
| [需求文档](docs/行政智能系统需求文档.md) | 产品需求文档 (PRD) |
| [技术方案](docs/architecture/行政智能系统-技术方案设计.md) | 技术架构设计 |
| [API 文档](docs/api/api-spec.md) | 接口规范 |
| [设计计划](docs/guides/设计计划与里程碑.md) | 项目规划 |
| [开发规范](docs/guides/开发规范.md) | 代码规范 |
| [测试计划](docs/guides/测试计划.md) | 测试策略 |

---

## 项目状态

- [x] 需求文档
- [x] 技术方案设计
- [x] 项目文档结构
- [ ] 项目骨架代码
- [ ] 核心模块开发
- [ ] 测试与联调
- [ ] 上线部署

---

## 贡献指南

请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解贡献流程。

---

## 版本历史

请阅读 [CHANGELOG.md](CHANGELOG.md) 了解版本更新历史。

---

## 开源协议

本项目采用 [MIT](LICENSE) 协议。

---

## 联系方式

- 项目负责人：[待填写]
- 技术负责人：[待填写]
- 问题反馈：[Issues](https://gitee.com/qiulongfei4408/admin-ai-agent/issues)
