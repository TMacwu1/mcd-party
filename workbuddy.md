# workbuddy.md — WorkBuddy 开发对话上下文

> 本文件用于「麦当劳程序员创意开发大赛（M-CODE）」WorkBuddy 专项奖励申报：
> 记录参赛项目 **mcd-party（麦拼单）** 使用腾讯 WorkBuddy 智能体完成的开发过程。
> 所有开发环节（调研、设计、编码、测试、文档）均由 WorkBuddy 自主执行，
> 人类参与者仅提供任务授权、外部凭证（MCP Token）与最终确认。

## 1. 任务背景

- **时间**：2026-10-24（1024 程序员节）21:17，大赛报名截止前约 26 小时
- **任务授权**：用户原话「麦当劳 M-CODE，全权给你开始干，要做哪些东西，你有没有把握」
- **约束**：报名截止 2026-10-25 23:59（北京时间）；仓库创建时间须在
  2025-12-25 ~ 2026-10-25；排名依据 GitHub 公开 Star 数

## 2. WorkBuddy 执行过程

### 阶段 1：规则调研（Web 检索）

提示词方向：「麦当劳 M-CODE 大赛规则、GitHub M-China 仓库、Token 获取方式」

获取并落盘的关键事实：

- 官方活动仓库 `M-China/mcd-developer-innovation-challenge` 的
  `activityGuidelines.md`（规则全文）与 `CONTEST_DECLARATION.md`（参赛声明原文）
- 报名 Issue 格式：`【参赛申请】` + 项目名称/地址/简介，**标题正文间不留空行、
  地址用裸链接**，否则校验打回
- 五个必备文件：`README.md` / `CONTEST_DECLARATION.md`（原文一字不改）/
  `MCP_INTEGRATION.md` / `mcp-config.example.json`（仅环境变量占位符）/
  `workbuddy.md`
- MCP 接入：`https://mcp.mcd.cn`，Streamable HTTP，`Bearer` 鉴权，
  35 个工具，600 次/分钟限流，Token 在 open.mcd.cn/mcp 控制台激活

### 阶段 2：竞品与技术基线（Web 检索 + 文档分析）

提示词方向：「麦当劳 MCP 35 个工具实测清单、已有参赛作品」

- 拉取社区实测文档（35 工具速查、调用顺序、坑点），识别出影响设计的关键事实：
  券 ID 仅 `query-store-coupons` 返回；到店/外送两套菜单编码；
  `calculate-price` 为金额唯一权威来源；写操作需二次确认
- 差异化定位：避开已扎堆的单人点餐/省钱助手，选择**多人拼单**场景
  （决策链路最长：N 人偏好 × 预算 × 券组合 × AA 结算）

### 阶段 3：实现（WorkBuddy 本地编码）

- `scripts/mcd.py`（约 540 行）：MCP 客户端（JSON-RPC over Streamable HTTP，
   initialize 握手、会话 ID 管理、JSON/SSE 双模解析、退出码语义化）
  + 拼单规划引擎（`menu_to_items` 归一 / `filter_by_avoid` 忌口过滤 /
  `pick_combo` 预算内组合 / `build_party_plan` 券建议+汇总 / `render_plan` 输出）
- `fixtures/`：结构与编码取自线上实测记录，数值为构造（文件内已标注）
- `tests/test_plan.py`：11 个用例，fixtures 驱动，无需 Token

### 阶段 4：验证（WorkBuddy 本地执行）

- 单测：**11/11 通过**（含无解场景、忌口过滤、券选择、AA 计算）
- 修复记录：fixtures 层级取错（dict 当 list）、测试断言餐品数数错（10→12）
- 离线演示：`python scripts/mcd.py plan --offline --people 5 --budget 3500 --avoid 辣`
  → 5 人方案 + 满 60 减 15 券建议 + 人均 AA 2700
- 兼容性：Windows 下 stdout 强制 UTF-8（`sys.stdout.reconfigure`），
  避免中文乱码

### 阶段 5：参赛文档（WorkBuddy 编写）

- `SKILL.md` / `README.md` / `MCP_INTEGRATION.md` / `mcp-config.example.json`
- `references/mcd-tools.md`（35 工具速查 + 10 条坑点）/
  `references/party-strategies.md`（拼单策略八章）
- `CONTEST_DECLARATION.md`：官方原文拷贝，MD5 校验一致
  （`91A7B32EC28098B609CA3F215CDF7147`）

### 阶段 6：MCP 实测（2026-10-24 21:49 ~ 21:53，Token 获取后执行）

- `initialize`：`serverInfo {"name":"mcd-mcp","version":"1.0.0"}`，协议 2025-03-26，
  `tools/list` 返回 **35 个工具**（与官方文档一致）
- 只读全链路实测通过（门店：麦当劳深圳同方信息港餐厅 storeCode 1420762）：
  1. `query-nearby-stores`（city+keyword+searchType=2）→ 3+ 真实门店；
  2. `query-store-coupons` → `data:[]`（该店当前无券，真实空结果）；
  3. `query-meals` → 28,473 字符真实菜单，归一 **111 个餐品**；
  4. `calculate-price`（3 件真实商品）→ `originalPrice 6030 / discount 1260 /
     price 4770（¥47.70）`
- 实测抓到并修复 3 个问题：① `query-nearby-stores` 隐性要求 city+keyword 同传
  （只传 keyword 报 600058）；② MCP text 返回是「Markdown 说明 + JSON」拼接，
  须先定位 `{"success"` 再解析；③ **价格单位不一致**：菜单 `currentPrice` 是元
  （"27.9"）、`calculate-price` 是分（2790），`menu_to_items` 已统一换算为分。
- 单测回归：**11/11 通过**（单位换算修复后）。
- 写操作（领券/下单）按设计未执行——需用户明确确认，留给真实使用场景。

## 3. 技术决策记录

| 决策 | 理由 |
|---|---|
| 纯 Python 标准库，零依赖 | 参赛作品可复现性优先；`urllib` 足够覆盖 Streamable HTTP |
| 规划引擎做成纯函数 | 无 Token 也能跑测试和演示；与网络层解耦 |
| 先拿券再点菜的策略顺序 | 券的适用商品决定点什么，顺序反了会做无用枚举 |
| MVP 不做多券叠加优化 | 单张最优券讲明白 > 堆组合优化复杂度；README 已声明边界 |
| 写操作二次确认写进 SKILL.md 能力边界 | 真实花钱操作，Agent 自主执行的必要红线 |
| fixtures 标注「数值为构造」 | 不假装是真实快照，诚实优先 |

## 4. 人类参与者操作

1. 任务授权与方向确认（2026-10-24 21:29）
2. 获取麦当劳 MCP Token（open.mcd.cn/mcp 手机号登录激活）——**已完成**（2026-10-24 晚）
3. GitHub 仓库创建与推送授权——**已完成**（仓库 TMacwu1/mcd-party）
4. 参赛 Issue 提交前终审——**已完成**

### 阶段 7：推送与报名（2026-10-24 23:00）

网络环境实测：git push 直连 github.com:443 超时（墙），本地代理对 git smart HTTP 返回 502。
换用 GitHub Git Data API（api.github.com 可达）完成原子提交：
- 空仓库先用 contents API 创建 README.md 作为初始提交（tree API 对空仓库返回 409）
- 再以 trees/commits/refs 一次性提交剩余 13 个文件（tree 不带 base_tree 会全量替换，README.md 需补回）
- 最终远端 14 个文件，参赛五件套齐全

参赛报名 Issue 已提交（官方仓库 M-China/mcd-developer-innovation-challenge #1304），
标题「麦拼单 —— 基于麦当劳 MCP 的多人拼单点餐 Skill」，正文按官方模板（【参赛申请】+ 项目名称/裸链接/简介，
标题正文间无空行）。等官方机器人回复报名结果。

全部开发对话由 WorkBuddy 完成（含 MCP 实测、单测修复、网络排障、API 推送方案）。

