---
title: "mcd-party · 麦拼单"
summary: "麦当劳多人拼单点餐 Skill：一句话需求（人数/预算/忌口）→ 门店定位 → 菜单 → 券组合 → 真实核价 → AA 拆单。写操作必须二次确认。"
read_when:
  - 用户要多人拼单点麦当劳
  - 用户说「拼单」「AA」「下午茶」「团队点餐」「带饭」
  - 需要调用麦当劳 MCP（mcp.mcd.cn）进行点餐规划
---

# 麦拼单 · mcd-party

办公室多人拼单点餐助手。把「5 个人、人均 35、有人不吃辣、帮我拼一单」这样的
一句话，变成一份**带真实核价和 AA 拆单**的拼单方案。

## 能力边界（先读这条）

- **默认只读**：查门店、拉菜单、查券、核价都不动账户状态。
- **写操作必须二次确认**：`auto-bind-coupons`（领券）、`create-order`（下单）、
  `cancel-order`、`party-order-create` 等会花钱或改变账户状态，必须向用户列明
  明细（门店、餐品、金额、券）并获得明确同意后才执行，**严禁静默执行**。
- **金额以 `calculate-price` 返回为准**：本地规划只做候选筛选，不替代实测核价。
- **券 ID 只有 `query-store-coupons` 返回**：`query-my-coupons` / `available-coupons`
  只给标题和状态，没有 couponId，喂不进算价入参。
- **到店 / 外送是两套菜单编码**：按当前 orderType 重新 `query-meals` 取码，
  用错编码算价会返回 `price:0` 且 `productList` 为空。
- **特调（modification）不承诺生效**：`calculate-price` 不回显特调结果，
  只确认不报错，不得向用户断言"已生效"。
- **无解就明说**：预算凑不出、忌口过滤完没菜、门店没货，直接说原因，不硬凑。

## 使用流程

### 方式 A：装了这个 Skill 的 Agent（推荐）

对 Agent 说：

> 帮我拼个麦当劳：5 个人，人均 35，我在深圳南山科技园，有人不吃辣，有人想要可乐。

Agent 按 `references/party-strategies.md` 的策略执行：
`now-time-info` → `query-nearby-stores`（定位）→ `query-store-coupons` + 
`query-my-coupons`（拿券）→ `query-meals`（当前渠道菜单）→ 
本地规划（见方式 C）→ `calculate-price`（多方案实测）→ 展示方案 →
用户确认 → `create-order`。

### 方式 B：只用 CLI（无需 MCP 客户端）

```bash
export MCD_MCP_TOKEN="你的Token"        # 或写入 ~/.mcd_mcp_token
python scripts/mcd.py check             # 连通性 + 工具数
python scripts/mcd.py tools             # 35 个工具清单（标注读写）
python scripts/mcd.py call query-my-account '{}'
```

### 方式 C：纯离线体验规划引擎（无需 Token）

```bash
python scripts/mcd.py plan --offline --people 5 --budget 3500 --avoid 辣
python tests/test_plan.py               # 11 个单测
```

## 拼单规划逻辑（scripts/mcd.py 内的纯函数）

1. `menu_to_items`：把 `query-meals` 返回归一成 `{code, name, price, category}`，
   兼容数组 / `products` / `categories` 三种结构；price 单位原样保留（线上为分）。
2. `filter_by_avoid`：按忌口词（辣/牛肉/鱼/鸡/海鲜…）过滤菜单，记录被过滤名单。
3. `pick_combo`：人均预算内为一人生成「主食+小食+饮料」组合（主食约占预算 45%），
   预算不够返回 None（不硬凑）。
4. `build_party_plan`：N 人规划 + 券建议（门槛可达成的最大优惠券）+ 汇总（原价 /
   优惠 / 预估实付 / 人均 AA）。
5. `render_plan`：终端文本表格输出，末尾固定提示「calculate-price 实测 → 确认 → 下单」。

## 文件说明

| 文件 | 作用 |
|---|---|
| `scripts/mcd.py` | CLI + 规划引擎，纯标准库，Python 3.9+ |
| `tests/test_plan.py` | 规划引擎离线单测（fixtures 驱动） |
| `fixtures/` | 离线样本：结构与编码取自线上实测记录，数值为构造 |
| `references/mcd-tools.md` | 35 个 MCP 工具速查 + 调用顺序 + 坑点 |
| `references/party-strategies.md` | 拼单策略方法论（何时用券、怎么拆单） |
| `config/preferences.json` | 默认偏好（预算档位、常见忌口、渠道） |

## 安全与合规

- Token 只从环境变量 `MCD_MCP_TOKEN` 或 `~/.mcd_mcp_token` 读取，
  **绝不写入仓库**；`mcp-config.example.json` 仅含 `${MCD_MCP_TOKEN}` 占位符。
- 限流 600 次/分钟/Token，CLI 串行调用，不做无意义重复查询。
- 本项目为第三方社区作品，与麦当劳中国无隶属、代理或背书关系；
  餐品信息、价格与供应状态以麦当劳官方渠道实时结果为准。
