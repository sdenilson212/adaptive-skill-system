"""
migrate_kb_to_lineage.py
========================
把 knowledge-base.md 里现有的 KB 条目全部导入 SQLite 谱系库。

运行方式：
    cd <repo-root>/output/adaptive-skill-system
    C:\\Python314\\python.exe migrate_kb_to_lineage.py


导入规则：
    - 所有存量条目 parent_id=None，evolution_type='original'
    - version 从条目里读，没有则默认 '1.0'
    - quality_score 尝试从 confidence 字段读
    - 已存在的条目跳过（幂等，可重复运行）
"""

import sys
import yaml
import importlib.util
from pathlib import Path

# 路径配置
PROJECT_ROOT = Path(__file__).resolve().parent

# 直接从文件路径导入 SkillLineage，绕过 __init__.py 的版本冲突
_lineage_file = PROJECT_ROOT / "adaptive_skill" / "skill_lineage.py"
_spec = importlib.util.spec_from_file_location("skill_lineage", _lineage_file)
_mod  = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
SkillLineage = _mod.SkillLineage
resolve_default_memory_bank_dir = _mod.resolve_default_memory_bank_dir
resolve_default_db_path = _mod.resolve_default_db_path

MEMORY_BANK_DIR = resolve_default_memory_bank_dir()
KB_PATH = MEMORY_BANK_DIR / "knowledge-base.md"
LINEAGE_DB = resolve_default_db_path()



def confidence_to_score(conf):
    """把字符串置信度转为 0-1 浮点数"""
    if isinstance(conf, (int, float)):
        return float(conf)
    mapping = {"high": 0.9, "medium": 0.7, "low": 0.5}
    return mapping.get(str(conf).lower(), None)


def run_migration():
    # 读取 KB
    if not KB_PATH.exists():
        result_lines = [f"[ERROR] KB 文件不存在: {KB_PATH}"]
        _write_result(result_lines)
        return

    with open(KB_PATH, "r", encoding="utf-8") as f:
        raw = f.read()

    # knowledge-base.md 可能包含多个 YAML 文档（多个 --- 分隔符）
    # 收集所有文档里的 entries
    entries = []
    try:
        for doc in yaml.safe_load_all(raw):
            if isinstance(doc, dict):
                entries.extend(doc.get("entries", []))
            elif isinstance(doc, list):
                entries.extend(doc)
    except yaml.YAMLError as e:
        _write_result([f"[ERROR] 解析 KB 失败: {e}"])
        return

    result_lines = [f"KB 条目总数: {len(entries)}"]

    # 初始化谱系库
    db = SkillLineage(db_path=str(LINEAGE_DB))

    inserted = 0
    skipped  = 0
    errors   = 0

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        skill_id = str(entry.get("id", ""))
        if not skill_id:
            skipped += 1
            continue

        # 检查是否已存在
        existing = db.get(skill_id)
        if existing:
            skipped += 1
            continue

        # 构造轻量 Skill dict
        skill_dict = {
            "skill_id":      skill_id,
            "name":          entry.get("title", "未命名"),
            "description":   (entry.get("content", "") or "")[:200],
            "version":       entry.get("version", "1.0"),
            "status":        "active" if entry.get("confirmed", True) else "experimental",
            "parent_id":     None,
            "evolution_type": "original",
            "generation_info": {
                "type":     "manual",
                "source":   entry.get("source", "user-upload"),
                "category": entry.get("category", ""),
                "tags":     entry.get("tags", []),
            },
            "quality_metrics": {},
        }

        quality_score = confidence_to_score(entry.get("confidence"))

        try:
            db.register(skill_dict, quality_score=quality_score)
            inserted += 1
            result_lines.append(f"  OK {skill_id[:8]}  {entry.get('title', '')[:50]}")
        except Exception as e:
            errors += 1
            result_lines.append(f"  ERR {skill_id[:8]}  {e}")

    result_lines.append(f"\n迁移完成：插入 {inserted} 条 | 跳过 {skipped} 条 | 错误 {errors} 条")
    result_lines.append(f"谱系库路径：{LINEAGE_DB}")

    stats = db.stats()
    result_lines.append(f"\n谱系库当前状态：")
    result_lines.append(f"  总技能数：{stats['total_skills']}")
    result_lines.append(f"  按进化类型：{stats['by_evolution_type']}")
    result_lines.append(f"  最大谱系深度：{stats['max_lineage_depth']}")
    if stats["avg_quality_score"]:
        result_lines.append(f"  平均质量分：{stats['avg_quality_score']}")

    _write_result(result_lines)


def _write_result(lines):
    """把结果写到文件（绕过 PowerShell 输出吞噬）"""
    out_path = PROJECT_ROOT / "output" / "migrate_lineage_result.txt"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    # 同时尝试 print（cmd 环境下能看到）
    for line in lines:
        print(line)


if __name__ == "__main__":
    run_migration()
