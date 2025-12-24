"""
缓存工具模块
提供SQLite和文件缓存支持，实现TTL过期机制
"""

import os
import json
import sqlite3
import time
import logging
from typing import Any, Optional, Dict
from pathlib import Path

from core.contracts import CacheEntry
from config.config_loader import get_config_value

logger = logging.getLogger(__name__)


class CacheBackend:
    """缓存后端抽象基类"""
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        raise NotImplementedError
    
    def set(self, key: str, value: Any, ttl: int) -> bool:
        """设置缓存值"""
        raise NotImplementedError
    
    def delete(self, key: str) -> bool:
        """删除缓存值"""
        raise NotImplementedError
    
    def clear(self) -> bool:
        """清空所有缓存"""
        raise NotImplementedError
    
    def cleanup_expired(self) -> int:
        """清理过期缓存，返回清理数量"""
        raise NotImplementedError


class SQLiteCacheBackend(CacheBackend):
    """SQLite缓存后端"""
    
    def __init__(self, db_path: str, max_entries: int = 10000):
        """
        初始化SQLite缓存
        
        Args:
            db_path: 数据库文件路径
            max_entries: 最大缓存条目数
        """
        self.db_path = db_path
        self.max_entries = max_entries
        
        # 确保目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化数据库
        self._init_db()
        
        logger.info(f"SQLite缓存初始化完成: {db_path}")
    
    def _init_db(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    ttl INTEGER NOT NULL
                )
            """)
            
            # 创建索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON cache(timestamp)")
            conn.commit()
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT value, timestamp, ttl FROM cache WHERE key = ?",
                    (key,)
                )
                row = cursor.fetchone()
                
                if not row:
                    return None
                
                value_json, timestamp, ttl = row
                
                # 检查是否过期
                if time.time() - timestamp > ttl:
                    # 删除过期缓存
                    conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                    conn.commit()
                    logger.debug(f"缓存过期已删除: {key}")
                    return None
                
                # 反序列化值
                value = json.loads(value_json)
                logger.debug(f"缓存命中: {key}")
                return value
                
        except Exception as e:
            logger.error(f"获取缓存失败: {key}, 错误: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: int) -> bool:
        """设置缓存值"""
        try:
            # 序列化值
            value_json = json.dumps(value, ensure_ascii=False)
            timestamp = time.time()
            
            with sqlite3.connect(self.db_path) as conn:
                # 插入或更新缓存
                conn.execute(
                    "INSERT OR REPLACE INTO cache (key, value, timestamp, ttl) VALUES (?, ?, ?, ?)",
                    (key, value_json, timestamp, ttl)
                )
                
                # 检查缓存条目数量，如果超过限制则清理旧条目
                cursor = conn.execute("SELECT COUNT(*) FROM cache")
                count = cursor.fetchone()[0]
                
                if count > self.max_entries:
                    # 删除最旧的条目
                    delete_count = count - self.max_entries + 100  # 多删除一些，减少频繁清理
                    conn.execute(
                        "DELETE FROM cache WHERE key IN (SELECT key FROM cache ORDER BY timestamp LIMIT ?)",
                        (delete_count,)
                    )
                    logger.debug(f"清理了 {delete_count} 个旧缓存条目")
                
                conn.commit()
                logger.debug(f"缓存已设置: {key} (TTL: {ttl}s)")
                return True
                
        except Exception as e:
            logger.error(f"设置缓存失败: {key}, 错误: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """删除缓存值"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                conn.commit()
                deleted = cursor.rowcount > 0
                if deleted:
                    logger.debug(f"缓存已删除: {key}")
                return deleted
                
        except Exception as e:
            logger.error(f"删除缓存失败: {key}, 错误: {e}")
            return False
    
    def clear(self) -> bool:
        """清空所有缓存"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM cache")
                conn.commit()
                logger.info("所有缓存已清空")
                return True
                
        except Exception as e:
            logger.error(f"清空缓存失败: {e}")
            return False
    
    def cleanup_expired(self) -> int:
        """清理过期缓存"""
        try:
            current_time = time.time()
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "DELETE FROM cache WHERE ? - timestamp > ttl",
                    (current_time,)
                )
                conn.commit()
                deleted_count = cursor.rowcount
                
                if deleted_count > 0:
                    logger.info(f"清理了 {deleted_count} 个过期缓存条目")
                
                return deleted_count
                
        except Exception as e:
            logger.error(f"清理过期缓存失败: {e}")
            return 0
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # 总条目数
                cursor = conn.execute("SELECT COUNT(*) FROM cache")
                total_count = cursor.fetchone()[0]
                
                # 过期条目数
                current_time = time.time()
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM cache WHERE ? - timestamp > ttl",
                    (current_time,)
                )
                expired_count = cursor.fetchone()[0]
                
                # 数据库大小
                db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
                
                return {
                    "total_entries": total_count,
                    "expired_entries": expired_count,
                    "valid_entries": total_count - expired_count,
                    "db_size_bytes": db_size,
                    "db_size_mb": db_size / (1024 * 1024),
                    "max_entries": self.max_entries
                }
                
        except Exception as e:
            logger.error(f"获取缓存统计失败: {e}")
            return {}


class FileCacheBackend(CacheBackend):
    """文件缓存后端（简单实现）"""
    
    def __init__(self, cache_dir: str, max_entries: int = 10000):
        """
        初始化文件缓存
        
        Args:
            cache_dir: 缓存目录
            max_entries: 最大缓存条目数
        """
        self.cache_dir = Path(cache_dir)
        self.max_entries = max_entries
        
        # 确保目录存在
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"文件缓存初始化完成: {cache_dir}")
    
    def _get_cache_file(self, key: str) -> Path:
        """获取缓存文件路径"""
        # 使用key的hash作为文件名，避免特殊字符问题
        import hashlib
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{key_hash}.json"
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        cache_file = self._get_cache_file(key)
        
        try:
            if not cache_file.exists():
                return None
            
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # 检查是否过期
            if time.time() - cache_data['timestamp'] > cache_data['ttl']:
                cache_file.unlink()  # 删除过期文件
                logger.debug(f"缓存过期已删除: {key}")
                return None
            
            logger.debug(f"缓存命中: {key}")
            return cache_data['value']
            
        except Exception as e:
            logger.error(f"获取缓存失败: {key}, 错误: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: int) -> bool:
        """设置缓存值"""
        cache_file = self._get_cache_file(key)
        
        try:
            cache_data = {
                'key': key,
                'value': value,
                'timestamp': time.time(),
                'ttl': ttl
            }
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"缓存已设置: {key} (TTL: {ttl}s)")
            return True
            
        except Exception as e:
            logger.error(f"设置缓存失败: {key}, 错误: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """删除缓存值"""
        cache_file = self._get_cache_file(key)
        
        try:
            if cache_file.exists():
                cache_file.unlink()
                logger.debug(f"缓存已删除: {key}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"删除缓存失败: {key}, 错误: {e}")
            return False
    
    def clear(self) -> bool:
        """清空所有缓存"""
        try:
            for cache_file in self.cache_dir.glob("*.json"):
                cache_file.unlink()
            logger.info("所有缓存已清空")
            return True
            
        except Exception as e:
            logger.error(f"清空缓存失败: {e}")
            return False
    
    def cleanup_expired(self) -> int:
        """清理过期缓存"""
        deleted_count = 0
        current_time = time.time()
        
        try:
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                    
                    if current_time - cache_data['timestamp'] > cache_data['ttl']:
                        cache_file.unlink()
                        deleted_count += 1
                        
                except Exception:
                    # 如果文件损坏，也删除它
                    cache_file.unlink()
                    deleted_count += 1
            
            if deleted_count > 0:
                logger.info(f"清理了 {deleted_count} 个过期缓存文件")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"清理过期缓存失败: {e}")
            return deleted_count


class CacheManager:
    """缓存管理器"""
    
    def __init__(self):
        """初始化缓存管理器"""
        # 从配置获取缓存设置
        self.enabled = get_config_value("cache.enabled", True)
        backend_type = get_config_value("cache.backend", "sqlite")
        self.ttl_hours = get_config_value("cache.ttl_hours", 12)
        self.ttl_seconds = self.ttl_hours * 3600
        
        if not self.enabled:
            logger.info("缓存已禁用")
            self.backend = None
            return
        
        # 创建缓存后端
        if backend_type == "sqlite":
            db_path = get_config_value("cache.db_path", "instance/cache/cache.db")
            max_entries = get_config_value("cache.max_entries", 10000)
            self.backend = SQLiteCacheBackend(db_path, max_entries)
        elif backend_type == "file":
            cache_dir = get_config_value("cache.db_path", "instance/cache").replace(".db", "")
            max_entries = get_config_value("cache.max_entries", 10000)
            self.backend = FileCacheBackend(cache_dir, max_entries)
        else:
            logger.error(f"不支持的缓存后端: {backend_type}")
            self.backend = None
            self.enabled = False
            return
        
        logger.info(f"缓存管理器初始化完成: {backend_type}, TTL={self.ttl_hours}小时")
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        if not self.enabled or not self.backend:
            return None
        
        return self.backend.get(key)
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存值"""
        if not self.enabled or not self.backend:
            return False
        
        ttl = ttl or self.ttl_seconds
        return self.backend.set(key, value, ttl)
    
    def delete(self, key: str) -> bool:
        """删除缓存值"""
        if not self.enabled or not self.backend:
            return False
        
        return self.backend.delete(key)
    
    def clear(self) -> bool:
        """清空所有缓存"""
        if not self.enabled or not self.backend:
            return False
        
        return self.backend.clear()
    
    def cleanup_expired(self) -> int:
        """清理过期缓存"""
        if not self.enabled or not self.backend:
            return 0
        
        return self.backend.cleanup_expired()
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        if not self.enabled or not self.backend:
            return {"enabled": False}
        
        stats = {"enabled": True, "ttl_hours": self.ttl_hours}
        
        if hasattr(self.backend, 'get_statistics'):
            stats.update(self.backend.get_statistics())
        
        return stats


# 全局缓存管理器实例
cache_manager = CacheManager()