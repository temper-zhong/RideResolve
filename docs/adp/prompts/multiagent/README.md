# Multi-Agent 版提示词

目标形态：ADP **Multi-Agent 模式 + 工作流编排协同**，五个 Agent 各自绑定角色隔离工具并**自主调用**。
总方案见 [`../../MULTI_AGENT_REBUILD_PLAN.md`](../../MULTI_AGENT_REBUILD_PLAN.md)。

## 文件

| 文件 | Agent | 绑定工具 | 凭证角色 |
|---|---|---|---|
| `evidence_collection_agent.md` | Evidence Collection Agent | `get_case_snapshot`, `get_trip_evidence`, `get_policy_rules` | `EVIDENCE_COLLECTION` |
| `rider_advocate.md` | Rider Advocate | `get_trip_evidence` | `RIDER_ADVOCATE` |
| `driver_advocate.md` | Driver Advocate | `get_trip_evidence` | `DRIVER_ADVOCATE` |
| `policy_precedent_agent.md` | Policy & Precedent Agent | `get_policy_rules`, `search_precedents` | `POLICY_PRECEDENT` |
| `judge.md` | Judge | 无 | 无 |

## 与旧版（`../`）的差异

旧版全部包含 "Do not call tools or emit tool-call syntax. This Agent has no attached tools."，配合工作流固定工具节点使用。

新版：

1. 删除该限制，改为明确列出**允许调用的工具**并强制 Agent 自行调用；
2. 输出契约新增 `tool_calls_made`（含真实 `request_id` 与 `SUCCESS|FAILED`），作为"自主取证"的可核验证据；
3. 新增"工具失败不得编造替代结果、不得重试或改写参数"的纪律条款；
4. Judge 增加"校验上游 `tool_calls_made` 是否全部 SUCCESS"的步骤。

## 使用方式

1. 在 ADP 新建 **Multi-Agent 模式**应用，协同方式切换为**工作流编排**；
2. 在应用设置中逐个新建 Agent，把对应文件里的 **System prompt** 粘进提示词栏；
3. 在「连接器与工具」中绑定该 Agent 的**角色工具**并配置**该角色的 APIKey**；
4. 用 **ADP 启动提示词** 作为 Agent 节点的输入模板；
5. 先做**单 Agent 调试**，再搭工作流，最后**全局调试**。

## 注意事项

- 凭证只能存在于 ADP 掩码鉴权字段中，绝不可写入提示词、工具描述或 Agent 输入。
- 服务端 fail-closed 授权不变：越权操作返回 HTTP 403 并审计。
- 旧的 `../` 目录提示词**不要删除**——它们对应当前已验证的 workflow-first 版本，是回退方案。
