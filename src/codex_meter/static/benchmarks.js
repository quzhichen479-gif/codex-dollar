(function (root, factory) {
  "use strict";
  const catalog = factory();
  if (typeof module === "object" && module.exports) module.exports = catalog;
  else root.CODEX_BENCHMARKS = catalog;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  // Fixed prompts only. This catalog performs no network requests or model calls.
  const questions = [
    {
      id: "pelican-svg",
      category: "SVG 作画",
      title: "鹈鹕骑自行车",
      summary: "用 SVG 画出一只正在骑自行车的鹈鹕，观察结构与空间关系。",
      prompt: "请画一只正在骑自行车的鹈鹕。只输出完整、可独立打开的 SVG 源码，不要 Markdown 代码围栏。使用 viewBox，全部图形由 SVG 元素绘制，不引用外部图片、字体或脚本。",
      rubric: [
        "能直接打开 SVG，画面没有被裁切，也没有借助外部图片。",
        "能辨认鹈鹕的长喙和喉囊，以及自行车的两个轮子、车架、车把和踏板。",
        "身体位于车座附近，翅膀与车把、脚与踏板的接触和遮挡关系合理。",
      ],
      reference: "此题没有唯一图形答案。把输出保存为 .svg 后查看成图；不能只凭源码长度或模型自述判断画得好不好。",
    },
    {
      id: "pelican-animation",
      category: "动画与一致性",
      title: "让鹈鹕踩起来",
      summary: "生成可离线播放的骑行动画，检查轮子、踏板与脚是否协调。",
      prompt: "制作一份可离线打开的单文件 HTML，用内联 SVG 画一只骑自行车的鹈鹕，并用 CSS 或 SVG 动画让它原地持续骑行。两个车轮应有可见轮辐，踏板围绕中轴转动，两只脚分别跟随相对的踏板，车架保持刚性。自行车面朝右，轮子按向右前进的方向转动。无需道路平移，也不要求严格物理传动比。提供暂停/继续按钮，并尊重 prefers-reduced-motion 设置（默认静止，可由按钮主动播放）。不使用外部依赖、图片或网络请求。只输出完整 HTML 源码，不要 Markdown 代码围栏。",
      rubric: [
        "离线打开能显示完整画面，轮辐清晰可见，两个车轮均顺时针旋转。",
        "踏板绕中轴旋转，左右脚始终贴合各自踏板，车架没有跟着扭曲或旋转。",
        "暂停/继续覆盖所有运动；减少动态效果模式下初始静止，仍可主动播放。",
      ],
      reference: "连续观察至少一个完整周期，再测试暂停/继续和减少动态效果。只让整个车轮圆形旋转、但看不出轮辐运动，不能充分展示旋转效果。",
    },
    {
      id: "coin-hth",
      category: "概率与推导",
      title: "等到 HTH 要多久",
      summary: "公平硬币首次出现“正、反、正”时停止，求期望投掷次数。",
      prompt: "连续独立投掷一枚公平硬币，H 表示正面，T 表示反面。首次在连续三次投掷中出现 HTH 时立即停止（允许不同候选片段重叠）。从尚未开始投掷算起，期望共投掷多少次？不要模拟；请定义状态、列出期望方程，并给出精确答案。",
      rubric: [
        "状态保留与目标串 HTH 的前缀匹配信息，而不是把每三次当作独立一组。",
        "已经匹配 H 后再出现 H，仍应保留 H 状态；HT 后出现 T 则回到初始状态。",
        "给出可复核的状态方程，并解得 10 次。",
      ],
      reference: "令 E0、EH、EHT 为尚无匹配、末尾为 H、末尾为 HT 时还需投掷的期望。E0 = 1 + (E0 + EH)/2；EH = 1 + (EH + EHT)/2；EHT = 1 + E0/2。解得 E0 = 10、EH = 8、EHT = 6。",
    },
    {
      id: "key-logic",
      category: "逻辑与不确定性",
      title: "钥匙是谁拿的",
      summary: "三人中一人拿了钥匙，三句话恰好一句真，信息足够定人吗？",
      prompt: "甲、乙、丙中恰好一人拿走了钥匙。甲说：『是乙拿的。』乙说：『是丙拿的。』丙说：『乙刚才那句话是假的。』已知这三句话恰好有一句为真。仅凭这些信息，能否唯一确定拿钥匙的人？请逐一检查三个候选人，列出所有符合条件的可能性。不要添加题目没有给出的条件。",
      rubric: [
        "把丙的话理解为对乙这句陈述的否定，不把它扩大成乙永远说谎。",
        "分别检查甲、乙、丙拿钥匙时三句话的真假，而不提前选定一个答案。",
        "明确结论无法唯一确定，符合条件的人是甲或丙。",
      ],
      reference: "若甲拿：假、假、真，符合。若乙拿：真、假、真，不符合。若丙拿：假、真、假，符合。因此甲、丙都可能，题目没有唯一人选。",
    },
    {
      id: "strict-json",
      category: "格式与约束",
      title: "一次满足全部条件",
      summary: "输出严格 JSON，同时满足字段、顺序、时长与中文字符数要求。",
      prompt: "只输出一个合法 JSON 对象，不要代码围栏、解释或注释。对象恰好包含 title、steps、total 三个键。title 必须是『周末实验』；steps 必须是按 n 升序排列的三个对象，每个恰好包含 n、seconds、label 三个键；n 依次为 1、2、3；seconds 是 10 到 30 之间的整数（含边界），三个数互不相同且总和为 60；每个 label 恰好四个汉字，不含标点、数字、字母或空格；total 为数字 60，并等于三个 seconds 的和。",
      rubric: [
        "整段输出可直接按 JSON 解析，没有前后说明、注释或代码围栏。",
        "顶层和各步骤只含指定字段，n 的值及顺序正确，数值没有写成字符串。",
        "三个 seconds 互异、都在范围内且和为 60；每个 label 都恰好四个汉字。",
      ],
      reference: '{"title":"周末实验","steps":[{"n":1,"seconds":15,"label":"检查输入"},{"n":2,"seconds":20,"label":"执行计算"},{"n":3,"seconds":25,"label":"核对结果"}],"total":60}',
    },
    {
      id: "interval-edges",
      category: "代码与边界",
      title: "区间合并，边界别合错",
      summary: "实现区间合并：只合并真正重叠的区间，接触端点要保留。",
      prompt: "用 Python 实现 normalize_ranges(ranges)。输入是整数二元组列表，每个 (start, end) 表示半开区间 [start, end)。只合并有非空交集的区间；仅端点相接的两个区间必须保留为两段。忽略 start == end 的空区间；遇到 start > end 抛出 ValueError；允许负数；不要修改输入列表；结果按起点升序，返回二元组列表，时间复杂度 O(n log n)。给出实现和 assert 测试，至少覆盖空输入、空区间、端点相接、重复、嵌套、重叠链、逆向区间、负数及输入不被修改。特别解释 [(1, 2), (2, 3)] 和 [(1, 3), (2, 4), (3, 5)] 的结果。",
      rubric: [
        "先验证和过滤区间，再对副本排序，不原地改变调用者的输入。",
        "比较 start < 当前合并区间的 end；仅用 <= 会错误合并端点相接的区间。",
        "用合并后的最大 end 处理嵌套和重叠链，测试确实覆盖题目要求的边界。",
      ],
      reference: "[(1, 2), (2, 3)] 应保持两段；[(1, 3), (2, 4), (3, 5)] 应得到 [(1, 5)]。[] 和 [(7, 7)] 都返回 []；[(2, 1)] 抛出 ValueError；[(-3, -1), (-2, 0)] 返回 [(-3, 0)]。排序 O(n log n)，随后线性扫描即可。",
    },
  ].map(question => Object.freeze({ ...question, rubric: Object.freeze(question.rubric) }));

  function chatgptUrl(prompt) {
    return `https://chatgpt.com/?q=${encodeURIComponent(prompt)}`;
  }

  return Object.freeze({ questions: Object.freeze(questions), chatgptUrl });
});
