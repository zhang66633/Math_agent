# 方案 C 设计对比 — 学习单元与方法卡片内容模型合并

> 状态: **已实施**（2026-09，方向 3 + 建议选项；提交 `90cb0f5` `f625d02` `eac1426` `9322306`）
> 背景: [ARCHITECTURE_REVIEW.md](./ARCHITECTURE_REVIEW.md) P0-1
> 问题: 61 个学习单元（`backend/app/learning/content/**/*.md`）与方法卡片
> （`backend/knowledge_base/methods/**/*.yaml`）主题大面积重叠（LP/IP/AHP/TOPSIS/
> 灰色预测/GA/SA…），双份维护、两条读取路径、两套前端。

## 现状资产盘点

| 侧 | 内容 | 读取路径 | 消费方 |
|----|------|---------|--------|
| 学习 | 61 个 md 单元 + 183 题 quiz_data + 技能树/前置依赖（knowledge_graph.py） | `learning/unit_content.py` 直接读文件 | /learn、/learn/:unitId、practice、progress |
| 知识库 | 47 方法卡 + 17 论文 + 38 真题 + 3 模板（YAML 真源） | `knowledge/loader.py`（进程级缓存）+ Chroma 向量 + BM25 | /knowledge、chat 工具、solution 流水线、上传提取流水线 |

重叠判定：模型er 类 40 个单元中约 30+ 个与卡片同主题；programmer（13）与 writer（10）
两类 KB 无对应卡片，是学习侧独有。

## 三个方向

### 方向 1：卡片即单元（YAML 唯一真源）

方法卡片 schema 增加 `content_md` 长文字段，61 个 md 内容迁入 YAML；learning 读取层
改为走 KB loader。

- 收益: 一套 schema、一套缓存/失效、一套索引；上传流水线提取的新知识自动进入学习路径
- 成本: md → YAML 迁移（含公式/代码块的 YAML 转义风险）；183 题按 unit_id 重挂到卡片 id；
  LearningDoc 渲染源从文件变 API；技能树前置依赖要进卡片 schema
- 风险: 中高。YAML 长文本可读性差，后续手工编辑体验下降

### 方向 2：单元即卡片（md 唯一真源）

61 个 md 成为唯一内容真源，结构化字段进 front matter，方法卡片 YAML 由构建脚本生成。

- 收益: 内容编辑体验不变（写 md）；卡片/向量/BM25 全是构建产物，不会手改漂移
- 成本: front matter 规范设计；生成脚本接入索引构建；旧 YAML 退役策略；papers/problems/
  templates 不在 md 体系内，仍需保留 YAML（并未全统一）
- 风险: 中。多一步构建；结构化字段受 front matter 表达力限制

### 方向 3：双层合一 — 卡片挂长文，单元是卡片的视图（推荐）

不大迁大改，增量合并：

1. `MethodCard` schema 增加可选 `content_md`（长文，来自现有 md 的前世）
2. `learning/unit_content.py` 的数据源从「读 md 文件」改为「KB loader 读卡片」：
   有 `content_md` 的单元渲染长文（现有 LearningDoc 不变），没有的渲染结构化摘要
   （principle/formulas/applicable_when 现成字段）
3. 迁移脚本：约 30+ 个与卡片同主题的 md 作为 `content_md` 挂到对应卡片；
   programmer/writer 两类独有内容保留为独立单元（或后续补成卡片）
4. quiz（183 题）保留 unit_id，加 `unit_id → card_id` 映射表（一个 yaml），
   做题记录与掌握度追踪的存储不变
5. 技能树/前置依赖暂时不动（learning/knowledge_graph.py 独立维护），C 二期再并入
   卡片的 related_cards

- 收益: 增量迁移可回滚；缓存/失效/检索/上传流水线全部复用；前端 API 契约不变
  （unit_content 接口的返回结构不变，只是数据源换了）；「学的内容」和「查的内容」
  从此一份
- 成本: 迁移脚本 + 映射表 + unit_content 读取层重写 + 回归测试
- 风险: 低。每一步可独立提交/回滚；最坏情况退回读文件

## 需要拍板的三个决策点

| # | 决策 | 选项 | 我的建议 |
|---|------|------|---------|
| 1 | 方向 | 1 / 2 / 3 | **3**（增量、可回滚、复用全部现有机制） |
| 2 | 迁移范围 | A=全量 61 单元对齐 / B=只迁移与卡片重叠的约 27 个，独有内容保留 | **B**（独有内容本就没有重复，迁它纯成本） |
| 3 | quiz 挂载 | A=183 题改用卡片 id / B=保留 unit_id + 映射表 | **B**（做题记录/掌握度/错题本存储零改动） |

> ✅ 2026-09 用户拍板：方向 3 + B + B，已实施完毕（见下方实施记录）。

## 工作量预估（方向 3 + 建议选项）

schema 与迁移脚本 0.5d · unit_content 读取层重写 + 缓存失效接线 1d ·
映射表与 quiz 链路验证 0.5d · 回归测试（单测 + 真机走 /learn 全页面）1d ≈ **3 天**。

## 实施记录（2026-09）

**改动**：
- `knowledge/schemas.py`：MethodCard 增加 `unit_id` / `content_md`（可选字段）
- `learning/unit_content.py`：单元正文优先取卡片 content_md，回落 content 文件
- `knowledge/retriever.py`：`_card_to_document` 把 content_md（前 3000 字符）纳入索引文本
- 数据迁移：27 个 modeler 单元的 md 正文挂到对应卡片（`unit_id` + `content_md`），
  md 源文件删除；索引已重建（247 文档）
- `api/knowledge_shared.py` + 前端：卡片详情暴露 unit_id，可跳转 /learn/<unit_id>
- 测试：`test_plan_c_migration.py` 五个不变量；`test_path_generator.py` 旧「一单元一
  文件」不变量更新为「有正文即可」

**最终映射（27 迁 / 11 留，人工校正后）**：

| 单元 | 卡片 | 单元 | 卡片 |
|---|---|---|---|
| modeler_lp_01 线性规划 | mc_001 | modeler_entropy 熵权法 | mc_013 |
| modeler_ip_01 整数规划 | mc_002 | modeler_fuzzy_eval 模糊综合评价 | mc_012 |
| modeler_dp_01 动态规划 | mc_007 | modeler_dea_01 数据包络分析 | mc_019 |
| modeler_ga_01 遗传算法 | mc_003 | modeler_grey_rel 灰色关联分析 | mc_045 |
| modeler_sa_01 模拟退火 | mc_040 | modeler_mc_01 蒙特卡洛 | mc_010 |
| modeler_pso_01 粒子群 | mc_011 | modeler_shortest 最短路径 | mc_018 |
| modeler_multiobj NSGA-II | mc_024 | modeler_network 网络流 | mc_026 |
| modeler_ant_colony 蚁群 | mc_59 | modeler_mst 最小生成树 | mc_74 |
| modeler_reg_02 多元回归 | mc_021 | modeler_pca_01 主成分分析 | mc_014 |
| modeler_arima_01 ARIMA | mc_004 | modeler_ode_01 常微分方程 | mc_030 |
| modeler_grey_01 灰色预测 | mc_005 | modeler_pde_01 有限差分 | mc_093 |
| modeler_nn_01 神经网络 | mc_036 | modeler_queue_01 排队论 | mc_027 |
| modeler_ahp_01 层次分析法 | mc_008 | modeler_ca_01 元胞自动机 | mc_83 |
| modeler_topsis_01 TOPSIS | mc_009 | | |

保留文件形态的 11 个单元：lp_02 / heuristic_practice（practice 类）、ip_02 /
convex_opt / reg_01 / rf_01 / ahp_02 / mle_01 / bayes_01 / game_01 /
model_combo（无对应卡片或主题比卡片宽）。

**迁移中发现并顺带修复的数据问题**：8 张不同方法的卡片 id 全部撞成 mc_048
（批量导入缺陷），已重新分配 mc_090–mc_097（提交 `d534743`）。

**验证**：迁移后新进程校验全过；真机验证通过（迁移单元正文来自卡片、保留单元
来自文件、卡片详情返回 unit_id、quiz 按 unit 仍返回 3 题、搜索命中）；23 个
测试文件全过；ruff / vue-tsc / biome 全绿。

## 明确不做（本期范围外）

- 技能树前置依赖并入卡片 related_cards（learning/knowledge_graph.py 独立维护，二期）
- papers/problems/templates 与学习内容的合并（无重叠，无收益）
- 向量索引重建由启动时自动检测 + 迁移脚本显式触发双保险
