# docs/ — 开发文档索引

根目录只保留三份权威文档：`README.md`（门面）/ `RULES.md`（红线）/ `PLAN.md`（实施计划）。
其余文档按「现行 / 历史归档」两级放在本目录，避免根目录文档互相漂移、新人无法判断以谁为准。

## 现行（仍可能被引用/更新）

| 文档 | 内容 |
|------|------|
| [solution-ux-audit-2026-10.md](./solution-ux-audit-2026-10.md) | 2026-10-13 方案模式 / 训练场交互审计：错题页横向溢出、图表重复的三条来源、论文引用不存在图片（12df70f4 实证）、进度文案去字符数、右栏交付物分组与导出取最新、会话-任务对齐；含验证记录与未修清单 |
| [AUDIT-2026-10.md](./AUDIT-2026-10.md) | 2026-10 全面审计：P0/P1/P2 与知识库数据债**全部闭环**；含 CI 修复记录、知识库四项充实（真题补齐 38→41 / 重名卡合并 86→81 / 字段缺口归零 / 14 类图表模板）、索引重建收尾与过程教训 |
| [functional-audit-2026-10.md](./functional-audit-2026-10.md) | 2026-10-14 功能层审计：209 测试全绿 + 全链路实测；**新发现 1 个 P0**（22/86 方法卡详情 500 + 编辑保存抹字段的数据毁灭路径）与 1 个 P1 死功能（Working Memory 问题状态文档永不更新） |
| [ARCHITECTURE_REVIEW.md](./ARCHITECTURE_REVIEW.md) | 2026-09 架构全面审查：实测数据、P0/P1/P2 问题清单、三条简化路线（A 文档与入口统一 / B 结构收敛 / C 内容模型合并）与目标架构图 |
| [learning-system.md](./learning-system.md) | 学习系统设计（技能树 / 掌握度追踪 / 题库 / 61 个学习单元） |
| [agent-skills.md](./agent-skills.md) | 智能体能力升级：技能系统（按题型装配提示词）+ Agent 注册表（定义外置 YAML），含踩坑记录 |
| [full-test-report.md](./full-test-report.md) | 全量功能测试报告（2026-10-13）：48 项接口实测、导出与公式渲染专项、修复的 3 个导出缺陷、已知限制 |
| [roadmap.md](./roadmap.md) | 资源清单与开发路线图 |
| [resources/README.md](./resources/README.md) | 外部资源索引（竞赛真题/优秀论文/数据集/教程/模板，2026-10 深度搜索整理，含可执行动作） |
| [deploy-cloud.md](./deploy-cloud.md) | 云服务器部署指南 |
| [memory-context-guide.md](./memory-context-guide.md) | 记忆管理、上下文管理与长任务开发经验总结 |

## archive/ — 历史归档（记录决策与踩坑，不作开发依据）

| 文档 | 内容 |
|------|------|
| [archive/ARCHITECTURE.md](./archive/ARCHITECTURE.md) | 早期 Next.js + MUI 架构蓝图（**已废弃，禁止作为开发依据**，仅作背景） |
| [archive/PLAN_V2.md](./archive/PLAN_V2.md) | Phase 2 改进方案（OOM / 方案模式 / 知识库） |
| [archive/NEXT_DEV_PLAN.md](./archive/NEXT_DEV_PLAN.md) | 后续开发计划与双人分工 |
| [archive/IMPROVEMENT_PLAN.md](./archive/IMPROVEMENT_PLAN.md) | NB_project 问题清单与解决方案（多人协作版） |
| [archive/AUDIT_REPORT.md](./archive/AUDIT_REPORT.md) | 2026-08-24 五模块链路验核报告 |

> 归档文件保留原始内容与相对链接修正记录——它们回答的是「当时为什么这么决定」，
> 按项目规则（把「为什么」记录下来比把代码写完更重要）不删除、不改写结论。
