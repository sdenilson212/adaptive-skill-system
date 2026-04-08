"""
知识库适配器模块

提供对接主流知识库平台的适配器：
- FeishuKBAdapter: 飞书知识库
- ConfluenceKBAdapter: Confluence
- NotionKBAdapter: Notion
- GenericKBAdapter: 通用 REST API 适配器
- MemoryKBAdapter: 纯内存适配器（测试 / 本地隔离验证）
"""

from .kb_adapters import (
    KBAdapter,
    FeishuKBAdapter,
    ConfluenceKBAdapter,
    NotionKBAdapter,
    GenericKBAdapter,
    MemoryKBAdapter,
    KBDocument,
    KBCredential,
    KBProvider,
    create_kb_adapter,
)

__all__ = [
    "KBAdapter",
    "FeishuKBAdapter",
    "ConfluenceKBAdapter",
    "NotionKBAdapter",
    "GenericKBAdapter",
    "MemoryKBAdapter",
    "KBDocument",
    "KBCredential",
    "KBProvider",
    "create_kb_adapter",
]
