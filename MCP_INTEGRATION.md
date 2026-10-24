# MCP_INTEGRATION.md — 麦当劳 MCP 接入说明

> 本文说明 mcd-party（麦拼单）实际使用的麦当劳 MCP Server、Tool、调用流程与业务价值。

## 1. MCP Server 信息

| 项 | 值 |
|---|---|
| 服务名称 | 麦当劳中国官方 MCP Server |
| 接入地址 | `https://mcp.mcd.cn` |
| 传输协议 | Streamable HTTP（不支持 WebSocket） |
| 鉴权方式 | 请求头 `Authorization: Bearer <MCP Token>` |
| 工具数量 | 35 个（`tools/list` 实测，2026-10） |
| 限流 | 每 Token 600 次/分钟，超限返回 429 |
| 覆盖范围 | 中国大陆（不含港澳台） |
| Token 获取 | [open.mcd.cn/mcp](https://open.mcd.cn/mcp) 手机号登录 → 控制台激活，免费 |

客户端实现见 `scripts/mcd.py`（纯 Python 标准库）：
`initialize` 握手 → `notifications/initialized` → `tools/list` / `tools/call`，
会话 ID 从响应头 `mcp-session-id` 提取并回带；响应兼容 JSON 与 SSE 两种格式。

## 2. 拼单流程实际使用的 Tool

| 阶段 | Tool | 读写 | 在拼单中的角色 |
|---|---|---|---|
| 0. 时间基准 | `now-time-info` | 读 | 确认当前日期/时段，判断活动与营业状态 |
| 1. 门店定位 | `query-nearby-stores` | 读 | 按拼单发起地址查附近门店，选定取餐/配送店 |
| 2. 地址（外送） | `delivery-query-addresses` / `delivery-query-stores` | 读 | 外送场景：确认收货地址与可配送门店 |
| 3. 菜单 | `query-meals` | 读 | 拉当前门店**当前渠道**菜单（到店/外送编码不同） |
| 4. 餐品详情 | `query-meal-detail` | 读 | 套餐组成、替换项、特调（modification） |
| 5. 券查询 | `query-store-coupons` | 读 | **唯一返回 couponId 的券接口**，拼单算价的券来源 |
| 5'. 券查询 | `query-my-coupons` / `available-coupons` | 读 | 我的券 / 可领券（只有标题状态，无 couponId） |
| 6. 账户 | `query-my-account` | 读 | 积分余额，判断积分商城/抽奖是否值得参与 |
| 7. 核价 | `calculate-price` | 读 | **金额唯一权威来源**：多方案实测比价 |
| 8. 写操作 | `auto-bind-coupons` / `create-order` | **写** | 领券 / 下单——**必须用户明确确认后执行** |

未使用但已评估的工具：积分抽奖类（`draw-lottery` 等）、积分商城类
（`mall-*`）、主题活动类（`party-*`）、营养类（`list-nutrition-foods`）——
拼单主链路不需要，避免无意义调用（限流 600 次/分钟）。

## 3. 完整调用流程

```
[用户输入] 人数 N、人均预算 B、地址、忌口、渠道偏好
    │
    ▼
now-time-info ────────────► 当前时间（活动/营业判断）
    │
    ▼
query-nearby-stores ──────► 附近门店列表 → 用户选定门店
    │ （外送则先 delivery-query-addresses → delivery-query-stores）
    ▼
query-store-coupons ──────► 该店可用券（含 couponId + 适用商品编码）
query-my-coupons ─────────► 我的券（标题/状态，补充参考）
    │
    ▼
query-meals ──────────────► 当前渠道菜单（code/name/price/category）
    │
    ▼
┌──────────────────────────────────────────────┐
│ 本地规划引擎（scripts/mcd.py 纯函数）          │
│  menu_to_items → filter_by_avoid → pick_combo  │
│  → build_party_plan（每人组合 + 券建议 + 汇总） │
└──────────────────────────────────────────────┘
    │
    ▼
calculate-price（每个候选方案各跑一次）──► 以返回值为准排序，选最优
    │
    ▼
[展示方案] 门店 / 每人明细 / 原价 / 优惠 / 实付 / 人均 AA
    │
    ▼ 用户明确确认（写操作红线）
auto-bind-coupons（如需领券）→ create-order（外送单可带 ≤50 字 remark）
```

## 4. 关键实测结论（影响设计的硬事实）

> 以下结论来自对线上 MCP 的实测记录（社区公开实测，2026-10；本项目开发者
> 复测验证，见 `references/mcd-tools.md`）。每条都直接决定了代码写法。
1. **券 ID 只有 `query-store-coupons` 返回**。`query-my-coupons` /
   `available-coupons` 只给标题/有效期/状态，没有 `couponId`，喂不进
   `calculate-price` 的券入参。→ 规划器的券池必须来自 `query-store-coupons`。
2. **`discount` 是相对券的原价口径**，不等于「省了多少」
   （实测冰美式中杯 `productOriginalPrice 2300` vs 促销价 `1190`，
   `discount 1310`）。→ README 与输出中不把 discount 当节省额展示。
3. **到店 / 外送是两套菜单编码**（巨无霸 到店 `1100` / 外送 `901100`）。
   用错编码 `calculate-price` 返回 `price:0`、`productList` 为空（不是下架）。
   → 规划前必须明确 orderType，菜单按渠道现取。
4. **`calculate-price` 不回显特调结果**，只确认不报错。→ 不对用户断言
   「特调已生效」。
5. **`create-order.remark` 仅外送（orderType=2）可用，≤50 字**；到店自取
   无备注入口。→ 免费配件（番茄酱等）引导走外送备注。
6. **无门店库存接口、无天气接口**（35 个工具中均不存在）。「这家店还有货吗」
   无法通过 MCP 回答。→ Skill 中明确此能力边界，不编造。
7. **`withOrder` 自动带入麦金卡体验卡并归零配送/打包费**，照抄返回值，
   不要自己拼价格。

## 4.5 本项目实测记录（2026-10-24 21:49 ~ 21:53，北京时间）

> 以下为本项目开发者对线上服务的真实调用记录（报名资质核验用）。
> 门店：麦当劳深圳同方信息港餐厅（storeCode `1420762`，科技园北区朗山路 11 号）。

| # | 调用 | 入参 | 结果 |
|---|---|---|---|
| 1 | `initialize` | protocolVersion 2025-03-26 | `serverInfo {"name":"mcd-mcp","version":"1.0.0"}`，`tools/list` 返回 **35 个工具**（与官方文档一致） |
| 2 | `query-nearby-stores` | `{"city":"深圳市","keyword":"南山科技园","searchType":2,"beType":1}` | `success:true`，返回同方信息港（403m）、禹洲广场（477m）、科技园长园得来速等门店；含营业时间、`reservation` 与预约时段 |
| 3 | `query-store-coupons` | `{"storeCode":"1420762","orderType":1,"beType":1}` | `success:true`，`data:[]`（该店到店渠道当前无可用券——真实空结果） |
| 4 | `query-meals` | 同上 storeCode | `success:true`，菜单 28,473 字符；本项目 `menu_to_items` 归一出 **111 个餐品**，覆盖主食/小食/饮料/甜品/小食拼盘多人餐等 14 个分类 |
| 5 | `calculate-price` | 3 件商品（板烧鸡腿堡三件套 `9900014838`、心形薯饼 8 块 `9900016566`、麦咖啡冰爽一夏 `9900015561`），`needTableware:false` | `originalPrice 6030` / `discount 1260` / **`price 4770`（¥47.70）**，`productList` 明细与原价小计齐全 |

**实测中抓到并修复的三个问题**（均已体现在代码与文档）：

1. **`query-nearby-stores` 只传 `keyword` 会报错**：`code 600058 "城市名或者关键词不能为空"`。
   必须 `city` + `keyword` 同时传（schema 上二者都是 optional，属隐性必填）。
2. **MCP 的 text 返回是「Markdown 说明 + JSON」拼接**：直接用 `json.loads` 会失败
   （说明区含 `{data[].title}` 这类模板占位符）。`mcd.py` 的 `extract_tool_text`
   与调用方需先定位 `{"success"` 再解析。
3. **价格单位不一致**：`query-meals` 的 `currentPrice` 是**元**（字符串 `"27.9"`），
   `calculate-price` 全字段是**分**（`2790`）。`menu_to_items` 已统一换算为分，
   换算逻辑有单测覆盖。

**写操作未执行**：`auto-bind-coupons` / `create-order` 等涉及真实扣款，
本项目在设计上要求用户明确确认后才执行，实测仅覆盖只读链路。

## 5. 业务价值

拼单是麦当劳场景里**决策链路最长**的一类需求：N 个人的偏好 × 预算约束 ×
券组合 × AA 结算，人工在小程序里要来回切换 N 次。麦拼单把这条链路压缩成
一次对话：

- **对用户**：人均预算可控、忌口不踩雷、券叠得明白、AA 精确到分；
- **对麦当劳 MCP 生态**：展示了「约束满足 + 真实核价 + 安全写操作」的
  Skill 工程范式——尤其是**写操作二次确认**与**金额以 calculate-price 为准**
  两条红线，可作为同类点餐类 Skill 的参考实现；
- **可复现性**：CLI + fixtures 让没有 Token 的人也能离线跑通规划引擎
  （`python tests/test_plan.py`，11 个用例）。

## 6. 安全与合规

- Token 仅从环境变量 `MCD_MCP_TOKEN` 或 `~/.mcd_mcp_token` 读取，
  **不进入仓库**；`mcp-config.example.json` 仅含 `${MCD_MCP_TOKEN}` 占位符。
- 限流友好：串行调用、复用会话内结果、不做无意义重复查询。
- 写操作（`auto-bind-coupons` / `create-order` / `cancel-order` /
  `party-order-create` / `draw-lottery` / `mall-create-order`）一律
  先列明细、获得用户明确同意后执行。
