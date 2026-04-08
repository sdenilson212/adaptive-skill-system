"""
用户反馈收集与分析

实现用户反馈闭环，让系统能够：
1. 收集用户对 AI 回复的评价（点赞/点踩/标注）
2. 持久化反馈数据，用于后续分析
3. 分析反馈趋势，生成优化建议
4. 触发 Skill 更新/下架流程

设计原则
--------
- 非阻塞：反馈收集失败不影响主流程
- 可追溯：每个反馈关联到具体的 session / task / skill
- 可分析：支持聚合统计和趋势分析
- 可行动：反馈达到阈值自动触发优化流程
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构定义
# ---------------------------------------------------------------------------

class FeedbackType(Enum):
    """反馈类型"""
    THUMBS_UP = "thumbs_up"           # 点赞
    THUMBS_DOWN = "thumbs_down"       # 点踩
    CORRECTION = "correction"         # 修正建议（用户提供正确答案）
    RATING = "rating"                 # 评分（1-5 星）
    COMMENT = "comment"               # 文字评论
    REPORT = "report"                 # 问题报告（有害/错误内容）
    VERIFICATION = "verification"     # 人工审核确认


class FeedbackStatus(Enum):
    """反馈状态"""
    NEW = "new"                       # 新反馈，待处理
    ACKNOWLEDGED = "acknowledged"     # 已确认，待分析
    ACTIONED = "actioned"             # 已采取行动
    DISMISSED = "dismissed"           # 已忽略（无效反馈）


@dataclass
class FeedbackEntry:
    """单条反馈记录"""
    feedback_id: str
    feedback_type: FeedbackType
    status: FeedbackStatus = FeedbackStatus.NEW
    
    # 关联信息
    task_id: Optional[str] = None
    session_id: Optional[str] = None
    skill_id: Optional[str] = None
    layer_used: Optional[int] = None
    
    # 反馈内容
    rating: Optional[int] = None          # 1-5 星
    comment: Optional[str] = None         # 文字评论
    correction: Optional[str] = None      # 用户提供的正确答案
    tags: List[str] = field(default_factory=list)
    
    # 元数据
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data["feedback_type"] = self.feedback_type.value
        data["status"] = self.status.value
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat() if self.updated_at else None
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FeedbackEntry":
        """从字典创建"""
        data["feedback_type"] = FeedbackType(data["feedback_type"])
        data["status"] = FeedbackStatus(data["status"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        if data.get("updated_at"):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return cls(**data)


# ---------------------------------------------------------------------------
# 反馈存储
# ---------------------------------------------------------------------------

class FeedbackStorage:
    """
    反馈数据持久化存储
    
    使用 SQLite 存储，支持：
    - 按 skill_id / task_id / date 聚合统计
    - 快速查询未处理的反馈
    - 导出为 JSON/CSV
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        初始化存储
        
        Args:
            db_path: SQLite 数据库路径，默认为 ~/.adaptive_skill/feedback.db
        """
        if db_path is None:
            db_dir = Path.home() / ".adaptive_skill"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(db_dir / "feedback.db")
        
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()
    
    def _init_db(self) -> None:
        """初始化数据库表"""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    feedback_id TEXT PRIMARY KEY,
                    feedback_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    task_id TEXT,
                    session_id TEXT,
                    skill_id TEXT,
                    layer_used INTEGER,
                    rating INTEGER,
                    comment TEXT,
                    correction TEXT,
                    tags TEXT,
                    user_id TEXT,
                    tenant_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT
                )
            """)
            
            # 创建索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_id ON feedback(skill_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_task_id ON feedback(task_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON feedback(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON feedback(created_at)")
            
            conn.commit()
    
    def save(self, entry: FeedbackEntry) -> bool:
        """保存反馈记录"""
        try:
            with self._lock, sqlite3.connect(self._db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO feedback VALUES (
                        :feedback_id, :feedback_type, :status,
                        :task_id, :session_id, :skill_id, :layer_used,
                        :rating, :comment, :correction, :tags,
                        :user_id, :tenant_id, :created_at, :updated_at
                    )
                """, {
                    "feedback_id": entry.feedback_id,
                    "feedback_type": entry.feedback_type.value,
                    "status": entry.status.value,
                    "task_id": entry.task_id,
                    "session_id": entry.session_id,
                    "skill_id": entry.skill_id,
                    "layer_used": entry.layer_used,
                    "rating": entry.rating,
                    "comment": entry.comment,
                    "correction": entry.correction,
                    "tags": json.dumps(entry.tags),
                    "user_id": entry.user_id,
                    "tenant_id": entry.tenant_id,
                    "created_at": entry.created_at.isoformat(),
                    "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
                })
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to save feedback: {e}")
            return False
    
    def get(self, feedback_id: str) -> Optional[FeedbackEntry]:
        """获取单条反馈"""
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM feedback WHERE feedback_id = ?",
                    (feedback_id,)
                )
                row = cursor.fetchone()
                if row:
                    return self._row_to_entry(row)
                return None
        except Exception as e:
            logger.error(f"Failed to get feedback: {e}")
            return None
    
    def list(self, 
             skill_id: Optional[str] = None,
             status: Optional[FeedbackStatus] = None,
             since: Optional[datetime] = None,
             limit: int = 100) -> List[FeedbackEntry]:
        """列出反馈记录"""
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                query = "SELECT * FROM feedback WHERE 1=1"
                params: List[Any] = []
                
                if skill_id:
                    query += " AND skill_id = ?"
                    params.append(skill_id)
                if status:
                    query += " AND status = ?"
                    params.append(status.value)
                if since:
                    query += " AND created_at >= ?"
                    params.append(since.isoformat())
                
                query += " ORDER BY created_at DESC LIMIT ?"
                params.append(limit)
                
                cursor = conn.execute(query, params)
                return [self._row_to_entry(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to list feedback: {e}")
            return []
    
    def _row_to_entry(self, row: sqlite3.Row) -> FeedbackEntry:
        """将数据库行转换为 FeedbackEntry"""
        return FeedbackEntry(
            feedback_id=row["feedback_id"],
            feedback_type=FeedbackType(row["feedback_type"]),
            status=FeedbackStatus(row["status"]),
            task_id=row["task_id"],
            session_id=row["session_id"],
            skill_id=row["skill_id"],
            layer_used=row["layer_used"],
            rating=row["rating"],
            comment=row["comment"],
            correction=row["correction"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
            user_id=row["user_id"],
            tenant_id=row["tenant_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )


# ---------------------------------------------------------------------------
# 反馈收集器
# ---------------------------------------------------------------------------

class FeedbackCollector:
    """
    反馈收集器
    
    提供统一的反馈收集接口，支持：
    - 快速收集点赞/点踩
    - 收集详细评价（评分+评论）
    - 收集修正建议
    - 触发后续处理流程
    
    Example:
        >>> collector = FeedbackCollector()
        >>> collector.thumbs_up(task_id="task-123", skill_id="skill-456")
        >>> collector.rate(task_id="task-123", rating=4, comment="不错但可以更好")
    """
    
    def __init__(self, storage: Optional[FeedbackStorage] = None):
        self._storage = storage or FeedbackStorage()
        self._callbacks: Dict[FeedbackType, List[Callable]] = defaultdict(list)
    
    def register_callback(self, feedback_type: FeedbackType, callback: Callable[[FeedbackEntry], None]) -> None:
        """
        注册回调函数，当收到指定类型的反馈时触发
        
        Args:
            feedback_type: 反馈类型
            callback: 回调函数，接收 FeedbackEntry 参数
        """
        self._callbacks[feedback_type].append(callback)
    
    def _generate_id(self) -> str:
        """生成唯一 ID"""
        import uuid
        return f"fb-{uuid.uuid4().hex[:12]}"
    
    def _emit(self, entry: FeedbackEntry) -> None:
        """触发回调"""
        for callback in self._callbacks.get(entry.feedback_type, []):
            try:
                callback(entry)
            except Exception as e:
                logger.error(f"Feedback callback error: {e}")
    
    def thumbs_up(self,
                  task_id: Optional[str] = None,
                  skill_id: Optional[str] = None,
                  session_id: Optional[str] = None,
                  layer_used: Optional[int] = None,
                  user_id: Optional[str] = None,
                  tenant_id: Optional[str] = None) -> FeedbackEntry:
        """收集点赞"""
        entry = FeedbackEntry(
            feedback_id=self._generate_id(),
            feedback_type=FeedbackType.THUMBS_UP,
            task_id=task_id,
            skill_id=skill_id,
            session_id=session_id,
            layer_used=layer_used,
            user_id=user_id,
            tenant_id=tenant_id,
        )
        self._storage.save(entry)
        self._emit(entry)
        logger.info(f"Collected thumbs_up: {entry.feedback_id}")
        return entry
    
    def thumbs_down(self,
                    task_id: Optional[str] = None,
                    skill_id: Optional[str] = None,
                    session_id: Optional[str] = None,
                    layer_used: Optional[int] = None,
                    user_id: Optional[str] = None,
                    tenant_id: Optional[str] = None,
                    reason: Optional[str] = None) -> FeedbackEntry:
        """收集点踩"""
        entry = FeedbackEntry(
            feedback_id=self._generate_id(),
            feedback_type=FeedbackType.THUMBS_DOWN,
            task_id=task_id,
            skill_id=skill_id,
            session_id=session_id,
            layer_used=layer_used,
            user_id=user_id,
            tenant_id=tenant_id,
            comment=reason,
        )
        self._storage.save(entry)
        self._emit(entry)
        logger.info(f"Collected thumbs_down: {entry.feedback_id}")
        return entry
    
    def rate(self,
             rating: int,
             task_id: Optional[str] = None,
             skill_id: Optional[str] = None,
             session_id: Optional[str] = None,
             layer_used: Optional[int] = None,
             user_id: Optional[str] = None,
             tenant_id: Optional[str] = None,
             comment: Optional[str] = None) -> FeedbackEntry:
        """
        收集评分
        
        Args:
            rating: 评分（1-5 星）
        """
        if not 1 <= rating <= 5:
            raise ValueError("Rating must be between 1 and 5")
        
        entry = FeedbackEntry(
            feedback_id=self._generate_id(),
            feedback_type=FeedbackType.RATING,
            task_id=task_id,
            skill_id=skill_id,
            session_id=session_id,
            layer_used=layer_used,
            user_id=user_id,
            tenant_id=tenant_id,
            rating=rating,
            comment=comment,
        )
        self._storage.save(entry)
        self._emit(entry)
        logger.info(f"Collected rating {rating}: {entry.feedback_id}")
        return entry
    
    def correct(self,
                correction: str,
                task_id: Optional[str] = None,
                skill_id: Optional[str] = None,
                session_id: Optional[str] = None,
                layer_used: Optional[int] = None,
                user_id: Optional[str] = None,
                tenant_id: Optional[str] = None,
                comment: Optional[str] = None) -> FeedbackEntry:
        """
        收集修正建议
        
        Args:
            correction: 用户提供的正确答案
        """
        entry = FeedbackEntry(
            feedback_id=self._generate_id(),
            feedback_type=FeedbackType.CORRECTION,
            task_id=task_id,
            skill_id=skill_id,
            session_id=session_id,
            layer_used=layer_used,
            user_id=user_id,
            tenant_id=tenant_id,
            correction=correction,
            comment=comment,
        )
        self._storage.save(entry)
        self._emit(entry)
        logger.info(f"Collected correction: {entry.feedback_id}")
        return entry
    
    def comment(self,
                comment: str,
                task_id: Optional[str] = None,
                skill_id: Optional[str] = None,
                session_id: Optional[str] = None,
                layer_used: Optional[int] = None,
                user_id: Optional[str] = None,
                tenant_id: Optional[str] = None,
                tags: Optional[List[str]] = None) -> FeedbackEntry:
        """收集文字评论"""
        entry = FeedbackEntry(
            feedback_id=self._generate_id(),
            feedback_type=FeedbackType.COMMENT,
            task_id=task_id,
            skill_id=skill_id,
            session_id=session_id,
            layer_used=layer_used,
            user_id=user_id,
            tenant_id=tenant_id,
            comment=comment,
            tags=tags or [],
        )
        self._storage.save(entry)
        self._emit(entry)
        logger.info(f"Collected comment: {entry.feedback_id}")
        return entry
    
    def report(self,
               task_id: Optional[str] = None,
               skill_id: Optional[str] = None,
               session_id: Optional[str] = None,
               layer_used: Optional[int] = None,
               user_id: Optional[str] = None,
               tenant_id: Optional[str] = None,
               reason: Optional[str] = None,
               tags: Optional[List[str]] = None) -> FeedbackEntry:
        """报告问题（有害/错误内容）"""
        entry = FeedbackEntry(
            feedback_id=self._generate_id(),
            feedback_type=FeedbackType.REPORT,
            task_id=task_id,
            skill_id=skill_id,
            session_id=session_id,
            layer_used=layer_used,
            user_id=user_id,
            tenant_id=tenant_id,
            comment=reason,
            tags=tags or [],
        )
        self._storage.save(entry)
        self._emit(entry)
        logger.info(f"Collected report: {entry.feedback_id}")
        return entry


# ---------------------------------------------------------------------------
# 反馈分析器
# ---------------------------------------------------------------------------

@dataclass
class SkillFeedbackStats:
    """单个 Skill 的反馈统计"""
    skill_id: str
    total_feedbacks: int = 0
    thumbs_up_count: int = 0
    thumbs_down_count: int = 0
    avg_rating: Optional[float] = None
    correction_count: int = 0
    report_count: int = 0
    satisfaction_rate: float = 0.0  # 优先使用二元反馈；缺失时回退到评分折算
    
    # 建议
    recommendation: Optional[str] = None


class FeedbackAnalyzer:
    """
    反馈分析器
    
    分析反馈数据，生成统计报告和优化建议。
    
    Example:
        >>> analyzer = FeedbackAnalyzer(storage)
        >>> stats = analyzer.analyze_skill("skill-123")
        >>> print(stats.satisfaction_rate)
        0.85
    """
    
    # 触发告警的阈值
    LOW_SATISFACTION_THRESHOLD = 0.6    # 满意度低于 60%
    HIGH_REPORT_THRESHOLD = 3           # 报告数超过 3 次
    HIGH_CORRECTION_THRESHOLD = 2       # 修正数超过 2 次
    
    def __init__(self, storage: Optional[FeedbackStorage] = None):
        self._storage = storage or FeedbackStorage()
    
    def analyze_skill(self, 
                      skill_id: str,
                      since: Optional[datetime] = None) -> SkillFeedbackStats:
        """
        分析单个 Skill 的反馈
        
        Args:
            skill_id: Skill ID
            since: 只分析此时间之后的反馈
        
        Returns:
            统计结果和建议
        """
        feedbacks = self._storage.list(skill_id=skill_id, since=since, limit=1000)
        
        stats = SkillFeedbackStats(skill_id=skill_id)
        stats.total_feedbacks = len(feedbacks)
        
        if not feedbacks:
            stats.recommendation = "暂无反馈数据"
            return stats
        
        ratings = []
        
        for fb in feedbacks:
            if fb.feedback_type == FeedbackType.THUMBS_UP:
                stats.thumbs_up_count += 1
            elif fb.feedback_type == FeedbackType.THUMBS_DOWN:
                stats.thumbs_down_count += 1
            elif fb.feedback_type == FeedbackType.RATING and fb.rating:
                ratings.append(fb.rating)
            elif fb.feedback_type == FeedbackType.CORRECTION:
                stats.correction_count += 1
            elif fb.feedback_type == FeedbackType.REPORT:
                stats.report_count += 1
        
        # 计算满意度
        total_binary = stats.thumbs_up_count + stats.thumbs_down_count
        if total_binary > 0:
            stats.satisfaction_rate = stats.thumbs_up_count / total_binary
        
        # 计算平均评分
        if ratings:
            stats.avg_rating = sum(ratings) / len(ratings)
            if total_binary == 0:
                # ratings-only 场景下回退到评分折算，避免把高分误判成 0% 满意度
                stats.satisfaction_rate = stats.avg_rating / 5
        
        # 生成建议
        stats.recommendation = self._generate_recommendation(stats)
        
        return stats
    
    def _generate_recommendation(self, stats: SkillFeedbackStats) -> str:
        """生成优化建议"""
        recommendations = []
        
        if stats.satisfaction_rate < self.LOW_SATISFACTION_THRESHOLD:
            recommendations.append(f"满意度偏低({stats.satisfaction_rate:.0%})，建议审查 Skill 内容")
        
        if stats.report_count >= self.HIGH_REPORT_THRESHOLD:
            recommendations.append(f"收到 {stats.report_count} 次问题报告，建议立即审查")
        
        if stats.correction_count >= self.HIGH_CORRECTION_THRESHOLD:
            recommendations.append(f"收到 {stats.correction_count} 条修正建议，可考虑更新 Skill")
        
        if stats.avg_rating is not None and stats.avg_rating < 3:
            recommendations.append(f"平均评分 {stats.avg_rating:.1f} 星，建议优化或下架")
        
        if not recommendations:
            if stats.satisfaction_rate >= 0.9:
                return "表现优秀，继续保持"
            elif stats.satisfaction_rate >= 0.7:
                return "表现良好，可小幅优化"
            else:
                return "表现正常，持续观察"
        
        return "；".join(recommendations)
    
    def analyze_all(self, 
                    since: Optional[datetime] = None) -> Dict[str, SkillFeedbackStats]:
        """
        分析所有 Skill 的反馈
        
        Returns:
            skill_id -> 统计结果的映射
        """
        # 获取所有反馈
        all_feedbacks = self._storage.list(since=since, limit=10000)
        
        # 按 skill_id 分组
        skill_ids = set(fb.skill_id for fb in all_feedbacks if fb.skill_id)
        
        results = {}
        for skill_id in skill_ids:
            results[skill_id] = self.analyze_skill(skill_id, since)
        
        return results
    
    def get_low_performers(self,
                           since: Optional[datetime] = None,
                           min_feedbacks: int = 3) -> List[SkillFeedbackStats]:
        """
        获取表现不佳的 Skill 列表
        
        Args:
            since: 只分析此时间之后的反馈
            min_feedbacks: 最少反馈数量（低于此数量的不参与评估）
        
        Returns:
            表现不佳的 Skill 统计列表，按满意度排序
        """
        all_stats = self.analyze_all(since)
        
        low_performers = [
            stats for stats in all_stats.values()
            if stats.total_feedbacks >= min_feedbacks
            and stats.satisfaction_rate < self.LOW_SATISFACTION_THRESHOLD
        ]
        
        return sorted(low_performers, key=lambda s: s.satisfaction_rate)
    
    def get_top_performers(self,
                           since: Optional[datetime] = None,
                           min_feedbacks: int = 3,
                           top_n: int = 10) -> List[SkillFeedbackStats]:
        """
        获取表现最佳的 Skill 列表
        """
        all_stats = self.analyze_all(since)
        
        top_performers = [
            stats for stats in all_stats.values()
            if stats.total_feedbacks >= min_feedbacks
            and stats.satisfaction_rate > 0.8
        ]
        
        return sorted(top_performers, key=lambda s: s.satisfaction_rate, reverse=True)[:top_n]
