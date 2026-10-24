# 麦当劳中国 MCP 工具速查（mcd-party 参考）

来源：`M-China/mcd-mcp-server` 官方 README + 社区线上实测记录（2026-10）。
本项目开发者已对关键结论复测，**与线上 `tools/list` 冲突时以线上为准**。

服务地址：`https://mcp.mcd.cn`（Streamable HTTP，`Authorization: Bearer <token>`）
**工具总数：35**，限流 600 次/分钟/Token。

## 活动 / 券 / 账户（8）

| Tool | 用途 | 写 |
|---|---|---|
| `now-time-info` | 当前完整时间信息 | |
| `campaign-calendar` | 活动日历（当月进行中/往期/未来） | |
| `available-coupons` | 麦麦省可领券列表（无 couponId） | |
| `auto-bind-coupons` | 一键领全部可领券 | **是** |
| `query-my-coupons` | 我的券（标题/状态，无 couponId） | |
| `query-my-account` | 积分（可用/累计/冻结/将过期） | |
| `query-store-coupons` | **门店可用券（有 couponId + 适用商品编码）** | |
| `query-survey-coupon` | 按订单号查 CSAT 答卷关联奖券 | |

## 点餐主链路（10）

| Tool | 用途 | 写 |
|---|---|---|
| `query-nearby-stores` | 按地址查附近门店 | |
| `query-meals` | 当前门店当前渠道菜单（分类/编码/标签/优惠价） | |
| `query-meal-detail` | 餐品详情、套餐组成、替换项、特调 modification | |
| `calculate-price` | 按选购列表（可含券与特调）算金额/配送费/打包费/应付 | |
| `create-order` | 创建订单 + 支付链接；外送支持 remark(≤50 字)与特调 | **是** |
| `query-order` | 订单状态/内容/配送 | |
| `order-list` | 近期到店/外送历史订单 | |
| `cancel-order` | 取消点餐订单 | **是** |
| `list-nutrition-foods` | 全表营养（约 180 项，无入参） | |
| `query-meal-assistance` / `query-promotions` | 企业团餐助餐/促销（仅 beType=6） | |

## 外送地址（3）

| Tool | 用途 | 写 |
|---|---|---|
| `delivery-query-addresses` | 我的配送地址 | |
| `delivery-create-address` | 新增配送地址 | **是** |
| `delivery-query-stores` | 按收货地址查可配送门店 | |

## 积分商城（5）

| Tool | 用途 | 写 |
|---|---|---|
| `mall-points-products` | 商城商品列表 | |
| `mall-product-detail` | 商城商品详情 | |
| `mall-create-order` | 积分兑换下单（返回券码） | **是** |
| `mall-order-list` / `mall-order-detail` | 商城订单 | |

## 积分抽奖（3）

| Tool | 用途 | 写 |
|---|---|---|
| `query-lottery-info` | 抽奖活动信息 | |
| `draw-lottery` | 执行一次积分抽奖 | **是** |
| `query-my-prizes` | 我的奖品记录 | |

## 主题活动 派对/品鉴会（6）

| Tool | 用途 | 写 |
|---|---|---|
| `query-party-city` | 可参与城市 | |
| `query-party-store` | 城市下可参与门店 | |
| `query-party-store-date` | 门店可预约日期 | |
| `query-party-store-session` | 门店+日期可预约场次 | |
| `party-order-create` | 主题活动订单创建 | **是** |

（8+10+3+5+3+5+1 计时口径说明：`query-meal-assistance` 与 `query-promotions`
为团餐场景 2 个工具，计入点餐主链路分组，合计 35。）

## 拼单典型调用顺序

```
now-time-info
  → query-nearby-stores（到店）或 delivery-query-addresses → delivery-query-stores（外送）
  → query-store-coupons（拿 couponId + 适用商品）
  → query-my-coupons（补充参考）
  → query-meals（按当前 orderType 取码）
  → [需要套餐/特调细节时] query-meal-detail
  → 本地规划（scripts/mcd.py）
  → calculate-price（每个候选一次，以返回值排序）
  → 用户确认
  → [需要时] auto-bind-coupons → create-order（外送带 remark）
```

## 坑点速查（实测结论）

| # | 坑 | 正确做法 |
|---|---|---|
| 1 | `query-my-coupons`/`available-coupons` 无 couponId | 带券算价必须 `query-store-coupons` |
| 2 | `discount` 是相对券的原价口径 | 别当「省了多少」展示 |
| 3 | 到店/外送两套编码（巨无霸 1100 / 901100） | 按 orderType 重新 `query-meals` |
| 4 | 编码用错 → `calculate-price` 返回 `price:0` 空 productList | 是编码错不是下架，重取菜单 |
| 5 | `calculate-price` 不回显特调结果 | 不断言「已生效」，只确认不报错 |
| 6 | `remark` 仅外送 orderType=2、≤50 字 | 免费配件走外送备注 |
| 7 | `withOrder` 自动带麦金卡体验卡并归零配送/打包费 | 照抄返回值，不自己拼价 |
| 8 | 无库存接口、无天气接口 | 「还有货吗/下雨吗」不通过 MCP 回答 |
| 9 | 403 + `校验鉴权authToken必填` 而非 401 | 是缺 `Bearer ` 前缀 |
| 10 | 429 | 600 次/分钟上限，串行+复用结果 |
| 11 | **`query-nearby-stores` 只传 keyword 报 600058「城市名或者关键词不能为空」** | schema 上 optional 实则隐性必填：city + keyword 同传（2026-10-24 实测） |
| 12 | **MCP text 返回是「Markdown 说明 + JSON」拼接**，`json.loads` 直接失败（说明区有 `{data[].title}` 占位符） | 先定位 `{"success"` 再截取解析（2026-10-24 实测） |
| 13 | **价格单位不一致**：`query-meals` 的 `currentPrice` 是元（字符串 "27.9"），`calculate-price` 全字段是分（2790） | 菜单价格 ×100 换算为分再进规划引擎（2026-10-24 实测） |
| 14 | `query-meals` 真实结构是 `data.categories[].meals[].code` + `data.meals.{code}` 详情映射表 | 分类只给 code，详情去映射表取（2026-10-24 实测） |

## 错误码

| code | 原因 | 处理 |
|---|---|---|
| 401 | Token 无效/过期 | 重新复制 Token |
| 403 | 缺 `Bearer ` 前缀（注意不是 401） | 值必须是 `Bearer <token>` |
| 429 | 超 600 次/分钟 | 降频 |
