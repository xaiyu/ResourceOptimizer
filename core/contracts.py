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


@dataclass
class SelectedFile:
    """
    [决策结果] 被选中用于转存的文件
    """
    file_node: RawFileNode    # 原始文件节点
    video_meta: VideoMeta     # 解析后的元数据
    selection_reason: str     # 选择原因
    priority: int = 0         # 优先级 (数字越大优先级越高)


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