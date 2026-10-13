/**
 * 节点完成文案 —— 把后端 node_end 事件的事实字段翻译成给人看的一句话。
 *
 * 为什么单独成模块：文案规则要能被单测覆盖（不改 UI 就能验证），
 * 且**统一禁止**把「输出 N 字」这类实现度量当作结果汇报给用户
 * ——「字」是模型的 token/字符统计，不是用户关心的产物。
 * 用户要看的是：这一步产出了什么（几张图、几章论文、几个文件）。
 */

/** node_end 事件 data 里本模块用到的事实字段（旧任务可能缺字段）。 */
export interface NodeEndFacts {
  stage?: string;
  title?: string;
  /** 产物字符数：只作为「有没有内容」的判断依据，不直接展示 */
  output_length?: number;
  images_count?: number;
  xlsx_count?: number;
  csv_count?: number;
  files_count?: number;
  /** 验证节点结论（true = 通过） */
  passed?: boolean;
  /** 论文写作：红队审校结论 */
  red_team?: string;
  /** 论文正文一级章节数（后端写作节点统计） */
  sections?: number;
  /** 论文正文引用的图表数（后端写作节点统计） */
  figures?: number;
  skipped?: boolean;
}

function plural(n: number, unit: string) {
  return `${n} ${unit}`;
}

/**
 * 生成节点完成气泡的正文。
 *
 * 返回的每一句都是人话：不带字符数、不带内部字段名。
 */
export function describeNodeEnd(facts: NodeEndFacts): string {
  const images = facts.images_count ?? 0;
  const sheets = (facts.xlsx_count ?? 0) + (facts.csv_count ?? 0);

  // 1) 验证节点：结论就是价值本身
  if (facts.passed !== undefined) {
    return facts.passed ? "模型检验通过" : "检验未通过，触发回退重做";
  }

  // 2) 结果导出：有几个文件才是有信息量的
  if (facts.files_count !== undefined && facts.files_count > 0) {
    return `已导出 ${plural(facts.files_count, "个结果文件")}`;
  }

  // 3) 论文写作：章节与图表才是读者会去数的东西
  const sections = facts.sections ?? 0;
  if (sections > 0 || facts.red_team) {
    const bits: string[] = [];
    if (sections > 0) bits.push(plural(sections, "章"));
    const figures = facts.figures ?? 0;
    if (figures > 0) bits.push(plural(figures, "张图表"));
    if (facts.red_team === "REVISED") bits.push("红队修订完成");
    else if (facts.red_team === "PASS") bits.push("红队审校通过");
    return bits.length ? `论文已生成 · ${bits.join(" · ")}` : "论文已生成";
  }

  // 4) 求解：图表 / 数据表
  if (images > 0 || sheets > 0) {
    const bits: string[] = [];
    if (images > 0) bits.push(plural(images, "张图表"));
    if (sheets > 0) bits.push(plural(sheets, "个数据表"));
    return `求解完成 · ${bits.join(" · ")}`;
  }

  if (facts.skipped) return `已跳过：${facts.title ?? facts.stage ?? "该步骤"}`;

  // 5) 兜底：有标题就用标题，没有就如实说完成（绝不写字符数凑数）
  const name = facts.title ?? facts.stage ?? "";
  return name ? `已完成：${name}` : "已完成";
}
