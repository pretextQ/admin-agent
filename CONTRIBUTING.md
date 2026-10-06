# 贡献指南

项目默认仓库：[GitHub / pretextQ/admin-agent](https://github.com/pretextQ/admin-agent)。环境、任务与代码约定分别见 [开发入门](docs/guides/开发入门.md)、[开发计划](docs/planning/开发计划.md)、[开发规范](docs/guides/开发规范.md)。

## 开发流程

1. 检查当前改动并同步分支，选择一个可独立验收的任务。
2. 多人协作或功能改动建议从 main 建 feature/xxx 或 fix/xxx 分支，再提交 PR；项目所有者明确要求直接提交推送时可按要求操作。
3. 根据改动运行相关测试与质量检查，记录真实结果及限制。
4. 接口变更同步调用方与 API 文档；功能状态更新「当前状态」，任务更新「开发计划」。
5. 提交并推送，避免把格式、无关重构和业务行为改动混在同一个提交。

首次克隆：

```powershell
git clone https://github.com/pretextQ/admin-agent.git admin-ai-agent
Set-Location admin-ai-agent
```

外部贡献者可 Fork 后添加本仓库为 upstream。已有本地仓库无需重新初始化 Git 或覆盖远程配置。

## 提交与检查

提交格式：`<type>(<scope>): <summary>`，常用 type 为 feat、fix、docs、refactor、test、chore。

```powershell
.\.venv\Scripts\ruff.exe check app/ tests/
.\.venv\Scripts\ruff.exe format --check app/ tests/
.\.venv\Scripts\mypy.exe app/
.\.venv\Scripts\python.exe -m pytest tests/admin_ai -q
```

前端改动按 [前端 README](frontend/README.md) 检查；集成与冒烟见 [测试计划](docs/guides/测试计划.md)。当前仓库没有已配置的 CI/pre-commit，也不宣称既有 lint 债已清零；新增改动应说明实际验证范围。

密钥与业务数据不提交。新增模型调用经 LLMGateway，管理接口鉴权、会话归属、审批规则、时间与迁移约定以开发规范为准。

## 问题反馈

在 [GitHub Issues](https://github.com/pretextQ/admin-agent/issues) 提供复现步骤、预期/实际行为、环境与脱敏日志。敏感问题按 [安全策略](SECURITY.md) 处理，不公开凭据或个人信息。
