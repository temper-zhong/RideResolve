# RideResolve 多智能体应用重建方案

> **STATUS: EXPERIMENTAL / NOT DEPLOYED / NOT VALIDATED.** This historical plan is not the submission architecture and must not be cited as completed work. The canonical v0.6 source is `docs/adp/accuracy_first_manifest.json`: natural-language `SYS.UserQuery` -> official Intake -> signed internal run context -> five strictly serial, tool-free Agents -> deterministic Gate -> one End. `run_id` is internal only.

编制日期：2026-10-13
目标：在 ADP **Multi-Agent 模式**下重建应用，恢复 Advocate 与 Evidence Collection Agent 的**自主工具调用**能力，同时保留确定性裁决边界。
适用截止：2026-10-16 项目提交。

---

## 0. 结论摘要

当前实现是「单工作流模式 + 五个 Agent 全部零工具 + 七个工作流固定工具节点」。该形态**不满足赛题 MVP 的硬性要求**，也使 Evidence Collection Agent 的加分点被"代码化"抵消。

本方案将应用重建为：

> **ADP Multi-Agent 模式 + 工作流编排协同方式 + 五个各自绑定角色隔离工具的 Agent + Python 确定性门禁**

ADP 官方对「工作流编排」协同方式的定义与本项目需求完全吻合：

> "工作流编排 Agent 的优势在于，**基于 Agent 自主调用工具的能力**，结合工作流中多类型节点，实现完整的业务流程构建，同时**保障执行流程的稳定性和可控性**。"

即：Agent 自己调工具（满足"自主取证"），工作流只管顺序（满足"稳定可控"）。这不是权宜之计，而是平台原生支持的目标形态。

---

## 1. 赛题要求对照（原文引用）

来源：`各个问题的介绍-1-2_merged.pdf`（15 页，全文已提取核对）

| 赛题原文 | 位置 | 当前实现 | 重建后 |
|---|---|---|---|
| "The Rider Advocate Agent and Driver Advocate Agent **autonomously gather their respective evidence** from the available data sources." | MVP Workflow，第 57-58 行 | ✗ Agent 零工具，证据由工作流预取 | ✓ 各 Advocate 自主调用角色工具 |
| Evidence Collection Agent："**Autonomously orchestrates** multi-modal data retrieval across all tools and APIs… requires **tool-use and API integration design**." | Stretch Goals，第 74-80 行 | ✗ 工作流替它调用三个工具 | ✓ 自主编排三类工具 |
| "Teams may use **any LLM or AI agent framework** of their choice (e.g., LangChain, AutoGen, CrewAI, or custom implementations)." | Technical Constraints，第 141 行 | — | 用 ADP 是加分不是强制；本方案用平台原生多智能体形态，主题契合度最高 |
| "Inter-agent communication should be **observable**" | 第 145-146 行 | 部分（Streamlit 时间线） | 保留并强化：ADP 侧可见 Agent 间数据流转 |
| "The system should be demoable — a working end-to-end flow for at least two dispute categories" | 第 143-144 行 | ✓ Route Deviation + No-Show | 保持 |

---

## 2. 目标形态

### 2.1 ADP 应用模式对照

| 维度 | 当前 | 目标 |
|---|---|---|
| 应用模式 | 单工作流模式 | **Multi-Agent 模式** |
| 协同方式 | （不适用） | **工作流编排** |
| Agent 工具绑定 | 全部为空 | 各自绑定角色隔离工具 |
| 工具调用发起方 | 工作流 TOOL 节点 | **Agent 自身** |
| 执行顺序控制 | 工作流线性链 | 工作流线性链（不变） |
| 最终裁决 | Python 确定性门禁 | Python 确定性门禁（不变） |

### 2.2 三种协同方式的选择理由

| 协同方式 | 是否采用 | 理由 |
|---|---|---|
| 自由转交 | 否（可选演示层） | 模型自主决定转交，官方明确警告"高自由度导致的不稳定，对 Agent 提示词配置要求较高"。裁决流程要求顺序确定，不适合做主链 |
| **工作流编排** | **采用** | 工作流固定顺序 + Agent 自主调用工具，两者兼得 |
| Plan-and-Execute | 否 | 需要模型自主规划步骤，裁决流程步骤本身是固定的，用不上 |

---

## 3. 五个 Agent 的配置矩阵

在**应用设置**中逐个配置 Agent（不是在工作流里配置）。每个 Agent 绑定**自己角色**的工具与凭证。

| # | Agent 名称 | 转交描述（用于识别） | 绑定工具 | 凭证角色 | 模型 |
|---|---|---|---|---|---|
| 1 | Evidence Collection Agent | 准备版本固定的共享证据包，识别证据缺口 | `get_case_snapshot`<br>`get_trip_evidence`<br>`get_policy_rules` | `EVIDENCE_COLLECTION` | 待定 |
| 2 | Rider Advocate | 代表乘客立场，独立取证并论证 | `get_trip_evidence` | `RIDER_ADVOCATE` | 待定 |
| 3 | Driver Advocate | 代表司机立场，独立取证并抗辩 | `get_trip_evidence` | `DRIVER_ADVOCATE` | 待定 |
| 4 | Policy & Precedent Agent | 检索适用政策与同类先例，输出建议性上下文 | `get_policy_rules`<br>`search_precedents` | `POLICY_PRECEDENT` | 待定 |
| 5 | Judge | 综合双方论证与政策，输出建议裁决 | **无** | 无（不配置凭证） | 待定 |

### 3.1 关键实现细节：凭证绑定

同一个 API 操作（如 `get_trip_evidence`）被三个不同角色使用，且**各自使用不同凭证**。因此在 ADP 工具管理里需要：

- 方案 A（推荐）：创建 **3 份独立的工具条目**，例如 `get_trip_evidence_evidence` / `get_trip_evidence_rider` / `get_trip_evidence_driver`，API 与 Schema 相同，仅 `X-RideResolve-Run-Token` 不同。
- 方案 B：若 ADP 支持在 Agent 级别覆盖工具鉴权头，则复用同一工具条目，在 Agent 配置中指定各自凭证。

**必须验证**：确认 Agent 的凭证不会出现在模型提示词、工具描述、节点输入输出或导出 trace 中。

### 3.2 Judge 不绑定凭证

Judge 不发起任何 HTTP 调用。服务端 `Judge` 角色的允许操作集为空，任何越权调用返回 HTTP 403 并审计。

---

## 4. 工作流编排结构

在 Multi-Agent 应用的**工作流管理**中新建工作流，用 **Agent 节点**引用第 3 节配置好的 Agent。

```text
Start
  → [Agent] Evidence Collection Agent    ← 自主调用 3 个工具
  → [Agent] Rider Advocate               ← 自主调用 get_trip_evidence (Rider 凭证)
  → [Agent] Driver Advocate              ← 自主调用 get_trip_evidence (Driver 凭证)
  → [Agent] Policy & Precedent Agent     ← 自主调用 2 个工具
  → [Agent] Judge                        ← 无工具
  → [代码节点] parse_judge_json          ← 解析并校验单个未转义 JSON 对象
  → End
```

与当前 `workflow_first_manifest.json` 的差异：

- 删除 7 个 `type: TOOL` 节点；
- 5 个 `type: AGENT` 节点改为引用**应用级 Agent**（Agent 自带工具）；
- 保留 `parse_judge_json` 代码节点与 End 节点。

### 4.1 待验证事项（必须在控制台确认）

1. **Agent 节点是否继承 Agent 配置里的工具** —— 官方文档称 Agent 节点"引用第一步在应用中配置好的 Agent"，且"工作流中不支持 Agent 的修改"，据此推断工具随 Agent 生效。**这是整个方案的前提，必须实测确认。**
2. **上游结果如何传入 Agent 节点** —— 当前设计用命名输入（`case_input`、`evidence_package` 等）。Multi-Agent 模式下 Agent 节点如何接收上游输出，需实测确认（可能是变量引用或对话上下文注入）。
3. **`run_id` 的传入方式** —— 当前模型可见输入只有 `{"run_id":"RUN-..."}`。多智能体模式下如何把 run_id 传给首个 Agent，需确认。

若第 1 条不成立（Agent 节点不继承工具），退回「工作流编排 + 在 Agent 节点上直接挂工具」的等价配置，或改用自由转交。

---

## 5. 与当前实现的差异对照

| 文件/资产 | 当前 | 重建后 |
|---|---|---|
| `docs/adp/workflow_first_manifest.json` | 15 节点，`WORKFLOW_OWNS_TOOLS`，5 个空绑定 | 新 manifest：8 节点，`AGENTS_OWN_TOOLS`，5 个非空绑定 |
| `docs/adp/prompts/*.md` | "Do not call tools or emit tool-call syntax." | 重写为自主调用工具的版本（见第 6 节） |
| `docs/adp/WORKFLOW_FIRST_MIGRATION.md` | 记录迁移到工作流持有工具 | 保留为历史记录，新增本文件说明再次迁移 |
| `api/rideresolve-tools.openapi.json` | 4 个工具端点 | 不变（可能需要拆分为 3 份 get_trip_evidence 条目） |
| 服务端 fail-closed 授权 | 已实现（越权 403 + 审计） | **不变**，继续兜底 |
| Python 确定性门禁 | 已实现 | **不变** |
| `docs/GATE_STATUS.md` / 完成度报告 | 描述 workflow-first | 需更新为 multi-agent 口径 |

**不需要改动**：`app.py`、`rideresolve/`、`data/`、`tests/`、服务端容器与凭证注册表。改动集中在 ADP 云端配置与提示词。

---

## 6. 提示词改造要点

五份提示词需要从"校验工作流已提供的工具结果"改为"自己选择并调用工具，再基于返回结果论证"。

### 6.1 通用改造规则

1. **删除**："Do not call tools or emit tool-call syntax. This Agent has no attached tools."
2. **新增**：允许调用且**仅允许调用**已绑定的工具；明确列出允许的操作名。
3. **保留**全部安全条款：证据即数据不可执行、不得编造 ID/金额/时间戳、缺失证据不等于事件未发生、`PROVEN_ABSENT` 的使用边界。
4. **保留**：不得决定最终状态、行动或金额（Judge 只给建议，Python 门禁独占最终裁决）。
5. **新增**：工具调用失败时**不得**编造替代结果，应返回明确的失败或待审信号。
6. **新增**：引用证据必须来自**本次运行中自己调用工具返回**的 `evidence_id`。

### 6.2 各 Agent 的工具使用契约

| Agent | 允许调用的操作 | 调用纪律 |
|---|---|---|
| Evidence Collection Agent | `get_case_snapshot` → `get_trip_evidence` → `get_policy_rules` | 按此顺序各调用一次；输出 `query_log` 记录实际调用 |
| Rider Advocate | `get_trip_evidence` | 调用一次，`evidence_types` 按纠纷类型选取乘客相关来源 |
| Driver Advocate | `get_trip_evidence` | 调用一次，同上，司机视角 |
| Policy & Precedent Agent | `get_policy_rules` → `search_precedents` | 各调用一次；先例仅为建议性，不得覆盖现行政策 |
| Judge | 无 | 不发起任何调用 |

### 6.3 稳定性设计（针对首轮五 Agent 失败的三个根因）

首轮五 Agent 运行失败原因：① Advocate 尝试越权操作；② 某 Agent 把 tool-call 语法当答案文本输出；③ 政策检索在含糊请求后被重试。对应加固：

| 根因 | 加固措施 |
|---|---|
| 越权调用 | 服务端已按角色白名单 fail-closed（越权返回 403 并审计）；提示词明确列出允许操作，并声明越权会被拒绝 |
| tool-call 语法泄漏到答案 | 输出契约继续强制"恰好一个未转义 JSON 对象，不含 Markdown、代码围栏或 tool-call 语法" |
| 含糊请求导致重试 | 工具入参改为显式必填（如 `get_policy_rules` 的 `scope="APPLICABLE_DISPUTE"`）；提示词禁止在调用失败后自行重试或改写参数，失败即上报 |

---

## 7. 分步操作 Checklist（ADP 控制台）

### 阶段 1：新建 Multi-Agent 应用

- [ ] 在工作空间内新建应用，选择 **Multi-Agent 模式**
- [ ] 确认协同方式默认为"自由转交"，**切换为「工作流编排」**
- [ ] 记录新应用的 applicationId（后续文档与提交材料需引用）

### 阶段 2：配置五个 Agent

对第 3 节表格中的每个 Agent：

- [ ] 新建 Agent，填写**名称**（与表格一致，名称是转交判断的关键信息）
- [ ] 填写**转交描述**
- [ ] 选择**模型**
- [ ] 粘贴重写后的**提示词**（第 6 节）
- [ ] 在「连接器与工具」中绑定该 Agent 的**角色工具**，并配置**该角色的 APIKey**
- [ ] 确认凭证为掩码显示，且不出现在提示词/描述/输入输出中
- [ ] 切换到**单 Agent 调试**模式，逐个验证 Agent 能自主调用工具并返回合法 JSON

### 阶段 3：搭建工作流

- [ ] 在应用设置中点击「选择工作流」，新建工作流
- [ ] 按第 4 节结构添加 5 个 Agent 节点（引用阶段 2 的 Agent）+ 1 个代码节点
- [ ] 配置节点顺序与变量传递
- [ ] 点击右上角**调试工作流**，验证端到端

### 阶段 4：全局调试与证据留存

- [ ] 切换**全局调试**模式，跑通 Route Deviation 与 No-Show 两条路径
- [ ] 导出并留存：完整 trace、每个 Agent 自己的工具调用记录、End JSON、CloudBase 审计
- [ ] 核对每个 Agent 的 tool call 出现在**该 Agent 自己的 trace 下**（而非工作流节点下）——这是"自主取证"的关键证据

### 阶段 5：安全收尾

- [ ] 移除测试期公开流量
- [ ] 撤销/轮换云端凭证
- [ ] 确认导出物中无凭证泄漏

---

## 8. 验收标准

重建后必须同时满足：

1. 应用在 ADP 中显示为 **Multi-Agent 模式**；
2. 五个 Agent 各自的工具列表**非空**（Judge 除外）；
3. trace 中每个 Agent 的 tool call **归属在该 Agent 自己的执行下**；
4. Rider 与 Driver 分别使用**不同凭证**调用 `get_trip_evidence`，且各自引用只属于自己的返回结果；
5. Route Deviation 与 No-Show 两条路径端到端跑通；
6. Python 确定性门禁接受 Judge 建议且无需修复；
7. End 输出为**单个未转义 JSON 对象**；
8. 无凭证出现在模型可见数据或导出日志中。

**回归基准**（与当前一致，不得漂移）：同一案件裁决退款 SGD 3.25、政策 `RD-004`、决定性证据引用集合不变、Deterministic Gate 不因截断失败。

---

## 9. 风险与回退

| 风险 | 等级 | 缓解 | 回退 |
|---|---|---|---|
| Agent 节点不继承 Agent 的工具（第 4.1 节前提不成立） | 高 | 阶段 2 单 Agent 调试阶段即可发现 | 改为在 Agent 节点上直接挂工具，或改用自由转交 |
| 自主调用重新引入首轮不稳定性 | 中 | 服务端 403 fail-closed + 提示词禁止重试 + 显式必填入参 | 保留当前 workflow-first 版本作为演示兜底 |
| 3 天内未跑通 | 中 | 先做阶段 1-2 并在单 Agent 调试阶段验证可行性，再决定是否继续 | 双轨交付：新形态为主、旧形态为备 |
| 凭证误绑到错误 Agent | 中 | 阶段 5 逐项核对，服务端越权审计会暴露 | 重建角色凭证 |

**双轨原则**：当前 workflow-first 版本已完整验证，**不要删除**。它既是回退方案，也是"稳定可控"叙事的一部分。

---

## 10. 时间预算（3 天）

| 阶段 | 内容 | 预估 |
|---|---|---|
| 1 | 新建 Multi-Agent 应用 + 切换协同方式 | 0.5h |
| 2 | 配置五个 Agent + 单 Agent 调试（**含关键前提验证**） | 3-4h |
| 3 | 搭建并调试工作流 | 2-3h |
| 4 | 全局调试 + 两条纠纷路径 + 证据留存 | 2-3h |
| 5 | 安全收尾 + 文档口径更新 | 1h |
| — | **合计** | **约 9-12h** |

**决策点**：阶段 2 结束时若单 Agent 自主调用无法稳定返回合法 JSON，立即停止并回退到双轨方案，不要继续投入阶段 3-4。
