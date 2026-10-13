# 外部资源索引（数学建模竞赛资料）

> 2026-10 经 firecrawl 8 路深度搜索整理；原始搜索结果在 `.firecrawl/`（已 gitignore）。
> 用途：① 扩充知识库 papers/problems；② 学习系统的资源推荐；③ 写作 agent 的格式参考。
> 2026-10 补充：第八节为 GitHub 同源项目**实测**数据（已 shallow clone 验证），回答「能否直接拉取」。

## 一、竞赛真题与官方源

| 资源 | 链接 | 说明 |
|------|------|------|
| 国赛官网（历年赛题） | https://www.mcm.edu.cn/html_cn/block/8579f5fce999cdc896f78bca5d4f8237.html | 官方源，**2026 年赛题已发布**（26-09-10），2025 及更早已归档 |
| 2025 国赛赛题 | https://www.mcm.edu.cn/html_cn/node/03c91a444e62eee81a3740fa97a461a6.html | A：烟幕干扰弹的投放策略；B：碳化硅外延层厚度的确定 |
| 2025 国赛 B 题解析视频 | https://www.bilibili.com/video/BV14Famz6Euv/ | 1-3 问完整思路 + 可运行代码 |
| CUMCM 历年试题速浏 | https://blog.csdn.net/qq_42818403/article/details/123046989 | 按年份+题号索引 |
| 数模知识库 wiki | https://www.shumo.com/wiki/doku.php?id=全国大学生数学建模竞赛_cumcm_历年试题 | 社区维护的历年试题 |
| 美赛 COMAP 官方结果 | https://www.contest.comap.com/undergraduate/contests/mcm/contests/2025/results/ | 2025 MCM A-C / ICM D-F 各题 Outstanding 获奖名单 + 完整结果 PDF |
| COMAP 历年赛事 | https://www.contest.comap.com/undergraduate/contests/mcm/previous-contests.php | 2019-2026 矩阵式索引 |

**2025 美赛题型**（COMAP 官方博客）：A 楼梯磨损与人类行为分析、B 森林变农田的土地利用变迁、C 奥运奖牌预测（MCM）；D-F 为 ICM 交叉学科题。2026 MCM Problem A 结果已出。

## 二、优秀论文资源

| 资源 | 链接 | 说明 |
|------|------|------|
| **zhanwen/MathModel** | https://github.com/zhanwen/MathModel | **国赛 2019-2023 优秀论文**，按年份/题号组织（如 2023C 极差的定义及标准分、2022B 方形件组批优化）。最适合直接走项目导入流水线扩充 KB |
| COMAP Outstanding 论文 | https://www.contest.comap.com/undergraduate/contests/mcm/contests/2025/results/ | 每题的 Outstanding Winner 论文 PDF（SIAM/INFORMS 等奖项标注） |
| 2025 MCM/ICM 43 篇 Outstanding | https://comap.org/blog/item/2025-mcm-icm-results | 官方公告 + 论文列表 |

## 三、数据集来源（数据预处理 agent 可推荐）

| 来源 | 链接 |
|------|------|
| 中国国家统计局 | http://www.stats.gov.cn/tjsj/ |
| World Bank Open Data | https://data.worldbank.org/ |
| Kaggle Datasets | https://www.kaggle.com/datasets |
| 美赛数据源汇总帖 | https://www.163.com/dy/article/ILS422SN0538057A.html |
| 数模资料渠道技巧（知乎） | https://zhuanlan.zhihu.com/p/1889822569659622482 |

## 四、教程与书籍（学习系统资源推荐用）

| 资源 | 链接 | 说明 |
|------|------|------|
| **DataWhale《数学建模导论》** | https://github.com/datawhalechina/intro-mathmodel | 开源十章教程：规划模型/复杂网络/进化计算/数据处理/评价模型/时间序列/机器学习——**与项目 61 个学习单元结构高度互补，可作为单元内容的引用源** |
| 司守奎《数学建模算法与应用》 | 国防工业出版社（第 3 版） | 经典教材；GitHub 配套解析 https://github.com/STL-CC/Mathematical-modeling-algorithm-and-Application |
| 姜启源《数学模型》 | 高等教育出版社 | 入门首选，案例全面 |
| 数学建模五类模型 50+ 算法手册 | https://zhuanlan.zhihu.com/p/19837671051 | 知乎汇总：评价/预测/分类/统计/优化 |
| 常见赛题类型与建模方案 | https://www.baltamatica.com/community/sposts/detail/7155a105-8129-c3f3-899a-cf653e2a7c58.html | 赛题三分类（评价/预测/优化） |

## 五、论文模板（写作 agent 格式参考）

| 资源 | 链接 | 说明 |
|------|------|------|
| **latexstudio/CUMCMThesis** | https://github.com/latexstudio/CUMCMThesis | 国赛 LaTeX 论文模板，**已适配 2026 年格式** |
| Overleaf cumcmthesis | https://www.overleaf.com/latex/templates/quan-guo-da-xue-sheng-shu-xue-jian-mo-jing-sai-bian-xie-de-latex/tkpdcwqsphwk | 在线版，无需本地 LaTeX 环境 |
| Word 模板（CSDN 汇总） | https://blog.csdn.net/qq_42818403/article/details/132634743 | Word 党参考 |

## 六、视频课程（B 站）

| 课程 | 链接 | 说明 |
|------|------|------|
| 清华大学数学建模公开课 | https://www.bilibili.com/video/av8824879 | 84 讲，体系最完整 |
| 从零开始学数学建模（北海） | https://www.bilibili.com/video/BV1UW4y1h74q/ | 38 集零基础向，MATLAB |
| 数学建模竞赛话题页 | https://m.bilibili.com/topic-detail?topic_id=1097982 | 聚合页：三天速成攻略、LaTeX 模板等 |
| 2025 国赛 B 题解析 | https://www.bilibili.com/video/BV14Famz6Euv/ | 单题精讲 |

## 七、可执行动作（按价值排序）

1. **KB papers 扩充**（最高）：从 zhanwen/MathModel 选 5-10 篇近年国赛优秀论文，PDF 走 `/knowledge` 上传 → LLM 提取流水线，papers 17 → 30+。上传流水线已支持 PDF/OCR/视觉模型。
2. **problems 录入**：2025/2026 国赛 + 2025 美赛真题按 `knowledge_base/problems/<竞赛>/<年份+题号>.yaml` 补录（现 27 道）。
3. **学习单元引用源**：DataWhale 导论各章链接挂到对应学习单元的「延伸阅读」；agent persona 里承诺的「推荐 B站视频/GitHub 仓库」有了具体弹药。
4. **写作 agent**：CUMCMThesis 2026 模板作为论文写作的格式基准（当前 writing agent 输出 Markdown/LaTeX 混排）。
5. **数据集推荐**：第三节来源接进数据预处理 agent 的系统提示，用户问「去哪找数据」时可直接给链接。

## 八、GitHub 同源项目实测（2026-10，已实际 shallow clone 验证）

> 结论先行：**技术上完全可以拉取**（三个仓库都 `git clone --depth 1` 成功，本机网络通 GitHub）。
> 但**可拉取价值与仓库体积基本成反比**——45MB 的仓库只有 0.13MB 是文本，0.33MB 的仓库几乎全是文本。
> 别按 star/体积判断，要看「文本知识密度」。

| 仓库 | 文件 | 总计 | 文本 | 文本文件 | 内容实质 | 建议 |
|------|------|------|------|----------|----------|------|
| [jihe520/MathModelAgent-Example](https://github.com/jihe520/MathModelAgent-Example) | 80 | **45.70 MB** | 0.13 MB | 12 | 上游项目的**运行产物**：41 PNG(15MB) + 5 docx(17MB) + 4 PDF + 2 ipynb(5MB) | ❌ 不值得整体入库。唯一有价值的是 5 份 `questions.txt`（约 10KB）与 2 篇 `res.md` 成文论文（各 25-27KB） |
| [Jaxon1216/mma-chart-templates](https://github.com/Jaxon1216/mma-chart-templates) | 32 | 3.06 MB | 0.04 MB | 16 | **14 类图型的 `template.py`**（bar/box_violin/bubble/dual_axis/grouped_bar/heatmap/line/multi_panel/network_graph/prediction_interval/radar/scatter_regression/stacked_bar/tornado_sensitivity），共约 35KB | ✅ **最值得拉取**。每个都是 `apply_chart_style()` + `create_chart()`，注释明写「运行时 agent 注入用」——与项目 `chart-standards` 技能（给规范）正好互补（给可跑代码） |
| [LiXiang106991/MathModelAgent](https://github.com/LiXiang106991/MathModelAgent) | 40 | 0.33 MB | 0.32 MB | 37 | Claude Code Skills 集合 + 方法知识 md（`optimization.md` 7KB / `prediction.md` 4.6KB / `all in.md` 4.4KB）+ 数据预处理 tools | 🟡 体积友好，但是 prompt 材料，与项目自有 skills 体系重叠；方法 md 可作 KB 扩充种子，但需走 LLM 提取（花钱） |

### 8.1 一个具体的高价值机会：真题库停在 2023

Example 仓库里有 **2024 国赛 C 题、2025 国赛 A/B/C 题、2023 华数杯 C 题**的题面原文，
而项目 `knowledge_base/problems/` 最新只到 **2023**（实测年份分布 2002-2023，论文同）。
2025/2026 赛题官网已发布（见第一节），这是 KB 最明显的一块空缺。

**但先别急着导**——本项目自己踩过的坑（见末节）：目录名不可信。
`2023 华数杯` 这类赛事名在 KB 现有四分类（国赛/美赛/研赛/华中赛）里没有对应项，
**导入前必须先读原文核实赛事归属**，否则会造出无法被 `competition` 字段正确归档的脏数据。

### 8.2 拉取方式建议

- **不要整体 clone 进仓库**：45MB 里 99.7% 是二进制产物，会把仓库撑爆且无检索价值。
- **按需取文件**：需要哪份就单独抓（`gh api` / raw 链接 /  shallow clone 到 TEMP 再筛），
  文本进 Git、二进制留库外。
- **绘图模板的落地形态**：把 14 个 `template.py` 折进 `chart-standards` 技能或新建
  `chart-templates` 技能。**注意代价**：该技能挂在 solving / data_preprocessing 两个 agent 上，
  正文变长会抬高每次调用的 prompt 成本，建议只放「按图型索引 + 按需展开」而不是全量铺开。

---

## 搜索方法论备注

- 8 路查询：国赛真题 / 美赛结果 / 算法教程 / 优秀论文 / 数据集 / 书籍 / LaTeX 模板 / 视频课程。
- 高价值源特征：官方域（mcm.edu.cn、contest.comap.com）> 高校/出版社 > 个人博客聚合帖；GitHub 仓库优先看目录结构是否按年/题号组织（决定能否脚本化批量导入）。
- **导入实测教训（2026-10）**：zhanwen/MathModel 的「国赛论文」目录里混装着研赛论文（2022B 三篇、2023C 十一篇经 PDF 首页核实均为华为杯研赛）——**目录名不可信，批量导入前必须读 PDF 首页裁定赛事**；LLM 从正文提取的 competition 反而可靠。同题多篇走上传流水线时输出文件名会自动追加 entry_id 去重（`_unique_output_path`），但年份等元数据仍需人工抽查（本次 paper_020 被提取成 2023，实为 2022）。
