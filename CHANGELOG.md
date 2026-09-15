# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/) 与
[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 规范。

---

## [0.1.0] - 未发布

### 新增
- 项目文档结构
- 需求文档（PRD）
- 技术方案设计
- API 接口文档
- 开发规范、代码风格指南、测试计划、设计计划与里程碑
- 工具链收敛为 ruff（format + lint）+ mypy + pytest + pre-commit

### 变更
- `pyproject.toml` 确立为依赖与工具链的唯一真相源，`requirements*.txt` 由其派生
- 软件版本统一为 `0.1.0`（pyproject / `.env` / FastAPI 应用）
- 统一目录布局与导入路径为 `app/admin_ai/...`，first-party 为 `app`

### 修复
- 修正 `.env.example` 与 `Settings` 字段不一致可能导致的配置静默失效问题

### 文档
- 统一 API 响应信封 `{code, message, data}` 与错误码口径
- 对齐覆盖率口径（Core ≥90%、Service ≥85%、API ≥80%、整体 ≥80%）
- 对齐验收指标（意图识别第 2 周 ≥85%、M4/上线 ≥92%）

### 移除
- 移除 black / isort / flake8 及其依赖，改由 ruff 统一承担

### 待开发
- FastAPI 项目骨架
- 核心业务模块
- 数据库模型
- API 接口实现

---

## [0.0.1] - 2026-09-15

### 新增
- 项目初始化
- Git 仓库创建
- 基础文档结构

---

## 版本说明

版本格式：主版本号.次版本号.修订号

- **主版本号**：不兼容的 API 修改
- **次版本号**：向下兼容的功能性新增
- **修订号**：向下兼容的问题修正

当前开发版本为 `0.1.0`（未发布），`0.0.1` 为初始基线版本。

[0.1.0]: https://gitee.com/qiulongfei4408/admin-ai-agent/compare/v0.0.1...v0.1.0
[0.0.1]: https://gitee.com/qiulongfei4408/admin-ai-agent/releases/tag/v0.0.1
