"""
集中式配置服务层
提供配置对象的统一访问和注入机制

设计原则：
1. 配置对象与业务逻辑分离
2. 组件通过构造函数接收配置对象，而非直接读取配置值
3. 默认值集中在配置文件模块中定义
4. 支持配置验证和依赖注入
"""

import os
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from config.config_loader import get_config_value

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """LLM客户端配置"""
    api_key: str = ""
    base_url: str = "https://api.siliconflow.cn/v1"
    model: str = "Qwen/Qwen3-8B-Instruct"
    max_concurrency: int = 4
    timeout: int = 30
    retry_count: int = 3
    circuit_breaker_threshold: int = 10

    @classmethod
    def from_config(cls) -> "LLMConfig":
        """从全局配置加载"""
        return cls(
            api_key=get_config_value("provider.silicon_api_key", ""),
            base_url=get_config_value("provider.silicon_base_url", "https://api.siliconflow.cn/v1"),
            model=get_config_value("provider.silicon_model", "Qwen/Qwen3-8B-Instruct"),
            max_concurrency=get_config_value("app.max_concurrency", 4),
            timeout=get_config_value("provider.silicon_timeout", 30),
            retry_count=get_config_value("provider.silicon_retry_count", 3),
            circuit_breaker_threshold=get_config_value("app.circuit_breaker_threshold", 10)
        )


@dataclass
class TMDBConfig:
    """TMDB状态提供者配置"""
    api_key: str = ""
    base_url: str = "https://api.themoviedb.org/3"
    language: str = "zh-CN"

    @classmethod
    def from_config(cls) -> "TMDBConfig":
        """从全局配置加载"""
        return cls(
            api_key=get_config_value("provider.tmdb_api_key", ""),
            base_url=get_config_value("provider.tmdb_base_url", "https://api.themoviedb.org/3"),
            language=get_config_value("provider.tmdb_language", "zh-CN")
        )


@dataclass
class QuarkConfig:
    """夸克网盘配置"""
    cookie: str = ""
    root_path: str = "/我的资源"
    upload_parallel: int = 3
    base_url: str = "https://drive-pc.quark.cn"
    base_url_app: str = "https://drive-m.quark.cn"
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) quark-cloud-drive/3.14.2 Chrome/112.0.5615.165 Electron/24.1.3.8 Safari/537.36 Channel/pckk_other_ch"
    timeout: int = 30
    retry_count: int = 3
    retry_delay: int = 1

    @classmethod
    def from_config(cls) -> "QuarkConfig":
        """从全局配置加载"""
        return cls(
            cookie=get_config_value("provider.quark_cookie", ""),
            root_path=get_config_value("provider.quark_root_path", "/我的资源"),
            upload_parallel=get_config_value("provider.quark_upload_parallel", 3),
            base_url=get_config_value("provider.quark_base_url", "https://drive-pc.quark.cn"),
            base_url_app=get_config_value("provider.quark_base_url_app", "https://drive-m.quark.cn"),
            user_agent=get_config_value("provider.quark_user_agent", 
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) quark-cloud-drive/3.14.2 Chrome/112.0.5615.165 Electron/24.1.3.8 Safari/537.36 Channel/pckk_other_ch"),
            timeout=get_config_value("provider.quark_timeout", 30),
            retry_count=get_config_value("provider.quark_retry_count", 3),
            retry_delay=get_config_value("provider.quark_retry_delay", 1)
        )


@dataclass
class WeightsConfig:
    """决策引擎权重配置"""
    quality_threshold: int = 70
    upgrade_threshold: int = 20
    local_quality_baseline: int = 70
    strategy_weights: Dict[str, float] = field(default_factory=lambda: {
        "weight": 0.3,
        "naming": 0.4,
        "llm": 0.2,
        "extra": 0.1
    })

    @classmethod
    def from_config(cls) -> "WeightsConfig":
        """从全局配置加载"""
        return cls(
            quality_threshold=get_config_value("weights.quality_threshold", 70),
            upgrade_threshold=get_config_value("weights.upgrade_threshold", 20),
            local_quality_baseline=get_config_value("weights.local_quality_baseline", 70),
            strategy_weights=get_config_value("weights.strategy_weights", {
                "weight": 0.3,
                "naming": 0.4,
                "llm": 0.2,
                "extra": 0.1
            })
        )


@dataclass
class AppConfig:
    """应用级别配置"""
    min_file_size_mb: int = 200
    max_concurrency: int = 4
    max_selections: int = 50
    circuit_breaker_threshold: int = 10

    @classmethod
    def from_config(cls) -> "AppConfig":
        """从全局配置加载"""
        return cls(
            min_file_size_mb=get_config_value("app.min_file_size_mb", 200),
            max_concurrency=get_config_value("app.max_concurrency", 4),
            max_selections=get_config_value("app.max_selections", 50),
            circuit_breaker_threshold=get_config_value("app.circuit_breaker_threshold", 10)
        )


@dataclass
class FunnelRuntimeConfig:
    """动态漏斗运行时配置"""
    batch_size: int = 3
    max_sources: int = 10
    stop_multiplier: float = 3.0
    enable_early_stop: bool = True
    min_candidates: int = 5

    @classmethod
    def from_config(cls) -> "FunnelRuntimeConfig":
        """从全局配置加载"""
        funnel = get_config_value("app.funnel", {})
        return cls(
            batch_size=funnel.get("batch_size", 3),
            max_sources=funnel.get("max_sources", 10),
            stop_multiplier=funnel.get("stop_multiplier", 3.0),
            enable_early_stop=funnel.get("enable_early_stop", True),
            min_candidates=funnel.get("min_candidates", 5)
        )


@dataclass
class CacheConfig:
    """缓存配置"""
    db_path: str = "./data/cache.db"
    ttl_hours: int = 24

    @classmethod
    def from_config(cls) -> "CacheConfig":
        """从全局配置加载"""
        return cls(
            db_path=get_config_value("cache.db_path", "./data/cache.db"),
            ttl_hours=get_config_value("cache.ttl_hours", 24)
        )


@dataclass
class LoggingConfig:
    """日志配置"""
    level: str = "INFO"
    file: str = "./data/logs/app.log"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    @classmethod
    def from_config(cls) -> "LoggingConfig":
        """从全局配置加载"""
        return cls(
            level=get_config_value("logging.level", "INFO"),
            file=get_config_value("logging.file", "./data/logs/app.log"),
            format=get_config_value("logging.format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )


@dataclass
class NamingConfig:
    """
    [v4.1] 标准化命名配置
    提供质量标签映射和命名模板的集中管理
    """
    enable: bool = True
    format_template: str = "{title} S{season:02d}E{episode:02d} [{quality}].{ext}"
    quality_tags: Dict[str, str] = field(default_factory=lambda: {
        "2160p": "4K",
        "1080p": "1080p",
        "hdr": "HDR",
        "atmos": "Atmos"
    })

    @classmethod
    def from_config(cls) -> "NamingConfig":
        """从全局配置加载"""
        naming = get_config_value("naming", {})
        quality_tags = naming.get("quality_tags", {
            "2160p": "4K",
            "1080p": "1080p",
            "hdr": "HDR",
            "atmos": "Atmos"
        })
        return cls(
            enable=naming.get("enable", True),
            format_template=naming.get("format_template", "{title} S{season:02d}E{episode:02d} [{quality}].{ext}"),
            quality_tags=quality_tags
        )


@dataclass
class ConsistencyConfig:
    """
    [v4.1] 一致性检查配置
    管理文件一致性验证的参数
    """
    enable: bool = True
    size_deviation: float = 0.5
    min_samples: int = 3

    @classmethod
    def from_config(cls) -> "ConsistencyConfig":
        """从全局配置加载"""
        consistency = get_config_value("consistency", {})
        return cls(
            enable=consistency.get("enable", True),
            size_deviation=consistency.get("size_deviation", 0.5),
            min_samples=consistency.get("min_samples", 3)
        )


@dataclass
class SourceScoreConfig:
    """
    [v4.1] 源评分配置
    集中管理源头竞价的关键词权重
    """
    weights: Dict[str, int] = field(default_factory=lambda: {
        "Remux": 50, "BluRay": 40, "4K": 30, "2160p": 30, "1080p": 10,
        "HDR": 20, "杜比视界": 25, "全景声": 15, "HEVC": 10, "H265": 10,
        "WEB-DL": 8, "TrueHD": 12, "DTS-HD": 12, "60fps": 8,
        "中字": 5, "内嵌": 5, "无水印": 3, "纯净": 3,
        "720p": -20, "Trailer": -100, "预告": -100, "广告": -100,
        "测试": -50, "假4K": -80, "机翻": -60, "删减版": -70
    })
    aliases: Dict[str, List[str]] = field(default_factory=dict)

    @classmethod
    def from_config(cls) -> "SourceScoreConfig":
        """从全局配置加载"""
        config_weights = get_config_value("weights.keyword_score", {})
        config_aliases = get_config_value("aliases", {})
        default_weights = {
            "Remux": 50, "BluRay": 40, "4K": 30, "2160p": 30, "1080p": 10,
            "HDR": 20, "杜比视界": 25, "全景声": 15, "HEVC": 10, "H265": 10,
            "WEB-DL": 8, "TrueHD": 12, "DTS-HD": 12, "60fps": 8,
            "中字": 5, "内嵌": 5, "无水印": 3, "纯净": 3,
            "720p": -20, "Trailer": -100, "预告": -100, "广告": -100,
            "测试": -50, "假4K": -80, "机翻": -60, "删减版": -70
        }
        return cls(
            weights={**default_weights, **config_weights},
            aliases=config_aliases
        )


@dataclass
class RetryConfig:
    """
    [v4.1] 重试配置
    管理失败重试的参数
    """
    max_retries: int = 3
    backoff_factor: float = 2.0
    initial_delay: float = 1.0
    max_delay: float = 60.0

    @classmethod
    def from_config(cls) -> "RetryConfig":
        """从全局配置加载"""
        retry = get_config_value("retry", {})
        return cls(
            max_retries=retry.get("max_retries", 3),
            backoff_factor=retry.get("backoff_factor", 2.0),
            initial_delay=retry.get("initial_delay", 1.0),
            max_delay=retry.get("max_delay", 60.0)
        )


@dataclass
class StopConditionConfig:
    """
    [v4.1] 停止条件配置
    管理动态漏斗停止条件的参数
    """
    candidate_multiplier: float = 3.0
    quality_threshold_batches: int = 3
    score_threshold: int = 60
    min_candidates: int = 5
    enable_early_stop: bool = True

    @classmethod
    def from_config(cls) -> "StopConditionConfig":
        """从全局配置加载"""
        stop = get_config_value("funnel.stop", {})
        return cls(
            candidate_multiplier=stop.get("candidate_multiplier", 3.0),
            quality_threshold_batches=stop.get("quality_threshold_batches", 3),
            score_threshold=stop.get("score_threshold", 60),
            min_candidates=stop.get("min_candidates", 5),
            enable_early_stop=stop.get("enable_early_stop", True)
        )


class ConfigService:
    """
    集中式配置服务
    提供所有配置对象的统一访问

    使用方式：
    1. 组件通过构造函数接收配置对象
    2. 主程序负责从ConfigService获取配置并注入组件
    """

    _instance: Optional["ConfigService"] = None
    _config_cache: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self._config_cache = {}

    def get_llm_config(self, override: Optional[Dict[str, Any]] = None) -> LLMConfig:
        """获取LLM配置，支持覆盖"""
        if override:
            base = LLMConfig.from_config()
            for key, value in override.items():
                if hasattr(base, key):
                    setattr(base, key, value)
            return base
        cache_key = "llm_config"
        if cache_key not in self._config_cache:
            self._config_cache[cache_key] = LLMConfig.from_config()
        return self._config_cache[cache_key]

    def get_tmdb_config(self, override: Optional[Dict[str, Any]] = None) -> TMDBConfig:
        """获取TMDB配置，支持覆盖"""
        if override:
            base = TMDBConfig.from_config()
            for key, value in override.items():
                if hasattr(base, key):
                    setattr(base, key, value)
            return base
        cache_key = "tmdb_config"
        if cache_key not in self._config_cache:
            self._config_cache[cache_key] = TMDBConfig.from_config()
        return self._config_cache[cache_key]

    def get_quark_config(self, override: Optional[Dict[str, Any]] = None) -> QuarkConfig:
        """获取夸克配置，支持覆盖"""
        if override:
            base = QuarkConfig.from_config()
            for key, value in override.items():
                if hasattr(base, key):
                    setattr(base, key, value)
            return base
        cache_key = "quark_config"
        if cache_key not in self._config_cache:
            self._config_cache[cache_key] = QuarkConfig.from_config()
        return self._config_cache[cache_key]

    def get_weights_config(self, override: Optional[Dict[str, Any]] = None) -> WeightsConfig:
        """获取权重配置，支持覆盖"""
        if override:
            base = WeightsConfig.from_config()
            for key, value in override.items():
                if hasattr(base, key):
                    setattr(base, key, value)
            return base
        cache_key = "weights_config"
        if cache_key not in self._config_cache:
            self._config_cache[cache_key] = WeightsConfig.from_config()
        return self._config_cache[cache_key]

    def get_app_config(self, override: Optional[Dict[str, Any]] = None) -> AppConfig:
        """获取应用配置，支持覆盖"""
        if override:
            base = AppConfig.from_config()
            for key, value in override.items():
                if hasattr(base, key):
                    setattr(base, key, value)
            return base
        cache_key = "app_config"
        if cache_key not in self._config_cache:
            self._config_cache[cache_key] = AppConfig.from_config()
        return self._config_cache[cache_key]

    def get_funnel_config(self, override: Optional[Dict[str, Any]] = None) -> FunnelRuntimeConfig:
        """获取动态漏斗配置，支持覆盖"""
        if override:
            base = FunnelRuntimeConfig.from_config()
            for key, value in override.items():
                if hasattr(base, key):
                    setattr(base, key, value)
            return base
        cache_key = "funnel_config"
        if cache_key not in self._config_cache:
            self._config_cache[cache_key] = FunnelRuntimeConfig.from_config()
        return self._config_cache[cache_key]

    def get_cache_config(self, override: Optional[Dict[str, Any]] = None) -> CacheConfig:
        """获取缓存配置，支持覆盖"""
        if override:
            base = CacheConfig.from_config()
            for key, value in override.items():
                if hasattr(base, key):
                    setattr(base, key, value)
            return base
        cache_key = "cache_config"
        if cache_key not in self._config_cache:
            self._config_cache[cache_key] = CacheConfig.from_config()
        return self._config_cache[cache_key]

    def get_logging_config(self, override: Optional[Dict[str, Any]] = None) -> LoggingConfig:
        """获取日志配置，支持覆盖"""
        if override:
            base = LoggingConfig.from_config()
            for key, value in override.items():
                if hasattr(base, key):
                    setattr(base, key, value)
            return base
        cache_key = "logging_config"
        if cache_key not in self._config_cache:
            self._config_cache[cache_key] = LoggingConfig.from_config()
        return self._config_cache[cache_key]

    def get_naming_config(self, override: Optional[Dict[str, Any]] = None) -> NamingConfig:
        """获取命名配置，支持覆盖"""
        if override:
            base = NamingConfig.from_config()
            for key, value in override.items():
                if hasattr(base, key):
                    setattr(base, key, value)
            return base
        cache_key = "naming_config"
        if cache_key not in self._config_cache:
            self._config_cache[cache_key] = NamingConfig.from_config()
        return self._config_cache[cache_key]

    def get_consistency_config(self, override: Optional[Dict[str, Any]] = None) -> ConsistencyConfig:
        """获取一致性检查配置，支持覆盖"""
        if override:
            base = ConsistencyConfig.from_config()
            for key, value in override.items():
                if hasattr(base, key):
                    setattr(base, key, value)
            return base
        cache_key = "consistency_config"
        if cache_key not in self._config_cache:
            self._config_cache[cache_key] = ConsistencyConfig.from_config()
        return self._config_cache[cache_key]

    def get_source_score_config(self, override: Optional[Dict[str, Any]] = None) -> SourceScoreConfig:
        """获取源评分配置，支持覆盖"""
        if override:
            base = SourceScoreConfig.from_config()
            for key, value in override.items():
                if hasattr(base, key):
                    setattr(base, key, value)
            return base
        cache_key = "source_score_config"
        if cache_key not in self._config_cache:
            self._config_cache[cache_key] = SourceScoreConfig.from_config()
        return self._config_cache[cache_key]

    def get_retry_config(self, override: Optional[Dict[str, Any]] = None) -> RetryConfig:
        """获取重试配置，支持覆盖"""
        if override:
            base = RetryConfig.from_config()
            for key, value in override.items():
                if hasattr(base, key):
                    setattr(base, key, value)
            return base
        cache_key = "retry_config"
        if cache_key not in self._config_cache:
            self._config_cache[cache_key] = RetryConfig.from_config()
        return self._config_cache[cache_key]

    def get_stop_condition_config(self, override: Optional[Dict[str, Any]] = None) -> StopConditionConfig:
        """获取停止条件配置，支持覆盖"""
        if override:
            base = StopConditionConfig.from_config()
            for key, value in override.items():
                if hasattr(base, key):
                    setattr(base, key, value)
            return base
        cache_key = "stop_condition_config"
        if cache_key not in self._config_cache:
            self._config_cache[cache_key] = StopConditionConfig.from_config()
        return self._config_cache[cache_key]

    def clear_cache(self) -> None:
        """清除配置缓存"""
        self._config_cache.clear()
        logger.debug("配置缓存已清除")


config_service = ConfigService()


def get_llm_config(override: Optional[Dict[str, Any]] = None) -> LLMConfig:
    """获取LLM配置的便捷函数"""
    return config_service.get_llm_config(override)


def get_tmdb_config(override: Optional[Dict[str, Any]] = None) -> TMDBConfig:
    """获取TMDB配置的便捷函数"""
    return config_service.get_tmdb_config(override)


def get_quark_config(override: Optional[Dict[str, Any]] = None) -> QuarkConfig:
    """获取夸克配置的便捷函数"""
    return config_service.get_quark_config(override)


def get_weights_config(override: Optional[Dict[str, Any]] = None) -> WeightsConfig:
    """获取权重配置的便捷函数"""
    return config_service.get_weights_config(override)


def get_app_config(override: Optional[Dict[str, Any]] = None) -> AppConfig:
    """获取应用配置的便捷函数"""
    return config_service.get_app_config(override)


def get_funnel_config(override: Optional[Dict[str, Any]] = None) -> FunnelRuntimeConfig:
    """获取动态漏斗配置的便捷函数"""
    return config_service.get_funnel_config(override)


def get_cache_config(override: Optional[Dict[str, Any]] = None) -> CacheConfig:
    """获取缓存配置的便捷函数"""
    return config_service.get_cache_config(override)


def get_logging_config(override: Optional[Dict[str, Any]] = None) -> LoggingConfig:
    """获取日志配置的便捷函数"""
    return config_service.get_logging_config(override)


def get_naming_config(override: Optional[Dict[str, Any]] = None) -> NamingConfig:
    """获取命名配置的便捷函数"""
    return config_service.get_naming_config(override)


def get_consistency_config(override: Optional[Dict[str, Any]] = None) -> ConsistencyConfig:
    """获取一致性检查配置的便捷函数"""
    return config_service.get_consistency_config(override)


def get_source_score_config(override: Optional[Dict[str, Any]] = None) -> SourceScoreConfig:
    """获取源评分配置的便捷函数"""
    return config_service.get_source_score_config(override)


def get_retry_config(override: Optional[Dict[str, Any]] = None) -> RetryConfig:
    """获取重试配置的便捷函数"""
    return config_service.get_retry_config(override)


def get_stop_condition_config(override: Optional[Dict[str, Any]] = None) -> StopConditionConfig:
    """获取停止条件配置的便捷函数"""
    return config_service.get_stop_condition_config(override)
