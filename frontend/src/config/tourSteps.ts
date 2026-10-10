/**
 * 新手导览步骤配置（纯数据，由 useGuidedTour 编排）。
 *
 * - `route` 缺省 = 当前页（欢迎/收尾/侧边栏等无需切页的步骤）
 * - `selector` 缺省 = 居中 popover（无高亮元素）；否则高亮该 data-tour 锚点
 * - 文案以导航员第一人称撰写（人设见 README 智能体团队表）
 */

export interface TourStepDef {
  /** 该步所在路由；与当前路由不同时导览会自动切页并等待锚点渲染 */
  route?: string;
  /** 目标元素的 data-tour 锚点名（如 "chat-input" → [data-tour="chat-input"]） */
  selector?: string;
  title: string;
  description: string;
}

/** 导览内容版本号：改版文案后递增，可让老用户重新看到自动导览 */
export const TOUR_VERSION = "v1";

export const tourSteps: TourStepDef[] = [
  {
    // 首页 · 欢迎卡（居中）
    title: "你好，我是导航员",
    description:
      "别急，先看看你在哪、要去哪。接下来两分钟，我带你把整个平台走一遍。" +
      "随时可以按 ESC 或点 × 跳过；以后想重看，侧边栏底部的「功能导览」随时叫我。",
  },
  {
    // 当前页 · 侧边栏总览
    selector: "sidebar",
    title: "两大板块，一张地图",
    description:
      "上面是论文工作台——实战解题的地方：对话、方案、知识库。" +
      "下面是学习中心——从入门到竞赛的修炼场：工位、训练场、成长档案。想去哪，从这里出发。",
  },
  {
    route: "/chat",
    selector: "chat-input",
    title: "对话：随手问",
    description:
      "像聊天一样把问题抛过来。分析师拆题、建模师讲方法、求解器跑代码，" +
      "支持多轮追问、文件上传和联网搜索——选中页面上的文字还能直接「问AI」。",
  },
  {
    route: "/solution",
    selector: "solution-timeline",
    title: "方案：全流程流水线",
    description:
      "丢一道赛题进来，七位智能体接力干活：分析 → 建模 → 求解 → 验证 → 写论文。" +
      "右侧时间线实时直播每个节点的进度，图表、数据、论文最后打包带走。",
  },
  {
    route: "/knowledge",
    selector: "knowledge-tabs",
    title: "知识库：弹药库",
    description:
      "方法卡片、真题论文拆解、竞赛真题、框架模板都在这里。" +
      "对话和方案生成时，智能体会自动来这里检索弹药；你也可以手动翻阅、导入自己的资料。",
  },
  {
    route: "/learn",
    selector: "learn-role",
    title: "学习工位：先选身份",
    description:
      "建模手、编程手还是论文手？选好角色，技能树会为你定制路径——" +
      "61 个真实学习单元按依赖关系铺开，看不懂的地方右侧助手随时讲解。",
  },
  {
    route: "/practice",
    selector: "practice-tabs",
    title: "训练场：练兵之地",
    description:
      "选择题题库按角色分类，答错自动收进错题本，做对再移出。" +
      "掌握度随练习表现动态升降，到了遗忘临界点，「成长档案」会提醒你复习。",
  },
  {
    route: "/progress",
    selector: "progress-page",
    title: "成长档案：你的足迹",
    description:
      "学习热力图、数字大屏、成就勋章都在这里。管家每周播报一次你的进度——" +
      "你的每一点进步，都有人帮你记着。",
  },
  {
    route: "/apikeys",
    selector: "apikeys-page",
    title: "API Key：发动机燃料",
    description:
      "学习中心不配 Key 也完全能用；但 AI 对话、方案生成需要一个模型 Key" +
      "（DeepSeek / OpenAI 兼容均可）。Key 只保存在本机，放心填。",
  },
  {
    // 收尾 · 居中
    title: "地图交付完毕",
    description:
      "推荐路线：先去学习工位选个角色打基础 → 训练场练几题找手感 → 方案模式真刀真枪做一道题。" +
      "竞赛路上，我们七位随叫随到。",
  },
];
