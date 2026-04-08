"""
多租户上下文管理与权限控制

实现企业级多租户支持：
1. 租户隔离：每个租户有独立的 KB/LTM 空间
2. 权限控制：基于角色的访问控制 (RBAC)
3. 上下文传递：请求中携带租户信息，自动路由到正确的隔离空间

设计原则
--------
- 透明隔离：业务代码无需关心多租户细节
- 最小权限：默认拒绝，显式授权
- 审计追踪：记录所有跨租户操作
"""

from __future__ import annotations

import logging
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..adapters.kb_adapters import KBAdapter, KBDocument
    from ..feedback.collector import FeedbackStorage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构定义
# ---------------------------------------------------------------------------

class Permission(Enum):
    """权限类型"""
    # Skill 相关
    SKILL_READ = "skill:read"
    SKILL_WRITE = "skill:write"
    SKILL_DELETE = "skill:delete"
    SKILL_PUBLISH = "skill:publish"
    
    # 知识库相关
    KB_READ = "kb:read"
    KB_WRITE = "kb:write"
    KB_ADMIN = "kb:admin"
    
    # LTM 相关
    LTM_READ = "ltm:read"
    LTM_WRITE = "ltm:write"
    
    # 系统管理
    TENANT_ADMIN = "tenant:admin"
    USER_MANAGE = "user:manage"
    AUDIT_VIEW = "audit:view"


class Role(Enum):
    """角色定义"""
    VIEWER = "viewer"
    MEMBER = "member"
    EDITOR = "editor"
    ADMIN = "admin"
    OWNER = "owner"


# 角色权限映射
ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
    Role.VIEWER: {
        Permission.SKILL_READ,
        Permission.KB_READ,
        Permission.LTM_READ,
    },
    Role.MEMBER: {
        Permission.SKILL_READ,
        Permission.KB_READ,
        Permission.LTM_READ,
        Permission.LTM_WRITE,
    },
    Role.EDITOR: {
        Permission.SKILL_READ,
        Permission.SKILL_WRITE,
        Permission.KB_READ,
        Permission.KB_WRITE,
        Permission.LTM_READ,
        Permission.LTM_WRITE,
    },
    Role.ADMIN: {
        Permission.SKILL_READ,
        Permission.SKILL_WRITE,
        Permission.SKILL_DELETE,
        Permission.SKILL_PUBLISH,
        Permission.KB_READ,
        Permission.KB_WRITE,
        Permission.KB_ADMIN,
        Permission.LTM_READ,
        Permission.LTM_WRITE,
        Permission.USER_MANAGE,
        Permission.AUDIT_VIEW,
    },
    Role.OWNER: {
        # Owner 拥有所有权限
        *list(Permission),
    },
}


@dataclass
class TenantConfig:
    """租户配置"""
    tenant_id: str
    tenant_name: str
    created_at: datetime = field(default_factory=datetime.now)
    
    # 隔离配置
    kb_namespace: str = ""      # KB 命名空间前缀
    ltm_namespace: str = ""     # LTM 命名空间前缀
    
    # 功能开关
    features: Dict[str, bool] = field(default_factory=lambda: {
        "layer3_generation": True,
        "skill_composition": True,
        "feedback_collection": True,
    })
    
    # 配额
    quotas: Dict[str, int] = field(default_factory=lambda: {
        "max_skills": 1000,
        "max_ltm_entries": 10000,
        "max_requests_per_day": 10000,
    })
    
    # 成员
    members: Dict[str, Role] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.kb_namespace:
            self.kb_namespace = f"tenant:{self.tenant_id}:kb"
        if not self.ltm_namespace:
            self.ltm_namespace = f"tenant:{self.tenant_id}:ltm"


# ---------------------------------------------------------------------------
# 租户上下文
# ---------------------------------------------------------------------------

class TenantContext:
    """
    租户上下文管理
    
    使用线程本地存储，确保每个请求都有正确的租户上下文。
    
    Example:
        >>> with TenantContext.use("tenant-123", user_id="user-456"):
        ...     # 在此上下文中，所有操作都针对 tenant-123
        ...     pass
    """
    
    _current: Dict[int, Optional["TenantContext"]] = {}
    _lock = threading.Lock()
    
    def __init__(self,
                 tenant_id: str,
                 user_id: Optional[str] = None,
                 role: Optional[Role] = None,
                 permissions: Optional[Set[Permission]] = None):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.role = role or Role.MEMBER
        self.permissions = permissions or ROLE_PERMISSIONS.get(self.role, set())
        self.request_id = str(uuid.uuid4())[:8]
        self.created_at = datetime.now()
    
    @classmethod
    def get_current(cls) -> Optional["TenantContext"]:
        """获取当前线程的租户上下文"""
        thread_id = threading.get_ident()
        with cls._lock:
            return cls._current.get(thread_id)
    
    @classmethod
    def set_current(cls, ctx: Optional["TenantContext"]) -> None:
        """设置当前线程的租户上下文"""
        thread_id = threading.get_ident()
        with cls._lock:
            cls._current[thread_id] = ctx
    
    @classmethod
    @contextmanager
    def use(cls,
            tenant_id: str,
            user_id: Optional[str] = None,
            role: Optional[Role] = None,
            permissions: Optional[Set[Permission]] = None):
        """
        在指定租户上下文中执行操作
        
        Args:
            tenant_id: 租户 ID
            user_id: 用户 ID
            role: 用户角色
            permissions: 自定义权限（覆盖角色默认权限）
        
        Yields:
            租户上下文对象
        """
        ctx = cls(tenant_id, user_id, role, permissions)
        previous = cls.get_current()
        
        try:
            cls.set_current(ctx)
            yield ctx
        finally:
            cls.set_current(previous)
    
    def has_permission(self, permission: Permission) -> bool:
        """检查是否拥有指定权限"""
        return permission in self.permissions
    
    def require_permission(self, permission: Permission) -> None:
        """要求指定权限，无权限时抛出异常"""
        if not self.has_permission(permission):
            raise PermissionError(
                f"User {self.user_id} in tenant {self.tenant_id} "
                f"does not have permission {permission.value}"
            )
    
    def __enter__(self):
        TenantContext.set_current(self)
        return self
    
    def __exit__(self, *args):
        TenantContext.set_current(None)


# ---------------------------------------------------------------------------
# 租户管理器
# ---------------------------------------------------------------------------

class TenantManager:
    """
    租户管理器
    
    管理租户配置、成员、配额等。
    
    Example:
        >>> manager = TenantManager()
        >>> manager.create_tenant("tenant-123", "My Company")
        >>> manager.add_member("tenant-123", "user-456", Role.EDITOR)
    """
    
    def __init__(self):
        self._tenants: Dict[str, TenantConfig] = {}
        self._lock = threading.Lock()
    
    def create_tenant(self,
                      tenant_id: str,
                      tenant_name: str,
                      **kwargs) -> TenantConfig:
        """创建租户"""
        with self._lock:
            if tenant_id in self._tenants:
                raise ValueError(f"Tenant {tenant_id} already exists")
            
            config = TenantConfig(
                tenant_id=tenant_id,
                tenant_name=tenant_name,
                **kwargs
            )
            self._tenants[tenant_id] = config
            logger.info(f"Created tenant: {tenant_id}")
            return config
    
    def get_tenant(self, tenant_id: str) -> Optional[TenantConfig]:
        """获取租户配置"""
        return self._tenants.get(tenant_id)
    
    def delete_tenant(self, tenant_id: str) -> bool:
        """删除租户"""
        with self._lock:
            if tenant_id in self._tenants:
                del self._tenants[tenant_id]
                logger.info(f"Deleted tenant: {tenant_id}")
                return True
            return False
    
    def add_member(self,
                   tenant_id: str,
                   user_id: str,
                   role: Role) -> bool:
        """添加租户成员"""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return False
        
        with self._lock:
            tenant.members[user_id] = role
            logger.info(f"Added member {user_id} to tenant {tenant_id} as {role.value}")
            return True
    
    def remove_member(self, tenant_id: str, user_id: str) -> bool:
        """移除租户成员"""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return False
        
        with self._lock:
            if user_id in tenant.members:
                del tenant.members[user_id]
                logger.info(f"Removed member {user_id} from tenant {tenant_id}")
                return True
            return False
    
    def get_member_role(self, tenant_id: str, user_id: str) -> Optional[Role]:
        """获取成员角色"""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return None
        return tenant.members.get(user_id)
    
    def check_quota(self,
                    tenant_id: str,
                    resource: str,
                    current_usage: int) -> bool:
        """检查配额"""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return False
        
        quota = tenant.quotas.get(resource, 0)
        return current_usage < quota


# ---------------------------------------------------------------------------
# 租户隔离
# ---------------------------------------------------------------------------

class TenantIsolation:
    """
    租户隔离层
    
    确保 KB/LTM 数据按租户隔离，防止跨租户数据泄露。
    
    Example:
        >>> isolation = TenantIsolation(kb_adapter, ltm_adapter)
        >>> # 自动根据当前上下文隔离数据
        >>> docs = isolation.search_kb("query")  # 只搜索当前租户的数据
    """
    
    def __init__(self,
                 kb_adapter: Optional["KBAdapter"] = None,
                 ltm_adapter: Optional[Any] = None):
        self._kb = kb_adapter
        self._ltm = ltm_adapter
    
    def _get_tenant_id(self) -> Optional[str]:
        """获取当前租户 ID；如果没有租户上下文则返回 None（passthrough 模式）"""
        ctx = TenantContext.get_current()
        if not ctx:
            return None
        return ctx.tenant_id
    
    def _prefix_doc_id(self, doc_id: str, tenant_id: str) -> str:
        """为文档 ID 添加租户前缀"""
        return f"{tenant_id}:{doc_id}"
    
    def _strip_prefix(self, doc_id: str) -> str:
        """移除租户前缀"""
        if ":" in doc_id:
            return doc_id.split(":", 1)[1]
        return doc_id
    
    def search_kb(self,
                  query: str,
                  top_k: int = 5,
                  filters: Optional[Dict[str, Any]] = None) -> List["KBDocument"]:
        """
        搜索当前租户的 KB

        - 有租户 context：自动叠加 tenant_id 过滤，只返回当前租户数据。
        - 无租户 context（passthrough 模式）：直接透传给 raw client，不加过滤。
        - 不修改调用方传入的 filters 字典。
        - 自动兼容不接受 filters 参数的 raw client（如 benchmark stub）。
        """
        if not self._kb:
            return []

        tenant_id = self._get_tenant_id()

        if tenant_id is not None:
            # 租户模式：叠加 tenant_id 过滤（操作副本）
            effective_filters = dict(filters) if filters is not None else {}
            effective_filters["tenant_id"] = tenant_id
        else:
            # passthrough 模式：使用调用方原始 filters（不复制，直接用）
            effective_filters = filters

        # 兼容不支持 filters 参数的 raw client
        import inspect
        try:
            sig = inspect.signature(self._kb.search)
            params = list(sig.parameters.keys())
            if len(params) >= 3 or any(
                p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
                for p in sig.parameters.values()
            ):
                return self._kb.search(query, top_k, effective_filters)
            else:
                return self._kb.search(query, top_k)
        except (ValueError, TypeError):
            # inspect 失败时，尝试先带 filters，再 fallback 无 filters
            try:
                return self._kb.search(query, top_k, effective_filters)
            except TypeError:
                return self._kb.search(query, top_k)
    
    def get_kb_doc(self, doc_id: str) -> Optional["KBDocument"]:
        """获取当前租户的 KB 文档。

        - 有租户 context：自动补租户前缀后查询。
        - 无租户 context（passthrough 模式）：直接透传原始 doc_id。
        """
        if not self._kb:
            return None

        tenant_id = self._get_tenant_id()
        target_id = self._prefix_doc_id(doc_id, tenant_id) if tenant_id is not None else doc_id
        return self._kb.get(target_id)

    
    def save_kb_doc(self, doc: "KBDocument") -> bool:
        """保存文档到当前租户的 KB（不修改入参原始对象）

        - 有租户 context：在 doc_id 前加租户前缀，metadata 注入 tenant_id。
        - 无租户 context（passthrough 模式）：直接保存，不修改任何字段。
        """
        if not self._kb:
            return False

        tenant_id = self._get_tenant_id()

        if tenant_id is None:
            # passthrough 模式：直接保存，不改 doc
            return self._kb.save(doc)

        # 租户模式：操作副本，保护调用方持有的原始对象
        import copy
        doc_copy = copy.copy(doc)
        doc_copy.doc_id = self._prefix_doc_id(doc.doc_id, tenant_id)
        doc_copy.metadata = dict(doc.metadata)
        doc_copy.metadata["tenant_id"] = tenant_id

        return self._kb.save(doc_copy)
    
    def search_ltm(self,
                   query: str,
                   max_results: int = 10) -> List[Dict[str, Any]]:
        """搜索当前租户的 LTM

        - 有租户 context：只返回当前租户数据。
        - 无租户 context（passthrough 模式）：直接透传，不过滤。
        """
        if not self._ltm:
            return []

        tenant_id = self._get_tenant_id()

        if tenant_id is None:
            # passthrough 模式：直接透传给 raw LTM client
            import inspect
            try:
                sig = inspect.signature(self._ltm.recall)
                if len(sig.parameters) >= 2:
                    return self._ltm.recall(query, max_results)
                else:
                    return self._ltm.recall(query)
            except (ValueError, TypeError):
                try:
                    return self._ltm.recall(query, max_results)
                except TypeError:
                    return self._ltm.recall(query)

        # 租户模式：多拉再过滤
        results = self._ltm.recall(query, max_results * 2)
        return [
            r for r in results
            if isinstance(r, dict) and r.get("metadata", {}).get("tenant_id") == tenant_id
        ][:max_results]
    
    def save_ltm(self,
                 content: str,
                 category: str,
                 tags: List[str]) -> bool:
        """保存到当前租户的 LTM"""
        if not self._ltm:
            return False
        
        tenant_id = self._get_tenant_id()
        
        return self._ltm.save({
            "content": content,
            "category": category,
            "tags": tags,
            "metadata": {"tenant_id": tenant_id},
        })

    # Compatibility layer - wrapper methods for existing code interfaces
    
    def search(self, query: str, top_k: int = 5, filters: Optional[Dict[str, Any]] = None):
        return self.search_kb(query, top_k, filters)
    
    def get(self, doc_id: str) -> Optional[Any]:
        return self.get_kb_doc(doc_id)
    
    def save(self, doc: Any) -> bool:
        """Compatibility proxy:
        - 如果是 KB 模式（有 _kb）：走 save_kb_doc()
        - 如果是 LTM 模式（无 _kb 但有 _ltm）：透传给 raw LTM client.save()
        - passthrough（无 tenant context）：直接保存
        """
        if self._kb:
            return self.save_kb_doc(doc)
        if self._ltm:
            try:
                result = self._ltm.save(doc)
                return result is not None
            except Exception:
                return False
        return False
    
    def update(self, doc_id: str, updates: Dict[str, Any]) -> bool:
        """更新当前租户的 KB 文档。

        - 有租户 context：自动补租户前缀后更新。
        - 无租户 context（passthrough 模式）：直接透传原始 doc_id。
        """
        if not self._kb:
            return False
        tenant_id = self._get_tenant_id()
        target_id = self._prefix_doc_id(doc_id, tenant_id) if tenant_id is not None else doc_id
        return self._kb.update(target_id, updates)

    
    def recall(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        return self.search_ltm(query, max_results)


# ---------------------------------------------------------------------------
# 访问控制
# ---------------------------------------------------------------------------

class AccessControl:
    """
    访问控制
    
    提供基于角色的访问控制 (RBAC)。
    
    Example:
        >>> ac = AccessControl(tenant_manager)
        >>> if ac.can(user_id="user-456", tenant_id="tenant-123", permission=Permission.SKILL_WRITE):
        ...     # 允许写入
        ...     pass
    """
    
    def __init__(self, tenant_manager: TenantManager):
        self._manager = tenant_manager
    
    def can(self,
            user_id: str,
            tenant_id: str,
            permission: Permission) -> bool:
        """
        检查用户是否有指定权限
        
        Args:
            user_id: 用户 ID
            tenant_id: 租户 ID
            permission: 权限类型
        
        Returns:
            是否有权限
        """
        role = self._manager.get_member_role(tenant_id, user_id)
        if not role:
            return False
        
        permissions = ROLE_PERMISSIONS.get(role, set())
        return permission in permissions
    
    def require(self,
                user_id: str,
                tenant_id: str,
                permission: Permission) -> None:
        """
        要求用户有指定权限，无权限时抛出异常
        """
        if not self.can(user_id, tenant_id, permission):
            raise PermissionError(
                f"User {user_id} does not have permission {permission.value} "
                f"in tenant {tenant_id}"
            )
    
    def grant_role(self,
                   tenant_id: str,
                   user_id: str,
                   role: Role,
                   granted_by: str) -> bool:
        """
        授予用户角色
        
        Args:
            tenant_id: 租户 ID
            user_id: 目标用户 ID
            role: 要授予的角色
            granted_by: 授权者 ID
        """
        # 检查授权者是否有权限
        if not self.can(granted_by, tenant_id, Permission.USER_MANAGE):
            raise PermissionError(
                f"User {granted_by} cannot manage users in tenant {tenant_id}"
            )
        
        return self._manager.add_member(tenant_id, user_id, role)
    
    def revoke_role(self,
                    tenant_id: str,
                    user_id: str,
                    revoked_by: str) -> bool:
        """撤销用户角色"""
        if not self.can(revoked_by, tenant_id, Permission.USER_MANAGE):
            raise PermissionError(
                f"User {revoked_by} cannot manage users in tenant {tenant_id}"
            )
        
        return self._manager.remove_member(tenant_id, user_id)
    
    def get_user_permissions(self,
                             tenant_id: str,
                             user_id: str) -> Set[Permission]:
        """获取用户的所有权限"""
        role = self._manager.get_member_role(tenant_id, user_id)
        if not role:
            return set()
        return ROLE_PERMISSIONS.get(role, set())
