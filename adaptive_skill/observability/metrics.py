"""
系统可观测性指标收集与分析

实现运行时指标收集，支持：
1. 实时收集：各层命中率、响应延迟、置信度分布
2. 聚合统计：按小时/天/周聚合
3. 异常检测：自动检测指标异常并告警
4. 仪表盘数据：生成可用于前端展示的数据结构

设计原则
--------
- 低开销：指标收集不影响主流程性能
- 可扩展：支持自定义指标
- 可导出：支持导出为 Prometheus/OpenMetrics 格式
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构定义
# ---------------------------------------------------------------------------

class MetricType(Enum):
    """指标类型"""
    COUNTER = "counter"       # 计数器（只增不减）
    GAUGE = "gauge"           # 仪表（可增可减）
    HISTOGRAM = "histogram"   # 直方图（分布统计）
    SUMMARY = "summary"       # 摘要（分位数统计）


@dataclass
class MetricEntry:
    """单条指标记录"""
    metric_name: str
    metric_type: MetricType
    value: float
    timestamp: datetime = field(default_factory=datetime.now)
    labels: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "metric_type": self.metric_type.value,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "labels": self.labels,
        }


@dataclass
class LayerMetrics:
    """单层统计指标"""
    layer: int
    total_requests: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    avg_confidence: float = 0.0
    hit_rate: float = 0.0
    
    # 置信度分布
    confidence_distribution: Dict[str, int] = field(default_factory=lambda: {
        "0.0-0.3": 0,
        "0.3-0.5": 0,
        "0.5-0.7": 0,
        "0.7-0.9": 0,
        "0.9-1.0": 0,
    })


@dataclass
class SystemMetrics:
    """系统整体指标"""
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 请求统计
    total_requests: int = 0
    success_rate: float = 0.0
    
    # 各层统计
    layer_metrics: Dict[int, LayerMetrics] = field(default_factory=dict)
    
    # 新 Skill 生成
    skills_generated: int = 0
    skills_composed: int = 0
    skills_from_cache: int = 0
    
    # 性能
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    
    # 置信度
    avg_confidence: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_requests": self.total_requests,
            "success_rate": self.success_rate,
            "layer_metrics": {
                k: asdict(v) for k, v in self.layer_metrics.items()
            },
            "skills_generated": self.skills_generated,
            "skills_composed": self.skills_composed,
            "skills_from_cache": self.skills_from_cache,
            "avg_latency_ms": self.avg_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "avg_confidence": self.avg_confidence,
        }


# ---------------------------------------------------------------------------
# 指标收集器
# ---------------------------------------------------------------------------

class MetricsCollector:
    """
    指标收集器
    
    收集系统运行时的各类指标，支持：
    - 实时收集：每次请求自动记录
    - 时间窗口聚合：按分钟/小时/天聚合
    - 导出：导出为 Prometheus/OpenMetrics 格式
    
    Example:
        >>> collector = MetricsCollector()
        >>> collector.record_request(layer=1, latency_ms=50, confidence=0.9, success=True)
        >>> stats = collector.get_layer_stats(layer=1)
        >>> print(stats.avg_latency_ms)
        50.0
    """
    
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_dir = Path.home() / ".adaptive_skill"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(db_dir / "metrics.db")
        
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()
        
        # 内存缓存（用于快速聚合）
        self._latency_buckets: Dict[int, List[float]] = defaultdict(list)
        self._confidence_buckets: Dict[int, List[float]] = defaultdict(list)
    
    def _init_db(self) -> None:
        """初始化数据库"""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_name TEXT NOT NULL,
                    metric_type TEXT NOT NULL,
                    value REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    labels TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON metrics(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_metric_name ON metrics(metric_name)")
            conn.commit()
    
    def record_request(self,
                       layer: int,
                       latency_ms: float,
                       confidence: float,
                       success: bool,
                       skill_id: Optional[str] = None,
                       tenant_id: Optional[str] = None) -> None:
        """
        记录一次请求
        
        Args:
            layer: 使用的层级 (1/2/3)
            latency_ms: 响应延迟（毫秒）
            confidence: 置信度 (0.0-1.0)
            success: 是否成功
            skill_id: 使用的 Skill ID
            tenant_id: 租户 ID
        """
        timestamp = datetime.now()
        
        # 写入数据库
        try:
            with self._lock, sqlite3.connect(self._db_path) as conn:
                # 记录请求计数
                conn.execute("""
                    INSERT INTO metrics (metric_name, metric_type, value, timestamp, labels)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    "request_total",
                    "counter",
                    1.0,
                    timestamp.isoformat(),
                    json.dumps({"layer": str(layer), "success": str(success).lower(), "tenant_id": tenant_id or ""}),
                ))
                
                # 记录延迟
                conn.execute("""
                    INSERT INTO metrics (metric_name, metric_type, value, timestamp, labels)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    "request_latency_ms",
                    "histogram",
                    latency_ms,
                    timestamp.isoformat(),
                    json.dumps({"layer": str(layer), "tenant_id": tenant_id or ""}),
                ))
                
                # 记录置信度
                conn.execute("""
                    INSERT INTO metrics (metric_name, metric_type, value, timestamp, labels)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    "request_confidence",
                    "histogram",
                    confidence,
                    timestamp.isoformat(),
                    json.dumps({"layer": str(layer), "tenant_id": tenant_id or ""}),
                ))
                
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to record metrics: {e}")
        
        # 更新内存缓存
        self._latency_buckets[layer].append(latency_ms)
        self._confidence_buckets[layer].append(confidence)
        
        # 限制缓存大小
        if len(self._latency_buckets[layer]) > 10000:
            self._latency_buckets[layer] = self._latency_buckets[layer][-5000:]
        if len(self._confidence_buckets[layer]) > 10000:
            self._confidence_buckets[layer] = self._confidence_buckets[layer][-5000:]
    
    def record_skill_generated(self, layer: int, skill_id: str) -> None:
        """记录新生成的 Skill"""
        try:
            with self._lock, sqlite3.connect(self._db_path) as conn:
                conn.execute("""
                    INSERT INTO metrics (metric_name, metric_type, value, timestamp, labels)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    "skill_generated",
                    "counter",
                    1.0,
                    datetime.now().isoformat(),
                    json.dumps({"layer": str(layer), "skill_id": skill_id}),
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to record skill generation: {e}")
    
    def get_layer_stats(self,
                        layer: int,
                        since: Optional[datetime] = None,
                        until: Optional[datetime] = None) -> LayerMetrics:
        """
        获取单层统计
        
        Args:
            layer: 层级
            since: 开始时间
            until: 结束时间
        """
        if since is None:
            since = datetime.now() - timedelta(hours=24)
        if until is None:
            until = datetime.now()
        
        metrics = LayerMetrics(layer=layer)
        
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # 查询请求总数
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN json_extract(labels, '$.success') = 'true' THEN 1 ELSE 0 END) as success
                    FROM metrics
                    WHERE metric_name = 'request_total'
                    AND timestamp >= ? AND timestamp <= ?
                    AND json_extract(labels, '$.layer') = ?
                """, (since.isoformat(), until.isoformat(), str(layer)))
                
                row = cursor.fetchone()
                if row:
                    metrics.total_requests = row["total"] or 0
                    metrics.success_count = row["success"] or 0
                    metrics.failure_count = metrics.total_requests - metrics.success_count
                    
                    if metrics.total_requests > 0:
                        metrics.hit_rate = metrics.success_count / metrics.total_requests
                
                # 查询延迟
                cursor = conn.execute("""
                    SELECT value FROM metrics
                    WHERE metric_name = 'request_latency_ms'
                    AND timestamp >= ? AND timestamp <= ?
                    AND json_extract(labels, '$.layer') = ?
                    ORDER BY value
                """, (since.isoformat(), until.isoformat(), str(layer)))
                
                latencies = [row[0] for row in cursor.fetchall()]
                if latencies:
                    metrics.total_latency_ms = sum(latencies)
                    metrics.avg_latency_ms = sum(latencies) / len(latencies)
                    metrics.p50_latency_ms = self._percentile(latencies, 50)
                    metrics.p95_latency_ms = self._percentile(latencies, 95)
                    metrics.p99_latency_ms = self._percentile(latencies, 99)
                
                # 查询置信度
                cursor = conn.execute("""
                    SELECT value FROM metrics
                    WHERE metric_name = 'request_confidence'
                    AND timestamp >= ? AND timestamp <= ?
                    AND json_extract(labels, '$.layer') = ?
                """, (since.isoformat(), until.isoformat(), str(layer)))
                
                confidences = [row[0] for row in cursor.fetchall()]
                if confidences:
                    metrics.avg_confidence = sum(confidences) / len(confidences)
                    
                    # 计算分布
                    for c in confidences:
                        if c < 0.3:
                            metrics.confidence_distribution["0.0-0.3"] += 1
                        elif c < 0.5:
                            metrics.confidence_distribution["0.3-0.5"] += 1
                        elif c < 0.7:
                            metrics.confidence_distribution["0.5-0.7"] += 1
                        elif c < 0.9:
                            metrics.confidence_distribution["0.7-0.9"] += 1
                        else:
                            metrics.confidence_distribution["0.9-1.0"] += 1
                            
        except Exception as e:
            logger.error(f"Failed to get layer stats: {e}")
        
        return metrics
    
    def get_system_stats(self,
                         since: Optional[datetime] = None,
                         until: Optional[datetime] = None) -> SystemMetrics:
        """获取系统整体统计"""
        if since is None:
            since = datetime.now() - timedelta(hours=24)
        if until is None:
            until = datetime.now()
        
        stats = SystemMetrics(timestamp=until)
        
        # 获取各层统计
        for layer in [1, 2, 3]:
            stats.layer_metrics[layer] = self.get_layer_stats(layer, since, until)
        
        # 汇总
        stats.total_requests = sum(m.total_requests for m in stats.layer_metrics.values())
        total_success = sum(m.success_count for m in stats.layer_metrics.values())
        
        if stats.total_requests > 0:
            stats.success_rate = total_success / stats.total_requests
        
        # 计算平均延迟
        total_latency = sum(m.total_latency_ms for m in stats.layer_metrics.values())
        total_count = sum(m.total_requests for m in stats.layer_metrics.values())
        if total_count > 0:
            stats.avg_latency_ms = total_latency / total_count
        
        # 计算 P95（取各层最大值）
        stats.p95_latency_ms = max(
            (m.p95_latency_ms for m in stats.layer_metrics.values()),
            default=0.0
        )
        
        # 计算平均置信度
        total_confidence = sum(
            m.avg_confidence * m.total_requests 
            for m in stats.layer_metrics.values()
        )
        if total_count > 0:
            stats.avg_confidence = total_confidence / total_count
        
        return stats
    
    def _percentile(self, values: List[float], p: int) -> float:
        """计算百分位数"""
        if not values:
            return 0.0
        sorted_values = sorted(values)
        idx = int(len(sorted_values) * p / 100)
        idx = min(idx, len(sorted_values) - 1)
        return sorted_values[idx]
    
    def export_prometheus(self) -> str:
        """
        导出为 Prometheus 格式
        
        Returns:
            Prometheus 文本格式的指标数据
        """
        stats = self.get_system_stats()
        
        lines = [
            "# HELP adaptive_skill_requests_total Total number of requests",
            "# TYPE adaptive_skill_requests_total counter",
            f"adaptive_skill_requests_total {stats.total_requests}",
            "",
            "# HELP adaptive_skill_success_rate Success rate of requests",
            "# TYPE adaptive_skill_success_rate gauge",
            f"adaptive_skill_success_rate {stats.success_rate:.4f}",
            "",
            "# HELP adaptive_skill_latency_ms Average latency in milliseconds",
            "# TYPE adaptive_skill_latency_ms gauge",
            f"adaptive_skill_latency_ms {stats.avg_latency_ms:.2f}",
            "",
            "# HELP adaptive_skill_confidence Average confidence score",
            "# TYPE adaptive_skill_confidence gauge",
            f"adaptive_skill_confidence {stats.avg_confidence:.4f}",
        ]
        
        # 各层指标
        for layer, m in stats.layer_metrics.items():
            lines.extend([
                "",
                f"# HELP adaptive_skill_layer{layer}_requests_total Layer {layer} total requests",
                f"# TYPE adaptive_skill_layer{layer}_requests_total counter",
                f"adaptive_skill_layer{layer}_requests_total {m.total_requests}",
                "",
                f"# HELP adaptive_skill_layer{layer}_hit_rate Layer {layer} hit rate",
                f"# TYPE adaptive_skill_layer{layer}_hit_rate gauge",
                f"adaptive_skill_layer{layer}_hit_rate {m.hit_rate:.4f}",
                "",
                f"# HELP adaptive_skill_layer{layer}_latency_ms Layer {layer} average latency",
                f"# TYPE adaptive_skill_layer{layer}_latency_ms gauge",
                f"adaptive_skill_layer{layer}_latency_ms {m.avg_latency_ms:.2f}",
            ])
        
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 仪表盘数据生成
# ---------------------------------------------------------------------------

@dataclass
class DashboardData:
    """仪表盘数据结构"""
    
    @staticmethod
    def generate(collector: MetricsCollector,
                 since: Optional[datetime] = None,
                 until: Optional[datetime] = None) -> Dict[str, Any]:
        """
        生成仪表盘数据
        
        Returns:
            可用于前端展示的数据结构
        """
        stats = collector.get_system_stats(since, until)
        
        # 层级分布
        layer_distribution = {
            f"Layer {layer}": m.total_requests
            for layer, m in stats.layer_metrics.items()
        }
        
        # 延迟趋势（简化版，实际应从时序数据中提取）
        latency_trend = [
            {"time": (datetime.now() - timedelta(hours=i)).isoformat(),
             "avg_latency": stats.avg_latency_ms,
             "p95_latency": stats.p95_latency_ms}
            for i in range(24, 0, -1)
        ]
        
        # 置信度分布
        confidence_distribution = {}
        for layer, m in stats.layer_metrics.items():
            for bucket, count in m.confidence_distribution.items():
                key = f"Layer {layer} - {bucket}"
                confidence_distribution[key] = count
        
        return {
            "summary": {
                "total_requests": stats.total_requests,
                "success_rate": f"{stats.success_rate:.1%}",
                "avg_latency_ms": f"{stats.avg_latency_ms:.1f}",
                "avg_confidence": f"{stats.avg_confidence:.1%}",
            },
            "layer_distribution": layer_distribution,
            "layer_metrics": {
                f"Layer {layer}": {
                    "total_requests": m.total_requests,
                    "hit_rate": f"{m.hit_rate:.1%}",
                    "avg_latency_ms": f"{m.avg_latency_ms:.1f}",
                    "p95_latency_ms": f"{m.p95_latency_ms:.1f}",
                    "avg_confidence": f"{m.avg_confidence:.1%}",
                }
                for layer, m in stats.layer_metrics.items()
            },
            "latency_trend": latency_trend,
            "confidence_distribution": confidence_distribution,
            "generated_at": datetime.now().isoformat(),
        }


# ---------------------------------------------------------------------------
# 告警管理
# ---------------------------------------------------------------------------

class AlertManager:
    """
    告警管理器
    
    检测指标异常并发送告警。
    
    Example:
        >>> alert_mgr = AlertManager()
        >>> alert_mgr.add_rule("latency_high", lambda stats: stats.avg_latency_ms > 1000)
        >>> alerts = alert_mgr.check(metrics_collector)
    """
    
    def __init__(self):
        self._rules: Dict[str, Callable[[SystemMetrics], bool]] = {}
        self._callbacks: List[Callable[[str, str], None]] = []
    
    def add_rule(self, name: str, condition: Callable[[SystemMetrics], bool]) -> None:
        """添加告警规则"""
        self._rules[name] = condition
    
    def add_callback(self, callback: Callable[[str, str], None]) -> None:
        """添加告警回调"""
        self._callbacks.append(callback)
    
    def check(self, collector: MetricsCollector) -> List[Dict[str, Any]]:
        """
        检查是否触发告警
        
        Returns:
            触发的告警列表
        """
        stats = collector.get_system_stats()
        alerts = []
        
        for name, condition in self._rules.items():
            try:
                if condition(stats):
                    alert = {
                        "name": name,
                        "timestamp": datetime.now().isoformat(),
                        "summary": stats.to_dict(),
                    }
                    alerts.append(alert)
                    
                    # 触发回调
                    for callback in self._callbacks:
                        try:
                            callback(name, json.dumps(alert))
                        except Exception as e:
                            logger.error(f"Alert callback error: {e}")
            except Exception as e:
                logger.error(f"Alert rule '{name}' error: {e}")
        
        return alerts
    
    def setup_default_rules(self) -> None:
        """设置默认告警规则"""
        self.add_rule(
            "high_failure_rate",
            lambda s: s.success_rate < 0.9 and s.total_requests > 10
        )
        self.add_rule(
            "high_latency",
            lambda s: s.avg_latency_ms > 30000  # 30 秒
        )
        self.add_rule(
            "low_confidence",
            lambda s: s.avg_confidence < 0.5 and s.total_requests > 10
        )
        self.add_rule(
            "layer1_low_hit_rate",
            lambda s: s.layer_metrics.get(1, LayerMetrics(1)).hit_rate < 0.3
            and s.layer_metrics.get(1, LayerMetrics(1)).total_requests > 10
        )
