"""
核心数据契约
定义系统中各模块间交互的标准化数据结构
"""

from dataclasses import dataclass, field
from typing import List, Set, Optional, Dict, Any
import time


@dataclass
class RawFileNode:
    """
    [原子节点] 扁平化后的文件信息
    用于在系统中传递单个文件的完整信息
    """
    file_id: str              # 唯一指纹 (用于去重)
    filename: str             # 文件名
    size: int                 # 文件大小(字节)
    full_path: str            # 完整路径 /文件夹/S01/文件.mp4
    share_token: str          # 所属分享链接标识
    source_context: str       # 【关键】注入的来源标题 (如 "[4K Remux] 庆余年2")
    
    def __post_init__(self):
        """数据完整性验证"""
        if not self.file_id:
            raise ValueError("file_id 不能为空")
        if not self.filename:
            raise ValueError("filename 不能为空")
        if self.size < 0:
            raise ValueError("size 不能为负数")


@dataclass
class SeriesState:
    """
    [状态快照] 上帝视角
    包含剧集的完整状态信息，用于决策计算
    """
    tmdb_total_aired: Set[int]  # TMDB已播出集数
    local_existing: Set[int]    # 本地已存储集数
    last_updated: float = field(default_factory=time.time)  # 缓存标记，避免短时间内重复查询
    
    def get_missing_episodes(self) -> Set[int]:
        """获取缺失的集数"""
        return self.tmdb_total_aired - self.local_existing
    
    def is_cache_valid(self, ttl_seconds: int = 43200) -> bool:
        """检查缓存是否有效 (默认12小时)"""
        return time.time() - self.last_updated < ttl_seconds


@dataclass
class VideoMeta:
    """
    [中间态] LLM 解析后的元数据
    包含视频文件的结构化信息
    """
    title_cn: str             # 中文标题
    season: int               # 季数
    episode: int              # 集数
    resolution: str           # 分辨率 (如 "4K", "1080p")
    quality_score: int        # 质量评分 0-100
    is_valid_video: bool      # 是否为有效视频文件
    
    def __post_init__(self):
        """数据完整性验证"""
        if self.quality_score < 0 or self.quality_score > 100:
            raise ValueError("quality_score 必须在 0-100 之间")
        if self.season < 0:
            raise ValueError("season 不能为负数")
        if self.episode < 0:
            raise ValueError("episode 不能为负数")


@dataclass
class AnalysisContext:
    """
    [输入包] 决策引擎的唯一输入
    封装了决策所需的所有信息
    """
    standard_title: str         # 标准剧名 (唯一键)
    candidates: List[RawFileNode]  # 候选文件列表
    state: SeriesState          # 剧集状态信息
    
    def __post_init__(self):
        """数据完整性验证"""
        if not self.standard_title:
            raise ValueError("standard_title 不能为空")
        if not isinstance(self.candidates, list):
            raise ValueError("candidates 必须是列表类型")
        if not isinstance(self.state, SeriesState):
            raise ValueError("state 必须是 SeriesState 类型")


@dataclass
class RankedSource:
    """
    [源竞价结果] 经过评分排序的源信息
    """
    title: str                # 源标题
    url: str                  # 源链接
    score: int                # 评分
    rank: int                 # 排名 (1-based)
    
    def __post_init__(self):
        """数据完整性验证"""
        if not self.title:
            raise ValueError("title 不能为空")
        if not self.url:
            raise ValueError("url 不能为空")
        if self.rank < 1:
            raise ValueError("rank 必须大于等于 1")


@dataclass
class SelectedFile:
    """
    [决策结果] 被选中用于转存的文件
    """
    file_node: RawFileNode    # 原始文件节点
    video_meta: VideoMeta     # 解析后的元数据
    selection_reason: str     # 选择原因
    priority: int = 0         # 优先级 (数字越大优先级越高)
    
    # v4.1 新增字段
    target_filename: Optional[str] = None  # 标准化目标文件名
    rename_metadata: Optional[Dict[str, Any]] = None  # 重命名元数据
    consistency_score: Optional[float] = None  # 一致性评分 (0.0-1.0)
    
    def __post_init__(self):
        """数据完整性验证"""
        if not isinstance(self.file_node, RawFileNode):
            raise ValueError("file_node 必须是 RawFileNode 类型")
        if not isinstance(self.video_meta, VideoMeta):
            raise ValueError("video_meta 必须是 VideoMeta 类型")
        if self.consistency_score is not None and not (0.0 <= self.consistency_score <= 1.0):
            raise ValueError("consistency_score 必须在 0.0-1.0 之间")


@dataclass
class SaveResult:
    """
    [转存结果] 批量转存操作的结果统计
    """
    total_files: int          # 总文件数
    success_count: int        # 成功转存数
    failed_count: int         # 失败转存数
    failed_files: List[str] = field(default_factory=list)  # 失败文件列表
    execution_time: float = 0.0  # 执行时间(秒)
    
    def __post_init__(self):
        """数据完整性验证"""
        if self.total_files < 0:
            raise ValueError("total_files 不能为负数")
        if self.success_count < 0:
            raise ValueError("success_count 不能为负数")
        if self.failed_count < 0:
            raise ValueError("failed_count 不能为负数")
        if self.success_count + self.failed_count > self.total_files:
            raise ValueError("成功+失败数不能超过总数")
        if self.execution_time < 0:
            raise ValueError("execution_time 不能为负数")
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_files == 0:
            return 0.0
        return self.success_count / self.total_files


@dataclass
class CacheEntry:
    """
    [缓存条目] 通用缓存数据结构
    """
    key: str                  # 缓存键
    data: Any                 # 缓存数据
    timestamp: float          # 创建时间戳
    ttl: int                  # 生存时间(秒)
    
    def __post_init__(self):
        """数据完整性验证"""
        if not self.key:
            raise ValueError("key 不能为空")
        if self.timestamp < 0:
            raise ValueError("timestamp 不能为负数")
        if self.ttl <= 0:
            raise ValueError("ttl 必须大于 0")
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        return time.time() - self.timestamp > self.ttl
    
    def refresh(self, new_data: Any) -> None:
        """刷新缓存数据"""
        self.data = new_data
        self.timestamp = time.time()


# 类型别名，提高代码可读性
FileList = List[RawFileNode]
SourceList = List[RankedSource]
MetaList = List[VideoMeta]
SelectedList = List[SelectedFile]


@dataclass
class DynamicFunnelConfig:
    """
    [v4.1] 动态漏斗筛选配置
    """
    batch_size: int = 3              # 每批检查源数量
    max_sources: int = 10            # 最大检查源数量
    stop_multiplier: float = 3.0     # 停止阈值系数 (候选数 > 缺集数 * 此系数)
    enable_early_stop: bool = True   # 是否启用提前停止


@dataclass
class ConsistencyConfig:
    """
    [v4.1] 一致性检查配置
    管理文件一致性验证的参数

    推荐使用 config_service.get_consistency_config() 获取配置实例
    """
    enable: bool = True
    size_deviation: float = 0.5
    min_samples: int = 3


@dataclass
class NamingConfig:
    """
    [v4.1] 标准化命名配置
    提供质量标签映射和命名模板的集中管理

    推荐使用 config_service.get_naming_config() 获取配置实例
    """
    enable: bool = True
    format_template: str = "{title} S{season:02d}E{episode:02d} [{quality}].{ext}"
    quality_tags: Dict[str, str] = field(default_factory=lambda: {
        "2160p": "4K",
        "1080p": "1080p",
        "hdr": "HDR",
        "atmos": "Atmos"
    })


@dataclass
class SeriesInfo:
    """
    [v4.1] 剧集基础信息
    """
    title: str                       # 剧集标题
    season: int                      # 季数
    total_episodes: int = 0          # 总集数
    tmdb_id: Optional[int] = None    # TMDB ID
    
    def __post_init__(self):
        """数据完整性验证"""
        if not self.title:
            raise ValueError("title 不能为空")
        if self.season < 1:
            raise ValueError("season 必须大于等于 1")
        if self.total_episodes < 0:
            raise ValueError("total_episodes 不能为负数")


# ============================================================================
# 动态漏斗循环与增强组件集成 - 新增数据结构
# ============================================================================

@dataclass
class FunnelResult:
    """动态漏斗处理结果"""
    selected_sources: List[RankedSource]
    candidate_files: List[RawFileNode]
    stop_reason: str
    performance_metrics: 'FunnelMetrics'
    batch_history: List['BatchResult']


@dataclass
class FunnelMetrics:
    """漏斗性能指标"""
    total_batches: int
    successful_batches: int
    total_api_calls: int
    total_processing_time: float
    candidates_per_batch: List[int]
    stop_condition_triggered: str


@dataclass
class BatchResult:
    """批次处理结果"""
    batch_index: int
    sources_processed: int
    candidates_found: int
    processing_time: float
    success: bool
    error_message: Optional[str] = None


@dataclass
class StopDecision:
    """停止决策"""
    should_stop: bool
    reason: str
    confidence: float


@dataclass
class ValidationResult:
    """组件验证结果"""
    is_valid: bool
    missing_components: List[str] = field(default_factory=list)
    configuration_errors: List[str] = field(default_factory=list)


@dataclass
class ComponentConfig:
    """组件配置"""
    consistency_config: ConsistencyConfig
    naming_config: NamingConfig
    enable_enhanced_features: bool = True
    validate_on_creation: bool = True


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3
    backoff_factor: float = 2.0
    initial_delay: float = 1.0
    max_delay: float = 60.0


@dataclass
class StopConditionConfig:
    """停止条件配置"""
    candidate_multiplier: float = 3.0
    quality_threshold_batches: int = 3
    score_threshold: int = 60
    min_candidates: int = 5          # 最小候选数量保底 (修复洗版模式漏洞)
    enable_early_stop: bool = True


@dataclass
class PipelineConfig:
    """管道配置"""
    funnel_config: DynamicFunnelConfig
    component_config: ComponentConfig
    enable_dynamic_mode: bool = True
    fallback_to_static: bool = True


@dataclass
class EnhancedDecisionResult:
    """增强的决策结果"""
    selected_files: List[SelectedFile]
    series_title: str
    total_candidates: int
    consistency_filtered: int
    renamed_files: int
    statistics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RetryResult:
    """重试结果"""
    success: bool
    total_attempts: int
    final_result: Any
    retry_history: List[Dict[str, Any]] = field(default_factory=list)
    total_delay: float = 0.0


@dataclass
class FunnelContext:
    """漏斗处理上下文"""
    series_title: str
    missing_episodes: Set[int]
    target_candidates: int
    current_batch: int = 0
    total_candidates: int = 0


# 扩展现有的DynamicFunnelConfig
@dataclass
class DynamicFunnelConfig:
    """
    [v4.1+] 动态漏斗筛选配置 - 扩展版
    """
    batch_size: int = 3              # 每批检查源数量
    max_sources: int = 15            # 最大检查源数量 (增加到15)
    stop_multiplier: float = 3.0     # 停止阈值系数 (候选数 > 缺集数 * 此系数)
    min_candidates: int = 5          # 最小候选数量保底 (修复洗版模式漏洞)
    enable_early_stop: bool = True   # 是否启用提前停止
    
    # 新增配置项
    retry_config: RetryConfig = field(default_factory=RetryConfig)
    stop_config: StopConditionConfig = field(default_factory=StopConditionConfig)


# 错误恢复相关
from enum import Enum

class RecoveryAction(Enum):
    """恢复动作枚举"""
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    FAIL_FAST = "fail_fast"
    REDUCE_BATCH_SIZE = "reduce_batch_size"
    FALLBACK_TO_STATIC = "fallback_to_static"
    DISABLE_CONSISTENCY_CHECK = "disable_consistency_check"
    USE_ORIGINAL_NAMES = "use_original_names"
    FALLBACK_TO_BASIC_DECISION = "fallback_to_basic_decision"