# 企业行政智能系统

> AI 行政数字员工 - "员工动嘴，系统办事"

## 项目简介

企业行政智能系统是一套面向企业内部员工的 AI 行政助理。员工通过自然语言提出行政诉求，智能体理解意图并自动完成事务办理，支持多轮对话澄清与全流程状态跟踪。

## 技术栈

| 层级 | 技术选型 |
|------|----------|
| 后端框架 | FastAPI |
| 数据库 | PostgreSQL |
| 缓存 | Redis |
| 向量库 | ChromaDB |
| LLM | OpenAI API |
| 任务队列 | Celery |
| 部署 | Docker + Nginx |

## 文档目录

```
docs/
├── 行政智能系统需求文档.md          # PRD 产品需求文档
├── architecture/
│   └── 行政智能系统-技术方案设计.md  # 技术架构设计
├── api/                             # API 接口文档（待补充）
│   └── api-spec.md
└── guides/                          # 开发指南
    ├── 设计计划与里程碑.md
    ├── 开发规范.md
    └── 测试计划.md
```

## 快速开始

```bash
# 1. 克隆项目
git clone <repo-url>

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动服务
docker-compose up -d

# 4. 访问 API 文档
open http://localhost:8000/docs
```

## 项目状态

- [x] 需求文档
- [x] 技术方案设计
- [ ] 项目初始化
- [ ] 核心模块开发
- [ ] 测试与联调
- [ ] 上线部署

## 联系方式

- 项目负责人：[待填写]
- 技术负责人：[待填写]
