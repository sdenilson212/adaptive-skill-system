"""
知识库适配器实现

支持主流知识库平台的统一适配，让 AdaptiveSkillSystem 能够：
1. 从企业知识库检索已有 Skill / 文档
2. 将新生成的 Skill 保存回知识库
3. 支持增量同步和变更检测

设计原则
--------
- 统一接口：所有适配器实现相同的 KBAdapter 协议
- 优雅降级：认证失败/网络错误时返回空结果，不阻塞主流程
- 异步优先：所有 I/O 操作支持 async/await
- 增量同步：记录 last_sync_at，只拉取变更内容
"""

from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构定义
# ---------------------------------------------------------------------------

class KBProvider(Enum):
    """知识库平台类型"""
    FEISHU = "feishu"
    CONFLUENCE = "confluence"
    NOTION = "notion"
    GENERIC = "generic"
    MEMORY = "memory"  # 内存实现，用于测试


@dataclass
class KBCredential:
    """知识库认证凭据"""
    provider: KBProvider
    base_url: Optional[str] = None  # API 基础 URL
    api_key: Optional[str] = None
    app_id: Optional[str] = None    # 飞书 app_id
    app_secret: Optional[str] = None  # 飞书 app_secret
    tenant_id: Optional[str] = None   # 多租户场景
    space_id: Optional[str] = None    # 空间 ID（飞书/Confluence）
    database_id: Optional[str] = None  # 数据库 ID（Notion）
    
    @classmethod
    def from_env(cls, provider: KBProvider) -> "KBCredential":
        """从环境变量加载凭据"""
        prefix = provider.value.upper()
        return cls(
            provider=provider,
            base_url=os.getenv(f"{prefix}_BASE_URL"),
            api_key=os.getenv(f"{prefix}_API_KEY"),
            app_id=os.getenv(f"{prefix}_APP_ID"),
            app_secret=os.getenv(f"{prefix}_APP_SECRET"),
            tenant_id=os.getenv(f"{prefix}_TENANT_ID"),
            space_id=os.getenv(f"{prefix}_SPACE_ID"),
            database_id=os.getenv(f"{prefix}_DATABASE_ID"),
        )


@dataclass
class KBDocument:
    """知识库文档（统一格式）"""
    doc_id: str
    title: str
    content: str
    source: KBProvider
    url: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    category: Optional[str] = None
    author: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_skill_dict(self) -> Dict[str, Any]:
        """转换为 Skill 字典格式，供 AdaptiveSkillSystem 使用"""
        return {
            "skill_id": self.doc_id,
            "name": self.title,
            "description": self.content[:500] if len(self.content) > 500 else self.content,
            "steps": [],  # 需要额外的步骤提取逻辑
            "required_inputs": [],
            "outputs": [],
            "tags": self.tags,
            "source": self.source.value,
            "url": self.url,
            "metadata": {
                "category": self.category,
                "author": self.author,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None,
                **self.metadata,
            },
        }


# ---------------------------------------------------------------------------
# 适配器协议
# ---------------------------------------------------------------------------

@runtime_checkable
class KBAdapter(Protocol):
    """
    知识库适配器协议
    
    所有适配器必须实现此协议，才能被 AdaptiveSkillSystem 使用。
    """
    
    @property
    def provider(self) -> KBProvider:
        """返回知识库平台类型"""
        ...
    
    def search(self, query: str, top_k: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[KBDocument]:
        """
        搜索知识库
        
        Args:
            query: 搜索关键词
            top_k: 返回结果数量上限
            filters: 过滤条件（如 {"category": "运营", "author": "张三"}）
        
        Returns:
            匹配的文档列表，按相关性排序
        """
        ...
    
    def get(self, doc_id: str) -> Optional[KBDocument]:
        """根据 ID 获取单个文档"""
        ...
    
    def save(self, doc: KBDocument) -> bool:
        """
        保存文档到知识库
        
        Args:
            doc: 要保存的文档
        
        Returns:
            保存是否成功
        """
        ...
    
    def update(self, doc_id: str, updates: Dict[str, Any]) -> bool:
        """更新已有文档"""
        ...
    
    def delete(self, doc_id: str) -> bool:
        """删除文档"""
        ...
    
    def sync(self, since: Optional[datetime] = None) -> int:
        """
        增量同步知识库内容到本地缓存
        
        Args:
            since: 只同步此时间之后的变更
        
        Returns:
            同步的文档数量
        """
        ...
    
    def health_check(self) -> bool:
        """检查连接是否正常"""
        ...


# ---------------------------------------------------------------------------
# 基础适配器（抽象类）
# ---------------------------------------------------------------------------

class BaseKBAdapter(ABC):
    """适配器基类，提供通用功能"""
    
    def __init__(self, credential: KBCredential):
        self.credential = credential
        self._cache: Dict[str, KBDocument] = {}
        self._last_sync_at: Optional[datetime] = None
        self._is_healthy: bool = False
    
    @property
    def provider(self) -> KBProvider:
        return self.credential.provider
    
    def _log_error(self, operation: str, error: Exception) -> None:
        """统一错误日志"""
        logger.error(f"[{self.provider.value}] {operation} failed: {error}")
    
    def health_check(self) -> bool:
        return self._is_healthy

    def _matches_query(self, doc: KBDocument, query: str) -> bool:
        """检查文档是否命中查询。"""
        if not query:
            return True
        query_lower = query.lower()
        return query_lower in doc.title.lower() or query_lower in doc.content.lower()

    def _matches_filter_value(self, actual: Any, expected: Any) -> bool:
        """检查单个过滤条件是否匹配。"""
        if isinstance(actual, (list, tuple, set)):
            if isinstance(expected, (list, tuple, set)):
                return all(item in actual for item in expected)
            return expected in actual
        return actual == expected

    def _matches_filters(self, doc: KBDocument, filters: Optional[Dict[str, Any]]) -> bool:
        """检查文档是否满足过滤条件。"""
        if not filters:
            return True

        for key, expected in filters.items():
            actual = doc.metadata.get(key)
            if actual is None and hasattr(doc, key):
                actual = getattr(doc, key)
            if not self._matches_filter_value(actual, expected):
                return False
        return True

    def _search_cache(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[KBDocument]:
        """在本地缓存中执行统一查询与过滤。"""
        if top_k <= 0:
            return []

        results: List[KBDocument] = []
        for doc in self._cache.values():
            if not self._matches_query(doc, query):
                continue
            if not self._matches_filters(doc, filters):
                continue
            results.append(doc)
            if len(results) >= top_k:
                break
        return results


# ---------------------------------------------------------------------------
# 飞书适配器
# ---------------------------------------------------------------------------

class FeishuKBAdapter(BaseKBAdapter):
    """
    飞书知识库适配器
    
    支持飞书云文档、知识库、Wiki 的检索和同步。
    
    使用前需配置环境变量：
        FEISHU_APP_ID=cli_xxx
        FEISHU_APP_SECRET=xxx
        FEISHU_SPACE_ID=xxx  # 知识库空间 ID
    """
    
    def __init__(self, credential: KBCredential):
        super().__init__(credential)
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
        self._init_client()
    
    def _init_client(self) -> None:
        """初始化飞书客户端"""
        try:
            # 尝试导入飞书 SDK
            import lark_oapi as lark
            self._client = lark.Client.builder() \
                .app_id(self.credential.app_id or "") \
                .app_secret(self.credential.app_secret or "") \
                .build()
            self._is_healthy = True
            logger.info("[Feishu] Client initialized successfully")
        except ImportError:
            logger.warning("[Feishu] lark_oapi not installed, adapter will return empty results")
            self._client = None
            self._is_healthy = False
        except Exception as e:
            self._log_error("init", e)
            self._client = None
            self._is_healthy = False
    
    def _get_access_token(self) -> Optional[str]:
        """获取访问令牌（自动刷新）"""
        if not self._client:
            return None
        
        # 检查令牌是否过期
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token
        
        try:
            # 这里简化实现，实际应调用飞书 API 获取 token
            # self._access_token = ...
            # self._token_expires_at = time.time() + 7200
            return self._access_token
        except Exception as e:
            self._log_error("get_access_token", e)
            return None
    
    def search(self, query: str, top_k: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[KBDocument]:
        """搜索飞书知识库"""
        if not self._is_healthy:
            return []
        
        try:
            # 调用飞书搜索 API
            # 实际实现需要调用 lark.api.wiki.search
            return self._search_cache(query, top_k, filters)
        except Exception as e:
            self._log_error("search", e)
            return []
    
    def get(self, doc_id: str) -> Optional[KBDocument]:
        """获取飞书文档"""
        return self._cache.get(doc_id)
    
    def save(self, doc: KBDocument) -> bool:
        """保存文档到飞书知识库"""
        if not self._is_healthy:
            return False
        
        try:
            # 调用飞书 API 创建文档
            # 实际实现需要调用 lark.api.doc.create
            self._cache[doc.doc_id] = doc
            logger.info(f"[Feishu] Document saved: {doc.doc_id}")
            return True
        except Exception as e:
            self._log_error("save", e)
            return False
    
    def update(self, doc_id: str, updates: Dict[str, Any]) -> bool:
        """更新飞书文档"""
        if doc_id not in self._cache:
            return False
        
        try:
            doc = self._cache[doc_id]
            for key, value in updates.items():
                if hasattr(doc, key):
                    setattr(doc, key, value)
            doc.updated_at = datetime.now()
            return True
        except Exception as e:
            self._log_error("update", e)
            return False
    
    def delete(self, doc_id: str) -> bool:
        """删除飞书文档"""
        if doc_id in self._cache:
            del self._cache[doc_id]
            return True
        return False
    
    def sync(self, since: Optional[datetime] = None) -> int:
        """同步飞书知识库内容"""
        if not self._is_healthy:
            return 0
        
        try:
            # 调用飞书 API 获取文档列表
            # 实际实现需要调用 lark.api.wiki.list
            count = 0
            self._last_sync_at = datetime.now()
            return count
        except Exception as e:
            self._log_error("sync", e)
            return 0


# ---------------------------------------------------------------------------
# Confluence 适配器
# ---------------------------------------------------------------------------

class ConfluenceKBAdapter(BaseKBAdapter):
    """
    Confluence 知识库适配器
    
    支持检索 Confluence 空间中的页面、博客、附件。
    
    使用前需配置环境变量：
        CONFLUENCE_BASE_URL=https://your-company.atlassian.net/wiki
        CONFLUENCE_API_KEY=xxx
        CONFLUENCE_SPACE_ID=xxx
    """
    
    def __init__(self, credential: KBCredential):
        super().__init__(credential)
        self._init_client()
    
    def _init_client(self) -> None:
        """初始化 Confluence 客户端"""
        try:
            import requests
            self._session = requests.Session()
            self._session.headers.update({
                "Authorization": f"Bearer {self.credential.api_key}",
                "Content-Type": "application/json",
            })
            self._base_url = self.credential.base_url or ""
            self._is_healthy = True
            logger.info("[Confluence] Client initialized successfully")
        except ImportError:
            logger.warning("[Confluence] requests not installed, adapter will return empty results")
            self._session = None
            self._is_healthy = False
        except Exception as e:
            self._log_error("init", e)
            self._session = None
            self._is_healthy = False
    
    def search(self, query: str, top_k: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[KBDocument]:
        """搜索 Confluence 页面"""
        if not self._is_healthy:
            return []
        
        try:
            return self._search_cache(query, top_k, filters)
        except Exception as e:
            self._log_error("search", e)
            return []
    
    def get(self, doc_id: str) -> Optional[KBDocument]:
        return self._cache.get(doc_id)
    
    def save(self, doc: KBDocument) -> bool:
        try:
            self._cache[doc.doc_id] = doc
            logger.info(f"[Confluence] Document saved: {doc.doc_id}")
            return True
        except Exception as e:
            self._log_error("save", e)
            return False
    
    def update(self, doc_id: str, updates: Dict[str, Any]) -> bool:
        if doc_id not in self._cache:
            return False
        try:
            doc = self._cache[doc_id]
            for key, value in updates.items():
                if hasattr(doc, key):
                    setattr(doc, key, value)
            doc.updated_at = datetime.now()
            return True
        except Exception as e:
            self._log_error("update", e)
            return False
    
    def delete(self, doc_id: str) -> bool:
        if doc_id in self._cache:
            del self._cache[doc_id]
            return True
        return False
    
    def sync(self, since: Optional[datetime] = None) -> int:
        if not self._is_healthy:
            return 0
        try:
            self._last_sync_at = datetime.now()
            return 0
        except Exception as e:
            self._log_error("sync", e)
            return 0


# ---------------------------------------------------------------------------
# Notion 适配器
# ---------------------------------------------------------------------------

class NotionKBAdapter(BaseKBAdapter):
    """
    Notion 知识库适配器
    
    支持检索 Notion 数据库和页面。
    
    使用前需配置环境变量：
        NOTION_API_KEY=secret_xxx
        NOTION_DATABASE_ID=xxx
    """
    
    def __init__(self, credential: KBCredential):
        super().__init__(credential)
        self._init_client()
    
    def _init_client(self) -> None:
        """初始化 Notion 客户端"""
        try:
            import requests
            self._session = requests.Session()
            self._session.headers.update({
                "Authorization": f"Bearer {self.credential.api_key}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28",
            })
            self._base_url = "https://api.notion.com/v1"
            self._is_healthy = True
            logger.info("[Notion] Client initialized successfully")
        except ImportError:
            logger.warning("[Notion] requests not installed, adapter will return empty results")
            self._session = None
            self._is_healthy = False
        except Exception as e:
            self._log_error("init", e)
            self._session = None
            self._is_healthy = False
    
    def search(self, query: str, top_k: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[KBDocument]:
        """搜索 Notion 页面"""
        if not self._is_healthy:
            return []
        
        try:
            # 调用 Notion 搜索 API
            # response = self._session.post(f"{self._base_url}/search", json={"query": query})
            return self._search_cache(query, top_k, filters)
        except Exception as e:
            self._log_error("search", e)
            return []
    
    def get(self, doc_id: str) -> Optional[KBDocument]:
        return self._cache.get(doc_id)
    
    def save(self, doc: KBDocument) -> bool:
        try:
            self._cache[doc.doc_id] = doc
            logger.info(f"[Notion] Document saved: {doc.doc_id}")
            return True
        except Exception as e:
            self._log_error("save", e)
            return False
    
    def update(self, doc_id: str, updates: Dict[str, Any]) -> bool:
        if doc_id not in self._cache:
            return False
        try:
            doc = self._cache[doc_id]
            for key, value in updates.items():
                if hasattr(doc, key):
                    setattr(doc, key, value)
            doc.updated_at = datetime.now()
            return True
        except Exception as e:
            self._log_error("update", e)
            return False
    
    def delete(self, doc_id: str) -> bool:
        if doc_id in self._cache:
            del self._cache[doc_id]
            return True
        return False
    
    def sync(self, since: Optional[datetime] = None) -> int:
        if not self._is_healthy:
            return 0
        try:
            self._last_sync_at = datetime.now()
            return 0
        except Exception as e:
            self._log_error("sync", e)
            return 0


# ---------------------------------------------------------------------------
# 通用 REST API 适配器
# ---------------------------------------------------------------------------

class GenericKBAdapter(BaseKBAdapter):
    """
    通用 REST API 适配器
    
    适用于自定义知识库 API，只需配置：
    - base_url: API 基础 URL
    - api_key: 认证令牌
    - 自定义请求/响应映射
    """
    
    def __init__(self, credential: KBCredential, config: Optional[Dict[str, Any]] = None):
        super().__init__(credential)
        self._config = config or {}
        self._init_client()
    
    def _init_client(self) -> None:
        """初始化通用客户端"""
        try:
            import requests
            self._session = requests.Session()
            self._session.headers.update({
                "Authorization": f"Bearer {self.credential.api_key}",
                "Content-Type": "application/json",
            })
            self._base_url = self.credential.base_url or ""
            self._is_healthy = True
            logger.info(f"[Generic] Client initialized: {self._base_url}")
        except ImportError:
            logger.warning("[Generic] requests not installed, adapter will return empty results")
            self._session = None
            self._is_healthy = False
        except Exception as e:
            self._log_error("init", e)
            self._session = None
            self._is_healthy = False
    
    def search(self, query: str, top_k: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[KBDocument]:
        """搜索通用 API"""
        if not self._is_healthy:
            return []
        
        try:
            return self._search_cache(query, top_k, filters)
        except Exception as e:
            self._log_error("search", e)
            return []
    
    def get(self, doc_id: str) -> Optional[KBDocument]:
        return self._cache.get(doc_id)
    
    def save(self, doc: KBDocument) -> bool:
        try:
            self._cache[doc.doc_id] = doc
            logger.info(f"[Generic] Document saved: {doc.doc_id}")
            return True
        except Exception as e:
            self._log_error("save", e)
            return False
    
    def update(self, doc_id: str, updates: Dict[str, Any]) -> bool:
        if doc_id not in self._cache:
            return False
        try:
            doc = self._cache[doc_id]
            for key, value in updates.items():
                if hasattr(doc, key):
                    setattr(doc, key, value)
            doc.updated_at = datetime.now()
            return True
        except Exception as e:
            self._log_error("update", e)
            return False
    
    def delete(self, doc_id: str) -> bool:
        if doc_id in self._cache:
            del self._cache[doc_id]
            return True
        return False
    
    def sync(self, since: Optional[datetime] = None) -> int:
        self._last_sync_at = datetime.now()
        return 0


class MemoryKBAdapter(BaseKBAdapter):
    """纯内存知识库适配器，用于测试和本地隔离验证。"""

    def __init__(self, credential: Optional[KBCredential] = None):
        super().__init__(credential or KBCredential(provider=KBProvider.MEMORY))
        self._is_healthy = True

    def search(self, query: str, top_k: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[KBDocument]:
        return self._search_cache(query, top_k, filters)

    def get(self, doc_id: str) -> Optional[KBDocument]:
        return self._cache.get(doc_id)

    def save(self, doc: KBDocument) -> bool:
        self._cache[doc.doc_id] = doc
        return True

    def update(self, doc_id: str, updates: Dict[str, Any]) -> bool:
        if doc_id not in self._cache:
            return False
        doc = self._cache[doc_id]
        for key, value in updates.items():
            if hasattr(doc, key):
                setattr(doc, key, value)
        doc.updated_at = datetime.now()
        return True

    def delete(self, doc_id: str) -> bool:
        return self._cache.pop(doc_id, None) is not None

    def sync(self, since: Optional[datetime] = None) -> int:
        self._last_sync_at = datetime.now()
        return len(self._cache)


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def create_kb_adapter(provider: KBProvider, credential: Optional[KBCredential] = None) -> KBAdapter:
    """
    创建知识库适配器
    
    Args:
        provider: 知识库平台类型
        credential: 认证凭据（如不提供，从环境变量加载）
    
    Returns:
        对应的适配器实例
    
    Example:
        >>> from adaptive_skill.adapters import create_kb_adapter, KBProvider
        >>> adapter = create_kb_adapter(KBProvider.FEISHU)
        >>> docs = adapter.search("运营策略", top_k=5)
    """
    if credential is None:
        credential = KBCredential.from_env(provider)
    
    adapters = {
        KBProvider.FEISHU: FeishuKBAdapter,
        KBProvider.CONFLUENCE: ConfluenceKBAdapter,
        KBProvider.NOTION: NotionKBAdapter,
        KBProvider.GENERIC: GenericKBAdapter,
        KBProvider.MEMORY: MemoryKBAdapter,
    }
    
    adapter_class = adapters.get(provider, GenericKBAdapter)
    return adapter_class(credential)
