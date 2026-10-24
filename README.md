# 麦拼单 · mcd-party

> 一句话，拼好一桌麦当劳。

办公室多人拼单点餐 Skill：输入人数、人均预算、忌口偏好，输出**带真实核价和
AA 拆单**的拼单方案。基于麦当劳中国官方 MCP（`https://mcp.mcd.cn`）开发，
本项目为「麦当劳程序员创意开发大赛（M-CODE）」参赛作品。

## 它解决什么问题

拼单最难的不是点餐，是**收尾**：

- 「5 个人人均 35，有人不吃辣」——怎么凑不超支还不踩忌口？
- 券有一把，满减券、单品券、0 元兑换券——**怎么叠最省**？
- 谁点了什么、谁该 AA 多少——**一笔一笔对不上**。

麦拼单把这三步一次做完：**规划 → 实测核价 → AA 拆单**。

## 目标用户

- 办公室拼单「伙食委员」：每周都要组织下午茶 / 团队餐
- 预算敏感的学生党 / 打工人：人均卡死，要花明白
- 有忌口需求的混合小组：辣 / 牛肉 / 海鲜，一键避开

## 功能特性

| 特性 | 说明 |
|---|---|
| 自然语言需求解析 | 「5 个人、人均 35、有人不吃辣」直接可用 |
| 门店定位 | 按地址查附近门店，拼单选大家都方便的店 |
| 菜单归一 | 兼容 `query-meals` 的数组 / `products` / `categories` 三种返回结构 |
| 忌口过滤 | 辣 / 牛肉 / 鱼 / 鸡 / 海鲜等别名映射，记录被过滤名单 |
| 组合规划 | 人均预算内「主食+小食+饮料」，主食约占预算 45%，无解明说 |
| 券组合建议 | 满 60 减 15 这类门槛券自动匹配，取门槛可达成的最大优惠 |
| AA 拆单 | 按实付均摊 / 按原价均摊，精确到分 |
| 安全边界 | 默认只读；领券、下单等写操作**必须用户明确确认** |

## 安装

### 方式 1：装进 WorkBuddy / 任意支持 Skill 的 Agent

对 Agent 说：

```
请安装这个技能：<本仓库地址>
保留 SKILL.md、scripts/、references/、config/ 的相对位置。
使用我已配置的麦当劳 MCP 连接器。
```

### 方式 2：配置麦当劳 MCP 连接器

Token 在 [open.mcd.cn/mcp](https://open.mcd.cn/mcp) 手机号登录 → 控制台激活获取（免费）。

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": { "Authorization": "Bearer ${MCD_MCP_TOKEN}" }
    }
  }
}
```

WorkBuddy：侧边栏「连接器」→「自定义连接器」→「配置 MCP」，粘贴上面内容
（`${MCD_MCP_TOKEN}` 替换为真实 Token，或配成本机环境变量）。

### 方式 3：只用 CLI（无需 MCP 客户端）

```bash
git clone <本仓库地址>
cd mcd-party
export MCD_MCP_TOKEN="你的Token"    # 或写入 ~/.mcd_mcp_token

python scripts/mcd.py check        # 连通性 + 35 个工具
python scripts/mcd.py tools        # 工具清单（读/写标注）
python scripts/mcd.py plan --address "深圳南山科技园" --people 5 --budget 3500
```

## 使用示例

### 示例 1：真实链路（2026-10-24 对线上 MCP 的实测记录）

```
门店：麦当劳深圳同方信息港餐厅（storeCode 1420762，科技园北区朗山路 11 号）

你：帮我核个价：板烧鸡腿堡三件套 + 心形薯饼 8 块 + 麦咖啡冰爽一夏，到店自取。

麦拼单：
1. query-nearby-stores（city=深圳市, keyword=南山科技园）→ 选定门店 1420762
2. query-store-coupons → 该店当前无可用券（真实空结果）
3. query-meals（orderType=1）→ 111 个餐品，确认 3 个编码在售
4. calculate-price 实测返回：
   原价 6030 分 / 促销优惠 1260 分 / 实付 4770 分（¥47.70）
   - 枫糖风味厚松饼猪柳蛋堡三件套 2790
   - 心形薯饼 8 块 2250 → 990（促销）
   - 麦咖啡冰爽一夏 990
   → 是否确认下单？（create-order，需明确确认）
```

> 拼单场景下，以上四步会按人数 N 扩展为「N 份组合各算一次价 + 券建议 + AA 拆单」，
> 见 `references/party-strategies.md`。

### 示例 2：离线体验规划引擎（无需 Token）

```bash
python scripts/mcd.py plan --offline --people 5 --budget 3500 --avoid 辣
```

```
========================================================
麦拼单 · 拼单方案（离线规划，金额以 calculate-price 实测为准）
========================================================
  1 号：麦香鱼 主食×1850；中薯条 小食×1150 → 小计 3000
  ...（每人一份）
--------------------------------------------------------
  原价合计：15000
  建议用券：满 60 减 15（麦麦省）（优惠约 1500）
  预估实付：13500    人均 AA：2700
  说明：已按忌口过滤：麦辣鸡腿汉堡、麦辣鸡腿汉堡套餐
========================================================
下一步（需用户确认后执行）：calculate-price 实测核价 → 确认 → create-order
```

### 示例 3：跑测试

```bash
python tests/test_plan.py     # 11 个用例，fixtures 驱动，无需 Token
```

## 安全边界（重要）

- **默认只读**：查门店、拉菜单、查券、核价均不改变账户状态。
- **写操作必须二次确认**：`auto-bind-coupons`、`create-order`、`cancel-order`、
  `party-order-create` 等，必须列明明细并获得用户明确同意后执行。
- **金额以 `calculate-price` 为准**：本地规划只做候选筛选，不替代实测。
- **特调不承诺生效**：`calculate-price` 不回显特调结果，只确认不报错。
- **到店 / 外送编码不同**：按当前 orderType 重新取菜单，避免 `price:0` 空返回。

## 技术栈

- Python 3.9+，**纯标准库**（`urllib` 直连 Streamable HTTP MCP，零依赖）
- JSON-RPC 2.0 over Streamable HTTP，`initialize` 握手 + 会话管理
- 规划引擎为纯函数，fixtures 离线可测

## 项目结构

```
mcd-party/
├── SKILL.md                   # Skill 入口（能力边界 + 使用流程）
├── README.md                  # 本文件
├── CONTEST_DECLARATION.md     # 参赛声明（官方原文，未做改动）
├── MCP_INTEGRATION.md         # MCP 接入说明（工具/流程/业务价值）
├── mcp-config.example.json    # 脱敏配置（仅 ${MCD_MCP_TOKEN} 占位符）
├── workbuddy.md               # WorkBuddy 开发对话上下文（参赛专项）
├── scripts/
│   └── mcd.py                 # CLI + 拼单规划引擎
├── tests/
│   └── test_plan.py           # 规划引擎单测
├── fixtures/                  # 离线样本（结构按线上实测，数值为构造）
├── config/
│   └── preferences.json       # 默认偏好
└── references/
    ├── mcd-tools.md           # 35 个 MCP 工具速查 + 坑点
    └── party-strategies.md    # 拼单策略方法论
```

## 参赛信息

| 项 | 内容 |
|---|---|
| 赛事 | 麦当劳程序员创意开发大赛（M-CODE） |
| 主办方 | 金拱门（中国）有限公司 |
| 开发工具 | 腾讯 WorkBuddy（见 `workbuddy.md`） |
| 报名 / 排名期 | 2026-10-09 10:30 ~ 2026-10-25 23:59（北京时间） |
| 排名依据 | GitHub 公开 Star 数 |

## 免责声明

本项目为第三方社区作品，由参赛者独立开发，**非麦当劳官方产品**，与麦当劳中国
及其关联方无隶属、代理、赞助或背书关系。项目输出仅供参考，不构成医疗、营养
或其他专业建议；餐品信息、价格及供应状态以麦当劳官方渠道的实时结果为准。
本项目不分发麦当劳 MCP 的任何源码、Token 或私密数据。

## License

MIT
