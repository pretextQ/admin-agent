# 贡献指南

感谢你对 Admin AI Agent 项目的关注！本文档将指导你如何参与项目贡献。

> 仓库托管在 [Gitee](https://gitee.com/qiulongfei4408/admin-ai-agent)。
> 代码风格与开发约定分别见 [代码风格指南](docs/guides/代码风格指南.md) 与
> [开发规范](docs/guides/开发规范.md)。

---

## 目录

- [行为准则](#行为准则)
- [如何贡献](#如何贡献)
- [开发流程](#开发流程)
- [代码规范](#代码规范)
- [提交规范](#提交规范)
- [Pull Request 流程](#pull-request-流程)
- [问题反馈](#问题反馈)

---

## 行为准则

- 尊重每一位参与者
- 接受建设性批评
- 专注于对社区最有利的事情
- 对他人表示同理心

---

## 如何贡献

### 贡献方式

| 方式 | 说明 |
|------|------|
| 报告 Bug | 提交 Issue 描述问题 |
| 提出建议 | 提交 Issue 描述新功能 |
| 提交代码 | Fork 项目后提交 PR |
| 完善文档 | 修正错误或补充内容 |
| 代码审查 | Review 他人的 PR |

### 贡献领域

- 🐛 Bug 修复
- ✨ 新功能开发
- 📝 文档完善
- 🧪 测试补充
- 🎨 代码重构
- ⚡ 性能优化

---

## 开发流程

本项目使用 [uv](https://github.com/astral-sh/uv) 管理 Python 环境与依赖。

### 1. Fork 项目

```bash
# 在 Gitee 上 Fork 项目到自己的仓库
# 然后克隆到本地
git clone https://gitee.com/你的用户名/admin-ai-agent.git
cd admin-ai-agent

# 添加上游仓库
git remote add upstream https://gitee.com/qiulongfei4408/admin-ai-agent.git
```

### 2. 创建分支

```bash
# 同步上游代码
git fetch upstream
git checkout main
git merge upstream/main

# 创建功能分支
git checkout -b feature/你的功能名称
```

### 3. 准备环境（uv）

> **快捷方式（Windows + Git Bash 已验证）**：直接跑 `bash scripts/setup_dev_env.sh`，
> 它会检查/安装 uv、创建 venv 装依赖、生成 `.env`、检测并拉起 PostgreSQL/Redis、
> 建库迁移种子并跑测试；加 `--check` 只体检不安装。幂等，可反复执行。
> 下面是等价的手工步骤。

```bash
# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh
# 或
pip install uv

# 创建并激活虚拟环境（建议显式指定 3.12）
uv venv --python 3.12
source .venv/bin/activate  # Linux/macOS
# 或
.venv\Scripts\activate  # Windows

# 安装依赖（含开发依赖）
uv pip install -r requirements-dev.txt

# 国内网络受限时走镜像：
# uv pip install -r requirements-dev.txt --index-url https://pypi.tuna.tsinghua.edu.cn/simple
# uv 安装 Python 用：UV_PYTHON_INSTALL_MIRROR=https://registry.npmmirror.com/-/binary/python-build-standalone
```

> **pip 替代方案（不推荐）**：`python -m venv .venv && pip install -r requirements-dev.txt`。
>
> 注意：`pyproject.toml` 是依赖的唯一真相源，`requirements*.txt` 由 `uv pip compile` 派生，
> 请勿手工编辑；新增依赖请修改 `pyproject.toml` 后重新生成。

### 4. 开发与自测

```bash
# 代码检查（ruff 同时承担 lint 与格式化）
ruff check app/ tests/
ruff format --check app/ tests/

# 自动修复 / 格式化
ruff check --fix app/ tests/
ruff format app/ tests/

# 类型检查
mypy app/

# 单元测试
pytest

# 覆盖率（整体 ≥80%，CI 使用 --cov-fail-under=80）
pytest --cov=app --cov-report=term-missing

# 集成测试 / 端到端测试
pytest -m integration
pytest -m e2e

# 端到端冒烟（需 PG/Redis/开发桩/后端 均已启动）
PYTHONPATH=. python scripts/e2e_smoke.py
```

> 提交前请确保 `pytest` 全绿（当前基线：99 passed, 1 deselected）。
> 涉及主链路（对话/编排/工具/审批）的改动，建议再跑一次 `scripts/e2e_smoke.py`。

### 5. 提交代码

```bash
git add .
git commit -m "feat: 添加xxx功能"
git push origin feature/你的功能名称
```

### 6. 创建 Pull Request

在 Gitee 上创建 PR，填写说明信息。

---

## 代码规范

### Python 代码风格

- 遵循 PEP 8 规范
- 使用 ruff 进行代码检查与格式化（替代 black / isort / flake8）
- 使用类型注解，并通过 mypy 校验
- 详细约定见 [代码风格指南](docs/guides/代码风格指南.md) 与 [开发规范](docs/guides/开发规范.md)

```bash
# 代码检查
ruff check app/ tests/

# 代码格式化
ruff format app/ tests/

# 类型检查
mypy app/
```

### 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 文件名 | 小写下划线 | `user_service.py` |
| 类名 | 大驼峰 | `UserService` |
| 函数名 | 小写下划线 | `get_user_by_id()` |
| 常量 | 大写下划线 | `MAX_RETRY_COUNT` |

### 文档规范

- 公共 API 必须有文档字符串
- 复杂逻辑需要添加注释
- 注释说明"为什么"而不是"是什么"

---

## 提交规范

本项目遵循 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/) 规范。

### Commit 消息格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type 类型

| 类型 | 说明 |
|------|------|
| feat | 新功能 |
| fix | Bug 修复 |
| docs | 文档更新 |
| style | 代码格式（不影响逻辑） |
| refactor | 重构 |
| test | 测试相关 |
| chore | 构建/工具相关 |

### 示例

```bash
# 简单提交
git commit -m "feat(chat): 添加多轮对话支持"

# 详细提交
git commit -m "fix(intent): 修复意图识别置信度计算错误

- 修正置信度计算公式
- 添加边界值处理
- 补充单元测试

Closes #123"
```

提交正文使用中文，跨文档引用使用相对路径。

---

## Pull Request 流程

### PR 检查清单

- [ ] 代码符合项目规范
- [ ] 添加/更新了测试
- [ ] 测试全部通过
- [ ] 更新了相关文档
- [ ] Commit 消息符合规范
- [ ] 没有合并冲突

### PR 描述模板

```markdown
## 变更说明
简要描述本次变更的内容和目的。

## 变更类型
- [ ] 新功能
- [ ] Bug 修复
- [ ] 重构
- [ ] 文档更新
- [ ] 测试补充

## 测试情况
- [ ] 单元测试通过
- [ ] 集成测试通过
- [ ] 手动测试通过

## 截图（如有UI变更）
[截图]

## 关联 Issue
Closes #123
```

### 代码审查

- 所有 PR 需要至少 1 人审查
- 审查者会关注：
  - 代码质量和可读性
  - 测试覆盖率
  - 是否符合项目规范
  - 是否有潜在问题

---

## 问题反馈

所有问题与建议统一通过 Gitee Issues 提交：
[https://gitee.com/qiulongfei4408/admin-ai-agent/issues](https://gitee.com/qiulongfei4408/admin-ai-agent/issues)。

### Bug 报告模板

```markdown
## Bug 描述
简要描述问题。

## 复现步骤
1. 步骤一
2. 步骤二
3. 步骤三

## 预期结果
描述预期行为。

## 实际结果
描述实际行为。

## 环境信息
- OS: [e.g., Windows 11]
- Python: [e.g., 3.11.5]
- 项目版本: [e.g., v0.1.0]

## 日志/截图
[相关日志或截图]
```

### 功能建议模板

```markdown
## 功能描述
简要描述建议的功能。

## 使用场景
描述该功能的使用场景。

## 解决方案
描述你期望的解决方案。

## 其他信息
[其他相关信息]
```

---

## 联系方式

- 问题反馈：[Gitee Issues](https://gitee.com/qiulongfei4408/admin-ai-agent/issues)

---

感谢你的贡献！🎉
