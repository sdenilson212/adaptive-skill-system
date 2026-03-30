"""
Skill Lineage — 版本 DAG + SQLite 持久化
==========================================
每当一个 Skill 被创建（原创/派生/修复/组合/自动生成），
就在这里记录它与父节点的关系，形成有向无环图（DAG）。

使用方式：
    from adaptive_skill.skill_lineage import SkillLineage

    db = SkillLineage()                          # 默认 DB 路径
    db.register(skill)                           # 注册新 Skill
    db.get_ancestors("SKL-xxx")                  # 查所有祖先
    db.get_descendants("SKL-xxx")                # 查所有后代
    db.get_lineage_tree("SKL-xxx")               # 完整谱系树
    db.list_roots()                              # 列出所有原创 Skill
    db.search(query="关键词")                    # 搜标题/描述
"""

import sqlite3
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any


# 默认 DB 文件路径（与 knowledge-base.md 同目录）
DEFAULT_DB_PATH = (
    Path("C:/Users/sdenilson/WorkBuddy/Claw/output/ai-memory-system"
         "/engine/memory-bank/skill_lineage.db")
)


class SkillLineage:
    """
    Skill 版本谱系数据库。
    用 SQLite 记录每个 Skill 的父子关系，支持任意深度的 DAG 查询。
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------ #
    #  内部初始化
    # ------------------------------------------------------------------ #

    def _init_db(self):
        """建表（如果不存在）"""
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS skill_lineage (
                    -- 主键
                    id          TEXT PRIMARY KEY,

                    -- 谱系字段
                    parent_id       TEXT,           -- NULL = 原创 Skill
                    evolution_type  TEXT NOT NULL DEFAULT 'original',
                    -- original | derived | fixed | composed | auto-generated

                    -- 版本
                    version         TEXT NOT NULL DEFAULT '1.0',
                    depth           INTEGER NOT NULL DEFAULT 0,
                    -- 距离根节点的跳数

                    -- 描述字段
                    name            TEXT NOT NULL,
                    description     TEXT,
                    status          TEXT NOT NULL DEFAULT 'active',
                    quality_score   REAL,

                    -- 时间
                    created_at      TEXT NOT NULL,
                    updated_at      TEXT NOT NULL,

                    -- 额外数据（JSON 序列化）
                    extra           TEXT,

                    -- 外键约束：parent 必须已存在
                    FOREIGN KEY (parent_id) REFERENCES skill_lineage(id)
                );

                -- 快速查父子关系的索引
                CREATE INDEX IF NOT EXISTS idx_parent ON skill_lineage(parent_id);
                CREATE INDEX IF NOT EXISTS idx_status  ON skill_lineage(status);
                CREATE INDEX IF NOT EXISTS idx_etype   ON skill_lineage(evolution_type);
            """)

    def _conn(self):
        """返回 SQLite 连接（使用上下文管理器自动提交/回滚）"""
        return sqlite3.connect(str(self.db_path))

    # ------------------------------------------------------------------ #
    #  写入
    # ------------------------------------------------------------------ #

    def register(self, skill, quality_score: Optional[float] = None) -> bool:
        """
        注册一个 Skill 到谱系库。
        skill 可以是 Skill dataclass 实例，也可以是字典。

        Returns:
            True  — 成功插入或更新
            False — 已存在且未变化，跳过
        """
        if hasattr(skill, 'to_dict'):
            d = skill.to_dict()
        else:
            d = dict(skill)

        skill_id       = d["skill_id"]
        parent_id      = d.get("parent_id")
        evolution_type = d.get("evolution_type", "original")
        version        = d.get("version", "1.0")
        name           = d.get("name", "")
        description    = d.get("description", "")
        status         = d.get("status", "active")
        now            = datetime.now().isoformat()

        # 计算深度
        depth = self._calc_depth(parent_id)

        # 把 quality_metrics 里的 success_rate 当 quality_score（如果没显式传入）
        if quality_score is None:
            qm = d.get("quality_metrics", {})
            quality_score = qm.get("success_rate") if isinstance(qm, dict) else None

        # extra 存 generation_info 等补充信息
        extra = json.dumps({
            "generation_info": d.get("generation_info", {}),
            "tags": d.get("tags", []),
        }, ensure_ascii=False)

        with self._conn() as conn:
            existing = conn.execute(
                "SELECT version FROM skill_lineage WHERE id = ?", (skill_id,)
            ).fetchone()

            if existing:
                # 已存在 → 更新（版本升级或状态变更）
                conn.execute("""
                    UPDATE skill_lineage
                    SET parent_id=?, evolution_type=?, version=?, depth=?,
                        name=?, description=?, status=?, quality_score=?,
                        updated_at=?, extra=?
                    WHERE id=?
                """, (parent_id, evolution_type, version, depth,
                      name, description, status, quality_score,
                      now, extra, skill_id))
                return True
            else:
                # 新插入
                conn.execute("""
                    INSERT INTO skill_lineage
                        (id, parent_id, evolution_type, version, depth,
                         name, description, status, quality_score,
                         created_at, updated_at, extra)
                    VALUES (?,?,?,?,?, ?,?,?,?, ?,?,?)
                """, (skill_id, parent_id, evolution_type, version, depth,
                      name, description, status, quality_score,
                      now, now, extra))
                return True

    def _calc_depth(self, parent_id: Optional[str]) -> int:
        """递归计算深度（根节点 = 0）"""
        if parent_id is None:
            return 0
        with self._conn() as conn:
            row = conn.execute(
                "SELECT depth FROM skill_lineage WHERE id = ?", (parent_id,)
            ).fetchone()
        if row:
            return row[0] + 1
        return 1  # 父节点还没注册，暂时假设 depth=1

    # ------------------------------------------------------------------ #
    #  读取 / 查询
    # ------------------------------------------------------------------ #

    def get(self, skill_id: str) -> Optional[Dict]:
        """按 ID 获取单条记录"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM skill_lineage WHERE id = ?", (skill_id,)
            ).fetchone()
            if row:
                return self._row_to_dict(conn, row)
        return None

    def get_ancestors(self, skill_id: str) -> List[Dict]:
        """
        获取某 Skill 的所有祖先（从父到根，按 depth 降序）。
        返回列表第一项是直接父节点，最后一项是根节点。
        """
        ancestors = []
        current_id = skill_id
        visited = set()

        with self._conn() as conn:
            while True:
                row = conn.execute(
                    "SELECT * FROM skill_lineage WHERE id = ?", (current_id,)
                ).fetchone()
                if not row:
                    break
                d = self._row_to_dict(conn, row)
                parent_id = d.get("parent_id")
                if not parent_id or parent_id in visited:
                    break
                visited.add(parent_id)

                parent_row = conn.execute(
                    "SELECT * FROM skill_lineage WHERE id = ?", (parent_id,)
                ).fetchone()
                if not parent_row:
                    break
                ancestors.append(self._row_to_dict(conn, parent_row))
                current_id = parent_id

        return ancestors

    def get_descendants(self, skill_id: str, max_depth: int = 10) -> List[Dict]:
        """
        获取某 Skill 的所有后代（广度优先）。
        max_depth 防止无限递归。
        """
        result = []
        queue = [skill_id]
        visited = {skill_id}
        depth_map = {skill_id: 0}

        with self._conn() as conn:
            while queue:
                current = queue.pop(0)
                current_depth = depth_map[current]
                if current_depth >= max_depth:
                    continue

                children = conn.execute(
                    "SELECT * FROM skill_lineage WHERE parent_id = ?", (current,)
                ).fetchall()

                for row in children:
                    d = self._row_to_dict(conn, row)
                    cid = d["id"]
                    if cid not in visited:
                        visited.add(cid)
                        result.append(d)
                        queue.append(cid)
                        depth_map[cid] = current_depth + 1

        return result

    def get_lineage_tree(self, skill_id: str) -> Dict:
        """
        返回以 skill_id 为根的完整谱系树（JSON 可序列化）。
        结构：{ "skill": {...}, "children": [ {...}, ... ] }
        """
        node = self.get(skill_id)
        if not node:
            return {}

        children_flat = self.get_descendants(skill_id, max_depth=1)
        children = [self.get_lineage_tree(c["id"]) for c in children_flat]

        return {
            "skill": node,
            "children": children
        }

    def list_roots(self) -> List[Dict]:
        """列出所有原创（无父节点）的 Skill"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM skill_lineage WHERE parent_id IS NULL ORDER BY created_at DESC"
            ).fetchall()
            return [self._row_to_dict(conn, row) for row in rows]

    def search(self, query: str, limit: int = 20) -> List[Dict]:
        """全文搜索 name / description（LIKE 匹配）"""
        pattern = f"%{query}%"
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM skill_lineage
                WHERE name LIKE ? OR description LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
            """, (pattern, pattern, limit)).fetchall()
            return [self._row_to_dict(conn, row) for row in rows]

    def stats(self) -> Dict:
        """返回谱系库统计信息"""
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM skill_lineage").fetchone()[0]
            by_type = dict(conn.execute(
                "SELECT evolution_type, COUNT(*) FROM skill_lineage GROUP BY evolution_type"
            ).fetchall())
            by_status = dict(conn.execute(
                "SELECT status, COUNT(*) FROM skill_lineage GROUP BY status"
            ).fetchall())
            max_depth = conn.execute("SELECT MAX(depth) FROM skill_lineage").fetchone()[0] or 0
            avg_quality = conn.execute(
                "SELECT AVG(quality_score) FROM skill_lineage WHERE quality_score IS NOT NULL"
            ).fetchone()[0]

        return {
            "total_skills": total,
            "by_evolution_type": by_type,
            "by_status": by_status,
            "max_lineage_depth": max_depth,
            "avg_quality_score": round(avg_quality, 3) if avg_quality else None,
            "db_path": str(self.db_path),
        }

    # ------------------------------------------------------------------ #
    #  工具方法
    # ------------------------------------------------------------------ #

    @staticmethod
    def _row_to_dict(conn, row) -> Dict:
        """将 sqlite3 Row 转为字典"""
        # 获取列名
        cursor = conn.execute("PRAGMA table_info(skill_lineage)")
        columns = [col[1] for col in cursor.fetchall()]
        d = dict(zip(columns, row))
        # 反序列化 extra
        if d.get("extra"):
            try:
                d["extra"] = json.loads(d["extra"])
            except Exception:
                pass
        return d

    def print_tree(self, skill_id: str, indent: int = 0):
        """
        在终端打印谱系树（调试用）。
        示例输出：
            [original] v1.0  SKL-001  登录页组件
              └─ [derived] v1.1  SKL-002  登录页组件（带记住密码）
                   └─ [fixed] v1.2  SKL-003  登录页组件（修复样式bug）
        """
        node = self.get(skill_id)
        if not node:
            print(f"{'  ' * indent}[NOT FOUND] {skill_id}")
            return

        prefix = "  " * indent + ("└─ " if indent > 0 else "")
        etype  = node.get("evolution_type", "?")
        ver    = node.get("version", "?")
        name   = node.get("name", "?")
        print(f"{prefix}[{etype}] v{ver}  {skill_id}  {name}")

        children = self.get_descendants(skill_id, max_depth=1)
        for child in children:
            self.print_tree(child["id"], indent + 1)


# ------------------------------------------------------------------ #
#  命令行入口
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    import sys

    db = SkillLineage()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"

    if cmd == "stats":
        import pprint
        pprint.pprint(db.stats())

    elif cmd == "roots":
        roots = db.list_roots()
        print(f"共 {len(roots)} 个根 Skill：")
        for r in roots:
            print(f"  {r['id']}  [{r['evolution_type']}] v{r['version']}  {r['name']}")

    elif cmd == "tree" and len(sys.argv) > 2:
        db.print_tree(sys.argv[2])

    elif cmd == "ancestors" and len(sys.argv) > 2:
        ancs = db.get_ancestors(sys.argv[2])
        print(f"祖先链（共 {len(ancs)} 级）：")
        for a in ancs:
            print(f"  {a['id']}  v{a['version']}  {a['name']}")

    elif cmd == "search" and len(sys.argv) > 2:
        results = db.search(sys.argv[2])
        print(f"搜索 '{sys.argv[2]}' → {len(results)} 条结果：")
        for r in results:
            print(f"  {r['id']}  v{r['version']}  {r['name']}")

    else:
        print("""用法:
  python skill_lineage.py stats
  python skill_lineage.py roots
  python skill_lineage.py tree   <skill_id>
  python skill_lineage.py ancestors <skill_id>
  python skill_lineage.py search <关键词>
""")
