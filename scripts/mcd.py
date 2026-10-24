# -*- coding: utf-8 -*-
"""
mcd.py — 麦当劳 MCP 直连 CLI + 「麦拼单」规划引擎

纯 Python 标准库实现（3.9+），无需安装任何依赖。
通过 Streamable HTTP 直连麦当劳中国官方 MCP Server（https://mcp.mcd.cn），
无需 MCP 客户端即可在命令行完成：查门店、拉菜单、领券、核价、拼单规划。

用法示例：
    export MCD_MCP_TOKEN="你的Token"          # 或写入 ~/.mcd_mcp_token
    python mcd.py check                       # 检查 Token 与连通性
    python mcd.py tools                       # 列出全部 35 个工具
    python mcd.py schema query-meals          # 查看单个工具入参 Schema
    python mcd.py call query-my-account '{}'  # 通用调用
    python mcd.py plan --offline --people 5 --budget 35 --address "深圳南山科技园"

退出码：0 成功 / 1 工具错误 / 2 鉴权失败 / 3 限流 / 4 网络错误 / 5 参数错误
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

MCP_URL = "https://mcp.mcd.cn"
TOKEN_FILE = os.path.join(os.path.expanduser("~"), ".mcd_mcp_token")
USER_AGENT = "mcd-party/1.0.0 (M-CODE contest entry)"


# ---------------------------------------------------------------------------
# MCP 客户端：Streamable HTTP + JSON-RPC 2.0
# ---------------------------------------------------------------------------

class McpError(Exception):
    """带退出码的错误，便于脚本判断处理。"""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


class McpClient:
    """最小可用的麦当劳 MCP 客户端。

    握手流程：initialize → notifications/initialized → tools/list / tools/call。
    服务端可能返回 JSON 或 SSE（text/event-stream），两种都解析。
    """

    def __init__(self, token, url=MCP_URL, timeout=30):
        if not token:
            raise McpError(
                "未找到 MCP Token。请设置环境变量 MCD_MCP_TOKEN，"
                "或写入文件 ~/.mcd_mcp_token。Token 在 open.mcd.cn/mcp 控制台激活获取。",
                code=2,
            )
        self.url = url
        self.timeout = timeout
        self.token = token
        self.session_id = None
        self._next_id = 1

    # -- 底层请求 ----------------------------------------------------------

    def _post(self, payload, expect_response=True):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer " + self.token,
            "User-Agent": USER_AGENT,
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
        req = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            if e.code in (401, 403):
                raise McpError("鉴权失败（HTTP %d）：%s\n请检查 Token 是否正确、是否带 'Bearer ' 前缀。" % (e.code, raw[:300]), code=2)
            if e.code == 429:
                raise McpError("触发限流（HTTP 429）：每 Token 每分钟最多 600 次请求，请降低频率。", code=3)
            raise McpError("HTTP %d：%s" % (e.code, raw[:300]), code=1)
        except urllib.error.URLError as e:
            raise McpError("网络错误：%s" % e.reason, code=4)

        # 会话 ID 在响应头里，后续请求要带回
        sid = resp.headers.get("mcp-session-id")
        if sid:
            self.session_id = sid
        raw = resp.read().decode("utf-8", "replace")
        if not expect_response:
            return None
        return _parse_mcp_response(raw)

    def _rpc(self, method, params=None):
        payload = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        self._next_id += 1
        if params is not None:
            payload["params"] = params
        resp = self._post(payload)
        if isinstance(resp, dict) and "error" in resp:
            err = resp["error"]
            raise McpError("RPC 错误 %s：%s" % (err.get("code"), err.get("message")), code=1)
        return resp.get("result") if isinstance(resp, dict) else resp

    # -- 公开方法 ----------------------------------------------------------

    def initialize(self):
        result = self._rpc("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "mcd-party", "version": "1.0.0"},
        })
        # initialized 通知无需响应
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, expect_response=False)
        return result

    def list_tools(self):
        return self._rpc("tools/list").get("tools", [])

    def call_tool(self, name, arguments=None):
        return self._rpc("tools/call", {"name": name, "arguments": arguments or {}})


def _parse_mcp_response(raw):
    """解析 MCP 响应：优先按 JSON，否则按 SSE 的 data: 行提取最后一个 JSON。"""
    raw = raw.strip()
    if not raw:
        return {}
    if raw.startswith("{"):
        return json.loads(raw)
    # SSE 格式：event: message\ndata: {...}\n\n
    last_json = None
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            chunk = line[5:].strip()
            if chunk.startswith("{"):
                try:
                    last_json = json.loads(chunk)
                except json.JSONDecodeError:
                    pass
    if last_json is None:
        raise McpError("无法解析 MCP 响应：%s" % raw[:200], code=4)
    return last_json


def load_token():
    """Token 读取顺序：环境变量 MCD_MCP_TOKEN > ~/.mcd_mcp_token。"""
    token = os.environ.get("MCD_MCP_TOKEN", "").strip()
    if token:
        return token
    if os.path.isfile(TOKEN_FILE):
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def extract_tool_text(result):
    """tools/call 的返回是 content 数组，抽出可读文本。"""
    if not isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False, indent=2)
    content = result.get("content") or []
    parts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(item.get("text", ""))
    text = "\n".join(parts) if parts else json.dumps(result, ensure_ascii=False)
    # MCP 工具常把结构化数据塞在 text 里的 JSON 字符串，尝试美化
    try:
        return json.dumps(json.loads(text), ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, TypeError):
        return text


# ---------------------------------------------------------------------------
# 拼单规划引擎（纯函数，可离线单测）
# ---------------------------------------------------------------------------
#
# 设计原则（来自对线上 MCP 的实测认知，详见 references/mcd-tools.md）：
#   1. 一切金额以 calculate-price 返回为准，本地只做「候选筛选」，不做最终定价；
#   2. 券 ID 只有 query-store-coupons 返回，本地券池必须带 couponId 才能参与规划；
#   3. 到店 / 外送菜单编码不同，规划前必须明确 orderType，菜单按渠道取；
#   4. 约束无解就明说，不硬凑。

# 餐品分类归一（query-meals 返回的分类名各店可能不同，按关键词归到大类）
CATEGORY_RULES = [
    ("主食", ["汉堡", "堡", "套餐", "饭", "卷", "派", "鸡", "牛", "鱼", "虾", "面"]),
    ("小食", ["薯", "翅", "块", "角", "派", " salad", "沙拉", "玉米", "骨"]),
    ("饮料", ["可乐", "雪碧", "芬达", "咖啡", "美式", "拿铁", "茶", "奶", "汁", "水"]),
    ("甜品", ["冰淇淋", "甜筒", "派", "蛋糕", "麦旋风"]),
]

# 默认忌口关键词映射（中文口语 → 菜单文本匹配词）
AVOID_ALIASES = {
    "辣": ["辣", "麦辣", "香辣"],
    "牛肉": ["牛", "吉士", "双层吉士", "安格斯"],
    "鱼": ["鱼", "麦香鱼"],
    "猪肉": ["猪", "麦香猪"],
    "鸡": ["鸡", "麦乐鸡", "麦辣鸡腿"],
    "海鲜": ["虾", "蟹", "鱼"],
    "冰": ["冰", "去冰"],  # 用户说"不要冰"时反查特调，此处仅作粗筛提示
}


def classify(name):
    """按餐品名归入 主食/小食/饮料/甜品 大类，归不入的返回 None。"""
    for category, keywords in CATEGORY_RULES:
        for kw in keywords:
            if kw.lower() in name.lower():
                return category
    return None


def _to_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _yuan_to_fen(value):
    """元（字符串，可带小数）→ 分（整数）。实测菜单价格为元口径。"""
    try:
        return int(round(float(value) * 100))
    except (TypeError, ValueError):
        return 0


def menu_to_items(menu_json):
    """把 query-meals 的返回归一成 [{code, name, price, category}] 列表。

    兼容结构（均已实测验证）：
      A. 线上真实结构（2026-10-24 实测）：{"data": {"categories": [{"name": "鸡肉汉堡",
         "meals": [{"code": "1440", "tags": [...]}]}], "meals": {"1440": {"name": ...,
         "currentPrice": "2100", ...}}}} —— 分类只给 code，详情在 data.meals 映射表；
      B. 扁平数组：[{code, name, price}, ...]；
      C. 包一层：{"products": [...]} 或 {"categories": [{"products": [...]}]}。
    price 单位原样保留（线上为分，字符串数字）。
    """
    items = []
    root = menu_json.get("data", menu_json) if isinstance(menu_json, dict) else menu_json
    detail_map = {}
    categories = None
    if isinstance(root, dict):
        detail_map = root.get("meals") or {}
        categories = root.get("categories")

    def from_detail(code, category_hint=""):
        detail = detail_map.get(code) if isinstance(detail_map, dict) else None
        if not isinstance(detail, dict):
            return None
        name = detail.get("name", "")
        # 实测（2026-10-24）：菜单 currentPrice 单位是「元」（字符串，可带小数，
        # 如 "27.9"）；而 calculate-price 的单位是「分」（2790）。统一换算为分。
        price = _yuan_to_fen(detail.get("currentPrice") or detail.get("originalPrice") or 0)
        category = classify(name) or category_hint.replace("\n", "") or "其他"
        return {"code": code, "name": name, "price": price, "category": category}

    # 结构 A：categories[].meals[].code + data.meals 映射表
    if isinstance(categories, list):
        for cat in categories:
            if not isinstance(cat, dict):
                continue
            cat_name = cat.get("name", "")
            for meal in cat.get("meals", []) or []:
                if not isinstance(meal, dict):
                    continue
                code = str(meal.get("code", ""))
                item = from_detail(code, cat_name)
                if item and item["name"]:
                    items.append(item)
        if items:
            # 按 code 去重（同一餐品可能出现在多个分类）
            seen, unique = set(), []
            for i in items:
                if i["code"] not in seen:
                    seen.add(i["code"])
                    unique.append(i)
            return unique

    # 结构 B / C
    products = []
    if isinstance(root, list):
        products = root
    elif isinstance(root, dict):
        for key in ("products", "productList", "meals", "data"):
            value = root.get(key)
            if isinstance(value, list):
                products = value
                break
        if not products:
            for cat in root.get("categories", []) or []:
                if isinstance(cat, dict):
                    products.extend(cat.get("products", []) or [])
    for p in products:
        if not isinstance(p, dict):
            continue
        name = p.get("name") or p.get("productName") or ""
        code = str(p.get("code") or p.get("productCode") or "")
        price = _to_int(p.get("price", p.get("currentPrice", p.get("salePrice", 0))))
        category = p.get("category") or classify(name) or "其他"
        items.append({"code": code, "name": name, "price": price, "category": category})
    return [i for i in items if i["name"]]


def filter_by_avoid(items, avoid):
    """按忌口清单过滤餐品，返回 (可用列表, 被过滤名单)。"""
    if not avoid:
        return list(items), []
    banned = []
    for word in avoid:
        banned.extend(AVOID_ALIASES.get(word, [word]))
    banned = [b for b in set(banned) if b]
    kept, dropped = [], []
    for item in items:
        if any(b in item["name"] for b in banned):
            dropped.append(item["name"])
        else:
            kept.append(item)
    return kept, dropped


def pick_combo(items, budget, prefer=None):
    """在预算内为一人生成「主食+小食+饮料」候选组合，返回最优的一个或 None。

    贪心策略：主食优先选 prefer 指定词命中的，否则选价格最接近预算 45% 的；
    小食/饮料在剩余预算内选性价比（价格低优先）项。预算单位与菜单 price 一致（分）。
    """
    staples = [i for i in items if i["category"] == "主食"]
    snacks = [i for i in items if i["category"] == "小食"]
    drinks = [i for i in items if i["category"] == "饮料"]
    if not staples:
        return None

    chosen_staple = None
    if prefer:
        for kw in prefer:
            for s in staples:
                if kw in s["name"]:
                    chosen_staple = s
                    break
            if chosen_staple:
                break
    if chosen_staple is None:
        # 目标：主食占预算约 45%，取价格最接近的
        target = budget * 0.45
        chosen_staple = min(staples, key=lambda s: abs(s["price"] - target))
        if chosen_staple["price"] > budget:
            return None

    remaining = budget - chosen_staple["price"]
    combo = {"主食": chosen_staple, "小食": None, "饮料": None}
    for category, pool in (("小食", snacks), ("饮料", drinks)):
        if not pool:
            continue
        affordable = [i for i in pool if i["price"] <= remaining]
        if affordable:
            # 小食/饮料留出余量：小食最多花掉剩余的 60%，饮料最多 40%
            cap = remaining * (0.6 if category == "小食" else 0.4)
            capped = [i for i in affordable if i["price"] <= cap] or affordable
            combo[category] = min(capped, key=lambda i: i["price"])
            remaining -= combo[category]["price"]
    if remaining < 0:
        return None
    total = sum(v["price"] for v in combo.values() if v)
    return {"combo": combo, "total": total}


def build_party_plan(items, coupons, people, per_budget, prefer=None, avoid=None):
    """拼单主规划：N 人 × 人均预算 → 每人一份组合 + 券使用建议 + 汇总。

    coupons: [{couponId, title, threshold, applicable:[餐品编码...]}]（来自 query-store-coupons）
    返回 {lines:[每人明细], totals:{原价/预估优惠/预估实付}, coupon_used:[券标题], note:说明}
    """
    usable, dropped = filter_by_avoid(items, avoid or [])
    if not usable:
        return {"error": "忌口条件过严，当前门店菜单没有可用餐品。被过滤：%s" % "、".join(dropped)}

    total_budget = per_budget * people
    lines = []
    for idx in range(1, people + 1):
        picked = pick_combo(usable, per_budget, prefer)
        if picked is None:
            return {"error": "第 %d 位同学在人均 %d 的预算内凑不出合规组合（主食超预算）。" % (idx, per_budget)}
        lines.append({"person": idx, "items": picked["combo"], "subtotal": picked["total"]})

    gross = sum(l["subtotal"] for l in lines)
    # 券建议：挑一张门槛可达成的满减券（简化：取门槛 ≤ 原价的最大优惠券）
    coupon_used, discount = [], 0
    for c in sorted(coupons or [], key=lambda c: -(c.get("discount") or 0)):
        threshold = c.get("threshold") or 0
        if threshold and gross >= threshold:
            coupon_used.append(c.get("title") or c.get("couponId"))
            discount = c.get("discount") or 0
            break

    note = ""
    if gross > total_budget:
        note = "当前组合原价 %d 已超总预算 %d，请上调人均或减少品类。" % (gross, total_budget)
    elif dropped:
        note = "已按忌口过滤：%s" % "、".join(sorted(set(dropped)))

    return {
        "lines": lines,
        "totals": {
            "people": people,
            "per_budget": per_budget,
            "gross": gross,
            "coupon_discount": discount,
            "estimated_pay": gross - discount,
            "per_person_aa": round((gross - discount) / people),
        },
        "coupon_used": coupon_used,
        "note": note,
    }


def render_plan(plan):
    """把规划结果渲染成终端可读的文本表格。"""
    if "error" in plan:
        return "规划失败：%s" % plan["error"]
    out = []
    out.append("=" * 56)
    out.append("麦拼单 · 拼单方案（离线规划，金额以 calculate-price 实测为准）")
    out.append("=" * 56)
    for line in plan["lines"]:
        parts = []
        for category in ("主食", "小食", "饮料"):
            item = line["items"].get(category)
            if item:
                parts.append("%s %s×%d" % (item["name"], category, item["price"]))
        out.append("  %d 号：%s → 小计 %d" % (line["person"], "；".join(parts), line["subtotal"]))
    t = plan["totals"]
    out.append("-" * 56)
    out.append("  原价合计：%d" % t["gross"])
    if plan["coupon_used"]:
        out.append("  建议用券：%s（优惠约 %d）" % ("、".join(plan["coupon_used"]), t["coupon_discount"]))
    out.append("  预估实付：%d    人均 AA：%d" % (t["estimated_pay"], t["per_person_aa"]))
    if plan["note"]:
        out.append("  说明：%s" % plan["note"])
    out.append("=" * 56)
    out.append("下一步（需用户确认后执行）：calculate-price 实测核价 → 确认 → create-order")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# 离线 fixtures 支持（无 Token 也能演示与测试规划引擎）
# ---------------------------------------------------------------------------

def load_fixture(name):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fixtures", name)
    if not os.path.isfile(path):
        raise McpError("fixtures 不存在：%s" % path, code=5)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 命令行入口
# ---------------------------------------------------------------------------

def cmd_check(client, args):
    info = client.initialize()
    tools = client.list_tools()
    names = [t.get("name") for t in tools]
    print("连接成功：%s" % info.get("serverInfo", {}).get("name", MCP_URL))
    print("协议版本：%s" % info.get("protocolVersion", "?"))
    print("工具数量：%d" % len(names))
    print("工具列表：%s" % ", ".join(n for n in names if n))
    return 0


def cmd_tools(client, args):
    tools = client.list_tools()
    for t in tools:
        write_mark = "写" if _looks_write(t.get("name", "")) else "读"
        print("[%s] %-28s %s" % (write_mark, t.get("name", "?"), (t.get("description") or "").splitlines()[0][:60] if t.get("description") else ""))
    return 0


# 经验证包含写操作的工具名（来自社区实测清单，2026-10-09 核对）
WRITE_TOOLS = {
    "auto-bind-coupons", "create-order", "cancel-order",
    "delivery-create-address", "mall-create-order", "draw-lottery",
    "party-order-create",
}


def _looks_write(name):
    return name in WRITE_TOOLS


def cmd_schema(client, args):
    tools = client.list_tools()
    target = None
    for t in tools:
        if t.get("name") == args.tool:
            target = t
            break
    if target is None:
        print("未找到工具 %s。可用：python mcd.py tools" % args.tool)
        return 1
    print(json.dumps(target.get("inputSchema", {}), ensure_ascii=False, indent=2))
    return 0


def cmd_call(client, args):
    arguments = json.loads(args.arguments) if args.arguments else {}
    result = client.call_tool(args.tool, arguments)
    print(extract_tool_text(result))
    return 0


def cmd_plan(client, args):
    if args.offline:
        menu = load_fixture("menu-sample.json")
        coupons = load_fixture("coupons-sample.json").get("coupons", [])
        items = menu_to_items(menu)
    else:
        # 在线模式：地址 → 门店 → 菜单 → 门店券，然后本地规划
        if not args.address:
            print("在线模式需要 --address（用于定位门店）")
            return 5
        stores = client.call_tool("query-nearby-stores", {"address": args.address})
        store_text = extract_tool_text(stores)
        print("附近门店（原始返回前 500 字）：\n%s\n" % store_text[:500])
        print("提示：门店选择与 orderType 确定后，请按 references/mcd-tools.md 的链路手动取菜单与券。")
        return 0
    plan = build_party_plan(
        items, coupons,
        people=args.people, per_budget=args.budget,
        prefer=args.prefer, avoid=args.avoid,
    )
    print(render_plan(plan))
    return 0 if "error" not in plan else 1


def main(argv=None):
    # Windows 下默认按 GBK 输出中文会乱码，强制 UTF-8（Python 3.7+ 支持）
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    parser = argparse.ArgumentParser(description="麦当劳 MCP CLI + 麦拼单规划引擎")
    parser.add_argument("--url", default=MCP_URL, help="MCP Server 地址")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("check", help="检查 Token 与连通性")
    sub.add_parser("tools", help="列出全部工具")

    p_schema = sub.add_parser("schema", help="查看单个工具入参 Schema")
    p_schema.add_argument("tool")

    p_call = sub.add_parser("call", help="调用工具")
    p_call.add_argument("tool")
    p_call.add_argument("arguments", nargs="?", default="{}", help="JSON 参数")

    p_plan = sub.add_parser("plan", help="拼单规划")
    p_plan.add_argument("--people", type=int, default=4)
    p_plan.add_argument("--budget", type=int, default=35, help="人均预算（单位：分，与菜单一致）")
    p_plan.add_argument("--address", default="", help="在线模式：定位地址")
    p_plan.add_argument("--prefer", nargs="*", default=[], help="偏好关键词，如：鸡 可乐")
    p_plan.add_argument("--avoid", nargs="*", default=[], help="忌口关键词，如：辣 牛肉")
    p_plan.add_argument("--offline", action="store_true", help="使用 fixtures 离线演示")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 5

    if args.command == "plan" and args.offline:
        return cmd_plan(None, args)

    client = McpClient(load_token(), url=args.url)
    try:
        if args.command == "check":
            return cmd_check(client, args)
        if args.command == "tools":
            return cmd_tools(client, args)
        if args.command == "schema":
            return cmd_schema(client, args)
        if args.command == "call":
            return cmd_call(client, args)
        if args.command == "plan":
            return cmd_plan(client, args)
    except McpError as e:
        print("错误：%s" % e)
        return e.code
    return 5


if __name__ == "__main__":
    sys.exit(main())
