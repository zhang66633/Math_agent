# 智能体能力升级：技能系统 + Agent 注册表

> 立项：2026-10-13　状态：**已实施，端到端验证通过**（B 技能系统 + D Agent 注册表）
> 回退锚点：`git tag pre-agent-upgrade`（commit `8fbf411`）+ 物理快照 `D:\_Projects\math_agent_snapshot_20261013`（192.9 MB，含未入库的 `backend/data/`）
> 关联：[RULES.md](../RULES.md)（技术栈红线）、[PLAN.md](../PLAN.md)（实施计划）、[defense-demo.md](./defense-demo.md)（答辩口径）

---

## 一、为什么要做

现在的智能体能力有三处结构性缺口，都来自「提示词与流程写死在代码里」：

1. **提示词是静态字符串。** 9 个 prompt 全在 `backend/app/core/prompts/*.py` 里硬编码；优化题、预测题、评价题拿到的是**同一套指令**，题型差别只体现在知识库检索回来的几段内容上。
2. **知识库只给「内容」，不给「流程」。** RAG 检索到的是方法卡（内容），但「这类题该按什么顺序建模、哪些坑必须避开」这类**流程性知识**没有载体。
3. **加一个智能体要改代码。** 7 个 agent 的名称写在 `core/router.py` 的 `AGENT_NODES` 常量里，节点与提示词模块的对应关系散落在 `workflow.py`，没有配置层。

## 二、参考来源（DSH，证据可查）

DSH 是插件化架构（cordis），287 个依赖包的**包名即能力清单**。本次直接借鉴其中两块的**设计**（不搬代码）：

| DSH 包 | 借鉴的机制 | 证据 |
|--------|-----------|------|
| `dsh-skill` / `dsh-skill-filesystem` / `dsh-tool-skill` | 技能注册表：多来源合并、frontmatter 摘要与正文分离、按需加载、`modelInvocable`/`userInvocable` 调用策略 | `dsh-skill/README.zh.md` |
| `dsh-agent-preset` / `dsh-agent-preset-registry` | 预设注册表：agent 定义外置、分层裁决（宿主层 / preset 层） | `dsh-agent-preset/README.zh.md`、其 `skills/*/SKILL.md` 实例 |

DSH 在它自己的 `agent-experience` 技能里写下的六条原则，本次作为设计检查表：

- 先给最小上下文（目的 / 可用动作 / 约束），细节按需加载；
- 让发现显式：每个延迟资源都要有清晰描述与可靠获取方式；
- 保持关键约束可见（权限、破坏性、必需校验要在动作之前）；
- 优先有界输出（返回简洁结果 + 标识符或路径，不倾倒整份日志）；
- 用局部性：结果带少量邻近上下文，**省略与截断必须显式标记**；
- **评估总工作量**：省上下文只有在不引起更多搜索 / 重复读取 / 错误时才有价值。

## 三、要做什么（本次范围）

### 3.1 技能系统（B）

**技能 = 一个目录，含 `SKILL.md`**（Markdown + YAML frontmatter，与 DSH 同构）：

```
backend/app/skills/
├── optimization-modeling/SKILL.md    # 优化类：模型选择与建模规范
├── prediction-modeling/SKILL.md      # 预测类
├── evaluation-modeling/SKILL.md      # 评价类
├── sensitivity-analysis/SKILL.md     # 灵敏度与鲁棒性分析（给检验员）
└── README.md                          # 编写规范
```

frontmatter 字段：

| 字段 | 必填 | 含义 |
|------|------|------|
| `name` | ✅ | kebab-case，与目录名一致（校验不通过快速失败） |
| `description` | ✅ | 一句话说明「什么时候该用它」——这是被匹配的依据 |
| `problem_types` | | 命中的题型（`optimization` / `prediction` / `evaluation` / `graph_theory` / `statistics` / `differential_equation` / `composite`），空表示不限 |
| `agents` | | 装配给哪些 agent 角色（`analysis` / `modeling` / `solving` / `verification` / `writing`），空表示所有执行型 agent |
| `auto` | | 是否参与自动装配（`true` 默认）；`false` 表示只在被显式点名时加载 |
| `priority` | | 同题型多个技能命中时的排序（默认 0） |

**加载器** `backend/app/skills/loader.py`：

- `list_skills()` → 只读 frontmatter 摘要（**不读正文**，对应 DSH「列举不读正文」）；
- `load_skill(name)` → 读完整正文；
- `resolve_skills(problem_type, agent_role)` → 按题型 + 角色选出技能，返回摘要列表；
- 进程级缓存 + 按文件 mtime 失效（对应 DSH「无 TTL、由提供方 invalidate」的简化版）；
- 校验失败只跳过该技能并告警，**不中断流水线**（对应 DSH「发现失败保留最后可用目录」）。

**装配**：在 `plan_execution`（planner）节点按 `problem_type` 解析技能，写入 `AgentState.active_skills`；各 agent 节点构建 system prompt 时把命中技能的正文附加到末尾（带 `## 专业技能` 小节标记）。**图拓扑不变，回退语义不变。**

### 3.2 Agent 注册表（D）

`backend/app/core/agent_registry.yaml` 成为 agent 定义的**唯一真源**：

```yaml
agents:
  - id: analysis
    node: analysis_agent
    label: 分析师
    model_role: analysis
    prompt_module: analysis
    uses_tools: false
    skills: true
  ...
```

`core/router.py` 的 `AGENT_NODES` 与 `workflow.py` 的节点注册表**从 YAML 派生**，加 agent 只改 YAML；测试守护「YAML 与图节点注册一一对应」，防止再次出现手抄表漂移。

## 四、明确不做（以及为什么）

| 不做 | 原因 |
|------|------|
| 动态子代理（方案 C） | 要引入 agent 生命周期、上下文隔离与回退语义交互，工期与演示风险都最高；先把技能与注册表做扎实 |
| 上下文压缩（方案 A） | 收益偏稳定性、答辩讲不出「智能体能力」；且要动求解与写作的消息组装，等 B/D 稳定后再上 |
| 照搬 DSH 的服务化插件架构 | 本项目是单机 FastAPI 应用，不需要 cordis 的插件生命周期与分层裁决；只取「文件即技能、摘要与正文分离」这部分 |
| 让技能影响图拓扑 | 技能只影响提示词内容，不影响调度——保持 11 节点与回退逻辑可预测 |

## 五、实施步骤与验收

```mermaid
flowchart LR
    A[1. 开发文档] --> B[2. 技能格式 + 加载器]
    B --> C[3. 5 个技能文件]
    C --> D[4. 接入 planner 与各 agent 节点]
    D --> E[5. Agent 注册表 YAML + 派生]
    E --> F[6. 回归测试]
    F --> G[7. 端到端跑一道题]
    G --> H[8. 提交 + 同步答辩口径]
```

| 步骤 | 验收标准 |
|------|----------|
| 技能加载器 | 单测覆盖：正常解析、frontmatter 缺失/名称非法被跳过、按题型匹配、缓存失效 |
| 技能文件 | 5 个技能均可加载，`description` 能说清「何时用」 |
| 装配 | 单测：优化题装配到 modeling 的 prompt 里能查到技能正文；评价题不装配优化技能 |
| 注册表 | 单测：YAML 派生的 `AGENT_NODES` 与 `workflow.py` 注册的节点集合完全一致 |
| 端到端 | 提交一道轻量题跑通 `completed`，`active_skills` 出现在事件流中 |
| 兼容 | 现有 148 个后端用例全绿；方案模式行为不变（技能是**附加**内容） |

## 六、风险与回退

- **风险**：技能正文挤占上下文（长任务本就吃紧）→ 用 `description` 做匹配、正文按需加载；技能正文设长度上限（超限告警）。
- **风险**：技能装错导致模型跑偏 → 技能默认只做「附加建议」，不改写原有指令的强制条款；且可一键关闭（`SKILLS_ENABLED=false`）。
- **回退**：`git checkout pre-agent-upgrade` 回到升级前；`backend/data/` 用快照目录回填。

## 七、决策记录（为什么这么定）

1. **技能放代码内（`app/skills/`）而非知识库目录**：技能是「指令」（影响模型行为），知识库是「内容」（供检索引用），两者生命周期不同——技能随代码评审与测试，内容随导入流水线增长。若将来要开放给用户扩展，再加一个知识库来源即可（加载器已按「多来源合并」设计）。
2. **frontmatter 摘要 + 正文分离**：列举阶段只读摘要，避免每次列技能都把全部正文读进内存，也避免把无关正文塞进提示词（DSH 同款设计）。
3. **技能不改图**：技能只影响提示词，不影响调度；调度逻辑（11 节点 + 回退）是答辩与测试的稳定基础。
4. **YAML 成为 agent 唯一真源而非新增一份配置**：原 `AGENT_NODES` 的价值就是「单一真源、不许手抄漂移」，改成 YAML 后这个性质保留，并额外获得可配置性。

---

## 八、实施结果（2026-10-13 实测）

| 验收项 | 实测结果 |
|--------|----------|
| 技能加载 | 5 个内置技能全部可用：优化 / 预测 / 评价三类建模规范、灵敏度分析规范、论文写作规范 |
| 题型匹配 | `optimization` → 目录 `[paper-structure, sensitivity-analysis, optimization-modeling]`；`composite` 与未知题型 → 只装配不限题型的两个 |
| 按角色装配 | modeling 1041 字符、writing 986 字符、verification 833 字符；analysis 与 solving 为 0（技能未声明给它们） |
| 注册表驱动 | `AGENT_NODES` 与注册表一致；7 个节点函数按 `entry` 动态装载；图构建成功 |
| 测试 | 后端 **175** 个用例全绿（新增 23：`test_skills.py` 15 + `test_agent_registry.py` 10，其中 2 个是本次 bug 的回归测试） |
| 端到端 | 轻量题任务 `9e3c2dd1` 跑通 `completed`；`plan` 事件携带 `skills` 目录；产出 6 个 artifacts；耗时约 3.5 分钟 |

## 九、踩坑记录

1. **frontmatter 只认第一个闭合标记。** 第一版用 `text.split("\n---", 2)` 切 frontmatter，正文里再无 `---` 时只能切出两段，直接判「未闭合」——5 个技能全被跳过，而加载器只打 warning，表面上就是「技能目录为空」。改为定位第一个 `\n---` 后取后半段。
   *教训*：解析器的边界条件必须拿真实文件验证，代码逻辑顺眼不代表对。

2. **目录阶段的角色过滤把技能全滤掉了。** `plan_execution` 生成技能目录时调用 `resolve_skills(problem_type)`（角色为空），而匹配函数把「无角色」理解成「必须匹配空角色」，于是所有声明了 `agents` 的技能均不匹配——端到端跑完 `skills=[]`，肉眼几乎看不出来，因为技能是附加内容，缺了照样出结果。
   修复：`agent_role is None` 表示**不限角色**，只有给定角色时才过滤；补 `test_catalog_without_role_is_not_filtered_by_agents` 守住。
   *教训*：**缺陷最容易藏在不影响主流程的地方**——「功能悄悄失效、任务照样成功」比直接报错危险得多，所以端到端验证要显式断言新增字段，而不是只看任务是否 completed。

3. **技能正文必须有长度上限。** 技能是「指令」不是「资料」，内置 5 个都在 6000 字符上限内；超限会截断并告警，提示该拆成 `references/`（对应 DSH 的 references 子目录做法）。

## 十、下一步（未做，按需接续）

- **前端展示技能目录**：`plan` 事件已带 `skills` 字段，前端时间线可显示「本题装配的技能」，目前未消费该字段。
- **上下文韧性（原方案 A）**：统一三处截断口径 + 长历史压缩，等技能稳定后接续。
- **动态子代理（原方案 C）**：风险最高，暂不做。
- **技能来源扩展**：当前技能内置在 `app/skills/`；加载器已按「多来源合并」设计，若要让用户自定义技能，再加一个知识库来源即可。
