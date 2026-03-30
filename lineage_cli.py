"""
lineage_cli.py — Skill 谱系库命令行工具
=========================================
快速查询 SQLite 谱系库，不需要 Python 环境里安装任何包。

使用方式：
    python lineage_cli.py stats
    python lineage_cli.py roots
    python lineage_cli.py tree   <skill_id>
    python lineage_cli.py anc    <skill_id>      # 查祖先链
    python lineage_cli.py desc   <skill_id>      # 查后代
    python lineage_cli.py search <关键词>
    python lineage_cli.py show   <skill_id>      # 查单条详情
    python lineage_cli.py recent [N]             # 最近 N 条（默认10）
"""

import sys
import importlib.util
from pathlib import Path

# 直接从文件路径加载 SkillLineage（绕过 __init__.py 版本问题）
_here = Path(__file__).parent
_lineage_file = _here / "adaptive_skill" / "skill_lineage.py"
_spec = importlib.util.spec_from_file_location("skill_lineage", _lineage_file)
_mod  = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
SkillLineage = _mod.SkillLineage

DB_PATH = (
    "C:/Users/sdenilson/WorkBuddy/Claw/output/ai-memory-system"
    "/engine/memory-bank/skill_lineage.db"
)

OUT_FILE = Path("C:/Users/sdenilson/WorkBuddy/Claw/output/lineage_cli_out.txt")

def _fmt(d: dict, detail: bool = False) -> str:
    eid   = d.get("id", "?")[:12]
    etype = d.get("evolution_type", "?")
    ver   = d.get("version", "?")
    name  = d.get("name", "?")[:55]
    depth = d.get("depth", 0)
    score = d.get("quality_score")
    score_str = f"  Q={score:.2f}" if score else ""
    parent = d.get("parent_id", "")
    parent_str = f"  <- {str(parent)[:8]}" if parent else ""
    line = f"  [{etype:<14}] v{ver:<5}  d={depth}  {eid}...  {name}{score_str}{parent_str}"
    if detail:
        desc = (d.get("description") or "")[:120]
        line += f"\n      {desc}"
    return line


def cmd_stats(db):
    s = db.stats()
    lines = [
        "=== Skill 谱系库统计 ===",
        f"  总技能数      : {s['total_skills']}",
        f"  按进化类型    : {s['by_evolution_type']}",
        f"  按状态        : {s['by_status']}",
        f"  最大谱系深度  : {s['max_lineage_depth']}",
        f"  平均质量分    : {s['avg_quality_score']}",
        f"  DB 路径       : {s['db_path']}",
    ]
    return lines


def cmd_roots(db):
    roots = db.list_roots()
    lines = [f"=== 根 Skill（共 {len(roots)} 个）==="]
    for r in roots:
        lines.append(_fmt(r))
    return lines


def cmd_tree(db, skill_id):
    node = db.get(skill_id)
    if not node:
        return [f"[NOT FOUND] {skill_id}"]
    
    lines = [f"=== 谱系树 — {skill_id} ==="]
    
    def _render(sid, indent=0):
        n = db.get(sid)
        if not n:
            lines.append("  " * indent + f"[NOT FOUND] {sid}")
            return
        prefix = "  " * indent + ("└─ " if indent > 0 else "")
        etype  = n.get("evolution_type", "?")
        ver    = n.get("version", "?")
        name   = n.get("name", "?")[:55]
        lines.append(f"{prefix}[{etype}] v{ver}  {sid[:10]}  {name}")
        children = db.get_descendants(sid, max_depth=1)
        for c in children:
            _render(c["id"], indent + 1)
    
    _render(skill_id)
    return lines


def cmd_ancestors(db, skill_id):
    ancs = db.get_ancestors(skill_id)
    lines = [f"=== 祖先链 — {skill_id}（共 {len(ancs)} 级）==="]
    for a in ancs:
        lines.append(_fmt(a))
    return lines


def cmd_descendants(db, skill_id):
    descs = db.get_descendants(skill_id)
    lines = [f"=== 所有后代 — {skill_id}（共 {len(descs)} 个）==="]
    for d in descs:
        lines.append(_fmt(d))
    return lines


def cmd_search(db, query):
    results = db.search(query, limit=20)
    lines = [f"=== 搜索 '{query}' → {len(results)} 条结果 ==="]
    for r in results:
        lines.append(_fmt(r, detail=True))
    return lines


def cmd_show(db, skill_id):
    node = db.get(skill_id)
    if not node:
        return [f"[NOT FOUND] {skill_id}"]
    lines = [f"=== 详情 — {skill_id} ==="]
    for k, v in node.items():
        lines.append(f"  {k:<20}: {str(v)[:100]}")
    return lines


def cmd_recent(db, n=10):
    import sqlite3
    with sqlite3.connect(str(Path(DB_PATH))) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM skill_lineage ORDER BY updated_at DESC LIMIT ?", (n,)
        ).fetchall()
    lines = [f"=== 最近 {n} 条（按更新时间）==="]
    for row in rows:
        d = dict(row)
        lines.append(_fmt(d))
    return lines


def main():
    db = SkillLineage(db_path=DB_PATH)
    args = sys.argv[1:]

    if not args or args[0] == "stats":
        lines = cmd_stats(db)
    elif args[0] == "roots":
        lines = cmd_roots(db)
    elif args[0] == "tree" and len(args) > 1:
        lines = cmd_tree(db, args[1])
    elif args[0] == "anc" and len(args) > 1:
        lines = cmd_ancestors(db, args[1])
    elif args[0] == "desc" and len(args) > 1:
        lines = cmd_descendants(db, args[1])
    elif args[0] == "search" and len(args) > 1:
        lines = cmd_search(db, args[1])
    elif args[0] == "show" and len(args) > 1:
        lines = cmd_show(db, args[1])
    elif args[0] == "recent":
        n = int(args[1]) if len(args) > 1 else 10
        lines = cmd_recent(db, n)
    else:
        lines = [
            "用法:",
            "  python lineage_cli.py stats",
            "  python lineage_cli.py roots",
            "  python lineage_cli.py tree   <skill_id>",
            "  python lineage_cli.py anc    <skill_id>",
            "  python lineage_cli.py desc   <skill_id>",
            "  python lineage_cli.py search <关键词>",
            "  python lineage_cli.py show   <skill_id>",
            "  python lineage_cli.py recent [N]",
        ]

    output = "\n".join(lines)
    print(output)

    # 同时写文件，供不能看 stdout 的环境使用
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(output)


if __name__ == "__main__":
    # 强制 stdout 用 UTF-8，避免 Windows GBK 编码错误
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()
