"""
seed_real_kb.py — P13: 向真实 KB 预置 Skill 条目

目的
----
benchmark_suite 的 6 个 case 在真实 KB 为空时全部回落到 Layer 3。
本脚本向真实 KB 写入 6 条结构化 Skill 条目，让 Layer 1 / Layer 2
在真实持久层下也能命中，验证端到端路径完整性。

写入策略
--------
- Layer 1 case：写入与 problem 高度重叠的 Skill（title/tags 完全匹配关键词）
- Layer 2/3 case：写入辅助知识条目，让 Layer 2 组合器能搜到上下文
"""

from __future__ import annotations

import json
import sys
import logging
from pathlib import Path
from typing import Dict, Any

# ── 路径初始化 ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent           # adaptive-skill-system/
sys.path.insert(0, str(ROOT))

MEMORY_BANK = Path(
    r"C:/Users/sdenilson/WorkBuddy/Claw/output/ai-memory-system/engine/memory-bank"
)

# ── 日志 ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

# ── 客户端初始化 ────────────────────────────────────────────────────────────
from adaptive_skill.memory_system_client import MemorySystemClient

client = MemorySystemClient(memory_dir=MEMORY_BANK)
if not client.is_available or client.kb is None:
    print("[FAIL] MemorySystemClient 初始化失败，退出")
    sys.exit(1)

print(f"[OK] 持久层就绪: {MEMORY_BANK}")
kb = client.kb._kb          # 直接访问原始 KBManager，用其 add() 方法写入


# ── Skill 条目定义 ──────────────────────────────────────────────────────────

SKILL_ENTRIES = [
    # ----------------------------------------------------------------
    # Layer 1 case: bench-layer1-kb-hit-v1
    # problem: "请用运营策略 分解法 给我一个三步方案，包含目标定义、渠道选择、执行计划。"
    # ----------------------------------------------------------------
    {
        "title": "运营策略分解法 — 三步方案框架（目标定义/渠道选择/执行计划）",
        "content": (
            "这是一个可直接调用的运营策略 Skill，基于分解法生成三步方案。\n"
            "\n"
            "## 技能描述\n"
            "适用于任何运营场景的三步方案设计：目标定义 → 渠道选择 → 执行计划。\n"
            "\n"
            "## 执行步骤\n"
            "1. **目标定义**：明确核心 KPI（用户数/GMV/留存率）、时间周期、成功标准\n"
            "2. **渠道选择**：评估目标用户触达渠道（社媒/内容/付费/私域），按 ROI 排序\n"
            "3. **执行计划**：拆解里程碑、分配资源、设定 OKR 和复盘节点\n"
            "\n"
            "## 示例输出\n"
            "目标：DAU 提升 30%\n"
            "渠道：小红书+抖音（ROI 最高）\n"
            "计划：Week1 内容矩阵搭建 → Week2-4 投放放量 → Week5 数据复盘\n"
        ),
        "category": "technical",
        "tags": ["skill", "运营策略", "分解法", "三步方案", "目标定义", "渠道选择", "执行计划"],
        "source": "seeded",
        "confidence": "high",
    },
    # ----------------------------------------------------------------
    # Layer 2 case: bench-layer2-compose-v1
    # problem: "请基于 Z世代 心理学 数据分析 健身App 留存，给我一个提升方案。"
    # ----------------------------------------------------------------
    {
        "title": "Z世代用户心理学模型 — 动机与留存行为分析",
        "content": (
            "Z世代（1995-2010年出生）的核心心理特征与留存驱动因素。\n"
            "\n"
            "关键心理维度：\n"
            "- 即时反馈依赖：需要每次行动后的即时正向激励\n"
            "- 社交认同感：排行榜/好友分享比纯功能更重要\n"
            "- 个性化期望：不接受千人一面的推送\n"
            "- 短注意力周期：30天打卡比180天计划更易坚持\n"
            "\n"
            "健身App 留存关键指标：\n"
            "- D1/D7/D30 留存率\n"
            "- 每周活跃频次\n"
            "- 完成率（计划vs实际）\n"
        ),
        "category": "domain",
        "tags": ["Z世代", "心理学", "用户留存", "健身App", "数据分析", "行为分析"],
        "source": "seeded",
        "confidence": "high",
    },
    {
        "title": "健身App 数据分析 — 留存提升实战方案",
        "content": (
            "基于数据分析的健身App用户留存提升框架。\n"
            "\n"
            "分析维度：\n"
            "1. 漏斗分析：注册→首次运动→7天复访→30天留存的转化率\n"
            "2. 流失预警：连续3天不活跃 = 高流失风险信号\n"
            "3. 特征工程：留存用户 vs 流失用户的行为差异（频次/时长/社交）\n"
            "\n"
            "提升策略：\n"
            "- 激活期（D1-7）：每日打卡+即时成就徽章\n"
            "- 习惯期（D8-30）：周报+好友排行+个性化课程推荐\n"
            "- 长期期（D30+）：里程碑奖励+社群归属感\n"
        ),
        "category": "technical",
        "tags": ["健身App", "留存", "数据分析", "用户增长", "Z世代"],
        "source": "seeded",
        "confidence": "high",
    },
    # ----------------------------------------------------------------
    # Layer 2 case: bench-layer2-mixed-support-v1
    # problem: "请基于 志愿者招募 培训复盘 社群激励 设计一个青年活动运营方案。"
    # ----------------------------------------------------------------
    {
        "title": "志愿者招募与社群激励 — 青年活动运营框架",
        "content": (
            "针对青年群体的志愿者招募、培训复盘与社群激励设计框架。\n"
            "\n"
            "核心模块：\n"
            "1. 招募策略：校园/社媒双渠道，突出成长价值（技能+人脉+证书）\n"
            "2. 培训复盘：活动前3天培训 → 活动后48h复盘会（STAR法则）\n"
            "3. 社群激励：成就体系（铜/银/金志愿者级别）+ 积分兑换 + 年度表彰\n"
            "\n"
            "关键成功因素：\n"
            "- 让志愿者感受到「被需要」而非「被使用」\n"
            "- 复盘的核心是学习而非追责\n"
            "- 社群的黏性来自横向连接（同伴），而非纵向管控\n"
        ),
        "category": "domain",
        "tags": ["志愿者招募", "培训复盘", "社群激励", "青年活动", "运营方案"],
        "source": "seeded",
        "confidence": "high",
    },
    # ----------------------------------------------------------------
    # Layer 3 cases — 写入稀疏知识条目，供 Layer 2 fallback 或 Layer 3 参考
    # ----------------------------------------------------------------
    {
        "title": "超马赛季训练 — 周期化计划设计原则",
        "content": (
            "超级马拉松（Ultra Marathon）赛季周期化训练计划设计原则。\n"
            "\n"
            "四阶段模型：\n"
            "1. 基础期（8-12周）：有氧基础，低强度高量，心率Z2为主\n"
            "2. 专项期（6-8周）：爬升训练/越野技术/长距离back-to-back\n"
            "3. 比赛期（2-4周）：减量，保状态，模拟比赛场景\n"
            "4. 恢复期（2-4周）：积极恢复，评估，下赛季规划\n"
            "\n"
            "关键指标：周里程、爬升量、长跑距离、恢复心率\n"
        ),
        "category": "domain",
        "tags": ["超马", "赛季训练", "周期化", "训练计划", "跑步", "运动员"],
        "source": "seeded",
        "confidence": "medium",
    },
    {
        "title": "校园读书会 — 长期陪伴与打卡反馈机制设计",
        "content": (
            "校园读书会长期运营中的陪伴机制与打卡反馈体系设计方案。\n"
            "\n"
            "陪伴机制：\n"
            "- 配对制：每本书匹配一位「领读人」（高年级/已读者）\n"
            "- 进度同步：每周一次15分钟 check-in（非讲解，是共同感受）\n"
            "\n"
            "打卡反馈机制：\n"
            "- 轻量打卡：每天一句话记录，不要求篇幅\n"
            "- 及时反馈：领读人24h内回应，哪怕只是一个emoji\n"
            "- 里程碑激励：完成50/100/200天打卡解锁「书友徽章」\n"
        ),
        "category": "domain",
        "tags": ["校园读书会", "打卡反馈", "长期陪伴", "社群运营", "学习机制"],
        "source": "seeded",
        "confidence": "medium",
    },
]


# ── 写入 KB ─────────────────────────────────────────────────────────────────

def seed_kb():
    results = []
    print(f"\n[P13] 开始向真实 KB 预置 {len(SKILL_ENTRIES)} 条 Skill 条目...\n")

    for i, entry in enumerate(SKILL_ENTRIES, 1):
        title = entry["title"]
        try:
            saved = kb.add(
                title=entry["title"],
                content=entry["content"],
                category=entry.get("category", "technical"),
                tags=entry.get("tags", []),
                source=entry.get("source", "seeded"),
                confidence=entry.get("confidence", "high"),
            )
            eid = getattr(saved, "id", None) or (saved.get("id") if isinstance(saved, dict) else "?")
            print(f"  [{i}] OK  id={eid[:8]}...  {title[:50]}")
            results.append({"status": "ok", "id": eid, "title": title})
        except Exception as exc:
            print(f"  [{i}] ERR {exc}  {title[:50]}")
            results.append({"status": "error", "error": str(exc), "title": title})

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\n写入完成: {ok}/{len(SKILL_ENTRIES)} 成功")
    return results


def verify_layer1_recall():
    """写入后立即验证 Layer 1 的 query 能否命中。"""
    print("\n[P13] 验证 Layer 1 query 命中...")
    from adaptive_skill.memory_system_client import KBClientAdapter
    kb_adapter = client.kb

    layer1_query = "请用运营策略 分解法 给我一个三步方案，包含目标定义、渠道选择、执行计划。"
    hits = kb_adapter.search(layer1_query, top_k=5)
    print(f"  Layer 1 query -> {len(hits)} hits")
    for h in hits:
        print(f"    [{h.get('id','?')[:8]}] {h.get('title','')[:60]}")

    return len(hits) > 0


if __name__ == "__main__":
    seed_results = seed_kb()
    hit = verify_layer1_recall()

    # dump summary
    summary = {
        "seed_results": seed_results,
        "layer1_hit_after_seed": hit,
    }
    out_path = Path(__file__).parent / "seed_kb_result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\nSummary written to {out_path}")
    print("\n[P13] DONE")
