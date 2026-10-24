# -*- coding: utf-8 -*-
"""
test_plan.py — 麦拼单规划引擎离线单测（用 fixtures 跑，无需 MCP Token）

运行：python tests/test_plan.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import mcd  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fixtures")


def load(name):
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as f:
        return json.load(f)


def test_menu_to_items_categories_structure():
    """categories 嵌套结构能正确归一。"""
    items = mcd.menu_to_items(load("menu-sample.json"))
    assert len(items) == 12, "应有 12 个餐品（5 主食+3 小食+3 饮料+1 甜品），实际 %d" % len(items)
    big_mac = [i for i in items if i["name"] == "巨无霸"][0]
    assert big_mac["code"] == "1100"
    assert big_mac["price"] == 2050
    assert big_mac["category"] == "主食"


def test_menu_to_items_flat_array():
    """扁平数组结构也能归一。"""
    items = mcd.menu_to_items([
        {"code": "1", "name": "麦辣鸡腿汉堡", "price": 2100},
        {"code": "2", "name": "中杯可口可乐", "price": 900},
    ])
    assert len(items) == 2
    assert items[0]["category"] == "主食"
    assert items[1]["category"] == "饮料"


def test_filter_by_avoid():
    """忌口过滤：辣 / 牛肉 / 鱼。"""
    items = mcd.menu_to_items(load("menu-sample.json"))
    kept, dropped = mcd.filter_by_avoid(items, ["辣", "鱼"])
    names = [i["name"] for i in kept]
    assert not any("麦辣" in n for n in names), "麦辣系应被过滤"
    assert not any("麦香鱼" in n for n in names), "麦香鱼应被过滤"
    assert any("巨无霸" in n for n in names), "牛肉不在忌口清单时应保留"
    assert dropped, "应有被过滤名单"


def test_pick_combo_within_budget():
    """人均预算内能凑出 主食+小食+饮料。"""
    items = mcd.menu_to_items(load("menu-sample.json"))
    picked = mcd.pick_combo(items, budget=3500)
    assert picked is not None, "3500 分预算应能凑出组合"
    combo = picked["combo"]
    assert combo["主食"] is not None
    assert picked["total"] <= 3500, "组合总价不应超预算"


def test_pick_combo_impossible_budget():
    """预算低于最便宜主食时返回 None（不硬凑）。"""
    items = mcd.menu_to_items(load("menu-sample.json"))
    assert mcd.pick_combo(items, budget=1000) is None


def test_build_party_plan_basic():
    """5 人 × 3500 人均的完整拼单规划。"""
    items = mcd.menu_to_items(load("menu-sample.json"))
    coupons = load("coupons-sample.json")["coupons"]
    plan = mcd.build_party_plan(items, coupons, people=5, per_budget=3500)
    assert "error" not in plan, "5 人 35 元应可规划：%s" % plan.get("error")
    assert len(plan["lines"]) == 5
    totals = plan["totals"]
    assert totals["people"] == 5
    assert totals["gross"] > 0
    assert totals["estimated_pay"] == totals["gross"] - totals["coupon_discount"]
    assert totals["per_person_aa"] > 0


def test_build_party_plan_avoid_spicy():
    """全员忌辣时方案不含麦辣系。"""
    items = mcd.menu_to_items(load("menu-sample.json"))
    coupons = load("coupons-sample.json")["coupons"]
    plan = mcd.build_party_plan(items, coupons, people=3, per_budget=3500, avoid=["辣"])
    assert "error" not in plan
    for line in plan["lines"]:
        for item in line["items"].values():
            if item:
                assert "麦辣" not in item["name"]


def test_build_party_plan_coupon_selection():
    """总价过门槛时应建议满减券。"""
    items = mcd.menu_to_items(load("menu-sample.json"))
    coupons = load("coupons-sample.json")["coupons"]
    plan = mcd.build_party_plan(items, coupons, people=5, per_budget=4000)
    assert "error" not in plan
    if plan["totals"]["gross"] >= 6000:
        assert plan["totals"]["coupon_discount"] > 0, "过门槛应有券优惠"
        assert plan["coupon_used"], "应记录建议用券"


def test_build_party_plan_no_solution():
    """预算过低时明说无解，不硬凑。"""
    items = mcd.menu_to_items(load("menu-sample.json"))
    plan = mcd.build_party_plan(items, [], people=2, per_budget=1500)
    assert "error" in plan


def test_render_plan():
    """渲染函数对成功/失败两种结果都不抛异常。"""
    items = mcd.menu_to_items(load("menu-sample.json"))
    plan = mcd.build_party_plan(items, [], people=3, per_budget=3500)
    text = mcd.render_plan(plan)
    assert "人均 AA" in text
    fail_text = mcd.render_plan({"error": "测试失败路径"})
    assert "规划失败" in fail_text


def test_load_token_missing(monkeypatch=None):
    """无 Token 时 load_token 返回空串（由 McpClient 报友好错误）。"""
    old = os.environ.pop("MCD_MCP_TOKEN", None)
    try:
        if os.path.isfile(mcd.TOKEN_FILE):
            print("（跳过：本机存在 %s）" % mcd.TOKEN_FILE)
            return
        assert mcd.load_token() == ""
    finally:
        if old is not None:
            os.environ["MCD_MCP_TOKEN"] = old


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS  %s" % t.__name__)
        except AssertionError as e:
            failed += 1
            print("FAIL  %s：%s" % (t.__name__, e))
        except Exception as e:  # noqa: BLE001
            failed += 1
            print("ERROR %s：%r" % (t.__name__, e))
    print("-" * 40)
    print("%d 个用例，%d 个失败" % (len(tests), failed))
    sys.exit(1 if failed else 0)
