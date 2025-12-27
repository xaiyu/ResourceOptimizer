"""
配置加载器
负责加载和验证系统配置
"""

import os
import yaml
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class ConfigValidator:
    """配置验证器"""
    
    @staticmethod
    def validate(config: Dict[str, Any]) -> List[str]:
        """
        验证配置并返回错误列表
        
        Args:
            config: 配置字典
            
        Returns:
            错误信息列表，空列表表示验证通过
        """
        errors = []
        
        # 验证必需的顶级配置节
        required_sections = ['app', 'weights', 'provider', 'cache', 'logging']
        for section in required_sections:
            if section not in config:
                errors.append(f"缺少必需的配置节: {section}")
        
        # 验证应用配置
        app_config = config.get('app', {})
        if app_config.get('max_concurrency', 0) <= 0:
            errors.append("app.max_concurrency 必须大于0")
        if app_config.get('max_concurrency', 0) > 10:
            errors.append("app.max_concurrency 不应超过10 (保护API)")
        if app_config.get('min_file_size_mb', 0) < 0:
            errors.append("app.min_file_size_mb 不能为负数")
        
        # 验证动态漏斗配置
        funnel_config = app_config.get('funnel', {})
        if funnel_config.get('batch_size', 0) <= 0:
            errors.append("app.funnel.batch_size 必须大于0")
        if funnel_config.get('max_sources', 0) <= 0:
            errors.append("app.funnel.max_sources 必须大于0")
        if funnel_config.get('stop_multiplier', 0) <= 0:
            errors.append("app.funnel.stop_multiplier 必须大于0")
        
        # 验证重试配置
        retry_config = funnel_config.get('retry', {})
        if retry_config.get('max_retries', 0) < 0:
            errors.append("app.funnel.retry.max_retries 不能为负数")
        if retry_config.get('backoff_factor', 0) <= 0:
            errors.append("app.funnel.retry.backoff_factor 必须大于0")
        
        # 验证增强组件配置
        enhanced_config = config.get('enhanced_components', {})
        if enhanced_config.get('enable', True):
            consistency_config = enhanced_config.get('consistency_checker', {})
            if consistency_config.get('size_deviation', 0) <= 0:
                errors.append("enhanced_components.consistency_checker.size_deviation 必须大于0")
            if consistency_config.get('min_samples', 0) <= 0:
                errors.append("enhanced_components.consistency_checker.min_samples 必须大于0")
        
        # 验证管道配置
        pipeline_config = config.get('pipeline', {})
        valid_modes = ['static', 'dynamic', 'auto']
        if pipeline_config.get('mode', 'dynamic') not in valid_modes:
            errors.append(f"pipeline.mode 必须是以下值之一: {valid_modes}")
        
        # 验证API配置 (警告级别，不阻止启动)
        provider_config = config.get('provider', {})
        if not provider_config.get('silicon_api_key'):
            logger.warning("未配置 SiliconFlow API 密钥，LLM功能将不可用")
        if not provider_config.get('tmdb_api_key'):
            logger.warning("未配置 TMDB API 密钥，剧集状态查询将不可用")
        if not provider_config.get('quark_cookie'):
            logger.warning("未配置夸克网盘Cookie，文件爬取将不可用")
        
        # 验证缓存配置
        cache_config = config.get('cache', {})
        if cache_config.get('ttl_hours', 0) <= 0:
            errors.append("cache.ttl_hours 必须大于0")
        
        return errors


class ConfigLoader:
    """
    配置加载器
    支持多种配置源和优先级
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置加载器
        
        Args:
            config_path: 配置文件路径，如果为None则自动查找
        """
        self.config_path = config_path or self._find_config_path()
        self.config = {}
        
    def _find_config_path(self) -> str:
        """自动查找配置文件路径"""
        # 查找顺序：
        # 1. 当前目录下的 smart_chase/config/settings.yaml
        # 2. 项目根目录下的 config/settings.yaml
        # 3. 环境变量 SMART_CHASE_CONFIG
        
        candidates = [
            "config/settings.yaml",
            "smart_chase/config/settings.yaml",  # 兼容旧路径
            os.environ.get("SMART_CHASE_CONFIG", "")
        ]
        
        for path in candidates:
            if path and os.path.exists(path):
                logger.info(f"找到配置文件: {path}")
                return path
        
        # 如果都找不到，返回默认路径
        default_path = "config/settings.yaml"
        logger.warning(f"未找到配置文件，将使用默认路径: {default_path}")
        return default_path
    
    def load_config(self) -> Dict[str, Any]:
        """
        加载配置文件
        
        Returns:
            配置字典
            
        Raises:
            FileNotFoundError: 配置文件不存在
            yaml.YAMLError: 配置文件格式错误
            ValueError: 配置验证失败
        """
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                
            if not config:
                raise ValueError("配置文件为空")
            
            # 应用环境变量覆盖
            config = self._apply_env_overrides(config)
            
            # 验证配置
            errors = ConfigValidator.validate(config)
            if errors:
                raise ValueError(f"配置验证失败: {'; '.join(errors)}")
            
            self.config = config
            logger.info("配置加载成功")
            return config
            
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"配置文件格式错误: {e}")
        except Exception as e:
            raise ValueError(f"加载配置失败: {e}")
    
    def _apply_env_overrides(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        应用环境变量覆盖
        支持的环境变量格式: SMART_CHASE_<SECTION>_<KEY>
        """
        env_mappings = {
            'SMART_CHASE_SILICON_API_KEY': ('provider', 'silicon_api_key'),
            'SMART_CHASE_TMDB_API_KEY': ('provider', 'tmdb_api_key'),
            'SMART_CHASE_QUARK_COOKIE': ('provider', 'quark_cookie'),
            'SMART_CHASE_LOG_LEVEL': ('logging', 'level'),
            'SMART_CHASE_MAX_CONCURRENCY': ('app', 'max_concurrency'),
            
            # 动态漏斗配置
            'SMART_CHASE_FUNNEL_BATCH_SIZE': ('app.funnel', 'batch_size'),
            'SMART_CHASE_FUNNEL_MAX_SOURCES': ('app.funnel', 'max_sources'),
            'SMART_CHASE_FUNNEL_STOP_MULTIPLIER': ('app.funnel', 'stop_multiplier'),
            
            # 增强组件配置
            'SMART_CHASE_ENHANCED_ENABLE': ('enhanced_components', 'enable'),
            'SMART_CHASE_CONSISTENCY_ENABLE': ('enhanced_components.consistency_checker', 'enable'),
            'SMART_CHASE_NAMING_ENABLE': ('enhanced_components.naming_generator', 'enable'),
            
            # 管道配置
            'SMART_CHASE_PIPELINE_MODE': ('pipeline', 'mode'),
            'SMART_CHASE_PIPELINE_FALLBACK': ('pipeline', 'fallback_enabled'),
        }
        
        for env_var, (section_path, key) in env_mappings.items():
            value = os.environ.get(env_var)
            if value:
                # 处理嵌套路径
                sections = section_path.split('.')
                current = config
                
                # 创建嵌套结构
                for section in sections[:-1]:
                    if section not in current:
                        current[section] = {}
                    current = current[section]
                
                final_section = sections[-1]
                if final_section not in current:
                    current[final_section] = {}
                
                # 类型转换
                if key in ['max_concurrency', 'batch_size', 'max_sources']:
                    try:
                        value = int(value)
                    except ValueError:
                        logger.warning(f"环境变量 {env_var} 值无效，忽略")
                        continue
                elif key in ['stop_multiplier']:
                    try:
                        value = float(value)
                    except ValueError:
                        logger.warning(f"环境变量 {env_var} 值无效，忽略")
                        continue
                elif key in ['enable', 'fallback_enabled']:
                    value = value.lower() in ('true', '1', 'yes', 'on')
                
                current[final_section][key] = value
                logger.info(f"应用环境变量覆盖: {env_var}")
        
        return config
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值，支持点分隔的键路径
        
        Args:
            key: 配置键路径，如 "app.max_concurrency"
            default: 默认值
            
        Returns:
            配置值或默认值
        """
        if not self.config:
            self.load_config()
        
        keys = key.split(".")
        value = self.config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def create_directories(self) -> None:
        """创建配置中指定的目录"""
        directories = [
            self.get("cache.db_path", "").rsplit("/", 1)[0],  # 缓存目录
            self.get("logging.file", "").rsplit("/", 1)[0],   # 日志目录
            self.get("output.base_dir", ""),                  # 输出目录
            self.get("monitoring.metrics_file", "").rsplit("/", 1)[0],  # 监控目录
        ]
        
        for directory in directories:
            if directory:
                Path(directory).mkdir(parents=True, exist_ok=True)
                logger.debug(f"创建目录: {directory}")


# 全局配置实例
config_loader = ConfigLoader()

def get_config() -> Dict[str, Any]:
    """获取全局配置"""
    return config_loader.config or config_loader.load_config()

def get_config_value(key: str, default: Any = None) -> Any:
    """获取配置值的便捷函数"""
    return config_loader.get(key, default)

def create_dynamic_funnel_config() -> 'DynamicFunnelConfig':
    """创建动态漏斗配置对象"""
    from core.contracts import DynamicFunnelConfig, RetryConfig, StopConditionConfig
    
    config = get_config()
    funnel_config = config.get('app', {}).get('funnel', {})
    
    retry_config = RetryConfig(
        max_retries=funnel_config.get('retry', {}).get('max_retries', 3),
        backoff_factor=funnel_config.get('retry', {}).get('backoff_factor', 2.0),
        initial_delay=funnel_config.get('retry', {}).get('initial_delay', 1.0),
        max_delay=funnel_config.get('retry', {}).get('max_delay', 60.0)
    )
    
    stop_config = StopConditionConfig(
        candidate_multiplier=funnel_config.get('stop_conditions', {}).get('candidate_multiplier', 3.0),
        quality_threshold_batches=funnel_config.get('stop_conditions', {}).get('quality_threshold_batches', 3),
        score_threshold=funnel_config.get('stop_conditions', {}).get('score_threshold', 60),
        enable_early_stop=funnel_config.get('stop_conditions', {}).get('enable_early_stop', True)
    )
    
    return DynamicFunnelConfig(
        batch_size=funnel_config.get('batch_size', 3),
        max_sources=funnel_config.get('max_sources', 15),
        stop_multiplier=funnel_config.get('stop_multiplier', 3.0),
        enable_early_stop=funnel_config.get('enable_early_stop', True),
        retry_config=retry_config,
        stop_config=stop_config
    )

def create_consistency_config() -> 'ConsistencyConfig':
    """创建一致性检查配置对象"""
    from core.contracts import ConsistencyConfig
    
    config = get_config()
    consistency_config = config.get('enhanced_components', {}).get('consistency_checker', {})
    
    return ConsistencyConfig(
        enable=consistency_config.get('enable', True),
        size_deviation=consistency_config.get('size_deviation', 0.5),
        min_samples=consistency_config.get('min_samples', 3)
    )

def create_naming_config() -> 'NamingConfig':
    """创建命名配置对象"""
    from core.contracts import NamingConfig
    
    config = get_config()
    naming_config = config.get('enhanced_components', {}).get('naming_generator', {})
    
    return NamingConfig(
        enable=naming_config.get('enable', True),
        format_template=naming_config.get('format_template', "{title} S{season:02d}E{episode:02d} [{quality}].{ext}"),
        quality_tags=naming_config.get('quality_tags', {
            "2160p": "4K",
            "1080p": "1080p", 
            "hdr": "HDR",
            "atmos": "Atmos"
        })
    )

def create_component_config() -> 'ComponentConfig':
    """创建组件配置对象"""
    from core.contracts import ComponentConfig
    
    config = get_config()
    enhanced_config = config.get('enhanced_components', {})
    
    return ComponentConfig(
        consistency_config=create_consistency_config(),
        naming_config=create_naming_config(),
        enable_enhanced_features=enhanced_config.get('enable', True),
        validate_on_creation=enhanced_config.get('validate_on_startup', True)
    )

def create_pipeline_config() -> 'PipelineConfig':
    """创建管道配置对象"""
    from core.contracts import PipelineConfig
    
    config = get_config()
    pipeline_config = config.get('pipeline', {})
    
    return PipelineConfig(
        funnel_config=create_dynamic_funnel_config(),
        component_config=create_component_config(),
        enable_dynamic_mode=pipeline_config.get('mode', 'dynamic') == 'dynamic',
        fallback_to_static=pipeline_config.get('fallback_enabled', True)
    )