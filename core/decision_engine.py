"""
逻辑裁决模块
负责根据剧集状态和解析结果，智能选择最优文件进行转存
"""

import logging
from typing import List, Set, Dict, Optional, Tuple
from collections import defaultdict
import re

from core.contracts import AnalysisContext, VideoMeta, SelectedFile, RawFileNode, SeriesState
from config.config_loader import get_config_value

logger = logging.getLogger(__name__)


class DecisionMaker:
    """
    决策引擎
    实现缺口计算、分组竞价、质量择优等核心算法
    """
    
    def __init__(self):
        """初始化决策引擎"""
        # 获取配置
        self.quality_threshold = get_config_value("weights.quality_threshold", 70)
        self.upgrade_threshold = get_config_value("weights.upgrade_threshold", 20)  # 洗版阈值
        self.max_selections = get_config_value("app.max_selections", 50)  # 最大选择数量
        
        # 权重配置
        self.strategy_weights = get_config_value("weights.strategy_weights", {
            "weight": 0.3,    # 质量权重
            "naming": 0.4,    # 命名匹配
            "llm": 0.2,       # LLM判断
            "extra": 0.1      # 额外因素
        })
        
        logger.info(f"决策引擎初始化完成 (质量阈值: {self.quality_threshold}, 洗版阈值: {self.upgrade_threshold})")
    
    def decide(self, context: AnalysisContext, parsed_results: List[VideoMeta]) -> List[SelectedFile]:
        """
        主决策函数 - 根据上下文和解析结果选择最优文件
        
        Args:
            context: 分析上下文
            parsed_results: LLM解析结果列表
            
        Returns:
            选中的文件列表
        """
        logger.info(f"开始决策: {context.standard_title}, 候选文件 {len(context.candidates)} 个")
        
        # 1. 确定缺口 - 计算需要下载的集数
        missing_episodes = self._identify_gaps(context.state)
        logger.info(f"缺失集数: {sorted(missing_episodes)} (共 {len(missing_episodes)} 集)")
        
        if not missing_episodes:
            logger.info("没有缺失集数，无需下载")
            return []
        
        # 2. 构建文件-元数据映射
        file_meta_map = self._build_file_meta_map(context.candidates, parsed_results)
        logger.info(f"有效文件-元数据映射: {len(file_meta_map)} 个")
        
        # 3. 按集数分组
        episode_groups = self._group_by_episode(file_meta_map, missing_episodes)
        logger.info(f"按集数分组: {len(episode_groups)} 个集数有候选文件")
        
        # 4. 为每个缺失集数选择最优文件
        selected_files = []
        
        for episode in sorted(missing_episodes):
            if episode in episode_groups:
                candidates = episode_groups[episode]
                best_candidate = self._select_best_quality(candidates, context.standard_title)
                
                if best_candidate:
                    file_node, video_meta = best_candidate
                    
                    # 创建选择结果
                    selected_file = SelectedFile(
                        file_node=file_node,
                        video_meta=video_meta,
                        selection_reason=self._generate_selection_reason(video_meta, len(candidates)),
                        priority=video_meta.quality_score
                    )
                    
                    selected_files.append(selected_file)
                    logger.info(f"选择集数 {episode}: {file_node.filename[:50]}... "
                               f"(评分: {video_meta.quality_score})")
                else:
                    logger.warning(f"集数 {episode} 没有合适的候选文件")
            else:
                logger.warning(f"集数 {episode} 没有找到候选文件")
        
        # 5. 检查洗版机会
        upgrade_files = self._check_upgrade_opportunities(context, file_meta_map)
        if upgrade_files:
            selected_files.extend(upgrade_files)
            logger.info(f"发现 {len(upgrade_files)} 个洗版机会")
        
        # 6. 按优先级排序并限制数量
        selected_files.sort(key=lambda x: x.priority, reverse=True)
        if len(selected_files) > self.max_selections:
            selected_files = selected_files[:self.max_selections]
            logger.warning(f"选择文件数量超过限制，截取前 {self.max_selections} 个")
        
        logger.info(f"决策完成: 选择了 {len(selected_files)} 个文件")
        return selected_files
    
    def _identify_gaps(self, state: SeriesState) -> Set[int]:
        """
        确定缺口 - 计算需要下载的集数
        
        Args:
            state: 剧集状态
            
        Returns:
            缺失的集数集合
        """
        missing = state.get_missing_episodes()
        logger.debug(f"TMDB已播出: {sorted(state.tmdb_total_aired)}")
        logger.debug(f"本地已存储: {sorted(state.local_existing)}")
        logger.debug(f"计算缺失: {sorted(missing)}")
        
        return missing
    
    def _build_file_meta_map(self, file_nodes: List[RawFileNode], 
                           parsed_results: List[VideoMeta]) -> List[Tuple[RawFileNode, VideoMeta]]:
        """
        构建文件-元数据映射
        
        Args:
            file_nodes: 文件节点列表
            parsed_results: 解析结果列表
            
        Returns:
            (文件节点, 视频元数据) 元组列表
        """
        if len(file_nodes) != len(parsed_results):
            logger.error(f"文件数量 ({len(file_nodes)}) 与解析结果数量 ({len(parsed_results)}) 不匹配")
            return []
        
        file_meta_pairs = []
        
        for file_node, video_meta in zip(file_nodes, parsed_results):
            # 过滤无效视频
            if not video_meta.is_valid_video:
                logger.debug(f"跳过无效视频: {file_node.filename}")
                continue
            
            # 过滤低质量文件
            if video_meta.quality_score < self.quality_threshold:
                logger.debug(f"跳过低质量文件: {file_node.filename} (评分: {video_meta.quality_score})")
                continue
            
            file_meta_pairs.append((file_node, video_meta))
        
        return file_meta_pairs
    
    def _group_by_episode(self, file_meta_pairs: List[Tuple[RawFileNode, VideoMeta]], 
                         missing_episodes: Set[int]) -> Dict[int, List[Tuple[RawFileNode, VideoMeta]]]:
        """
        按集数分组
        
        Args:
            file_meta_pairs: 文件-元数据对列表
            missing_episodes: 缺失集数
            
        Returns:
            按集数分组的字典 {集数: [(文件节点, 视频元数据), ...]}
        """
        episode_groups = defaultdict(list)
        
        for file_node, video_meta in file_meta_pairs:
            episode = video_meta.episode
            
            # 只关注缺失的集数
            if episode in missing_episodes:
                episode_groups[episode].append((file_node, video_meta))
                logger.debug(f"集数 {episode} 添加候选: {file_node.filename[:30]}...")
        
        # 记录每个集数的候选数量
        for episode, candidates in episode_groups.items():
            logger.debug(f"集数 {episode}: {len(candidates)} 个候选文件")
        
        return dict(episode_groups)
    
    def _select_best_quality(self, candidates: List[Tuple[RawFileNode, VideoMeta]], 
                           title: str) -> Optional[Tuple[RawFileNode, VideoMeta]]:
        """
        质量择优选择
        
        Args:
            candidates: 候选文件列表
            title: 剧集标题
            
        Returns:
            最优的 (文件节点, 视频元数据) 对，如果没有合适的则返回None
        """
        if not candidates:
            return None
        
        if len(candidates) == 1:
            return candidates[0]
        
        # 计算综合评分
        scored_candidates = []
        
        for file_node, video_meta in candidates:
            # 基础质量评分
            quality_score = video_meta.quality_score
            
            # 命名匹配加分
            naming_score = self._calculate_naming_score(file_node, video_meta, title)
            
            # 文件大小加分 (大文件通常质量更好)
            size_score = self._calculate_size_score(file_node.size)
            
            # 来源可信度加分
            source_score = self._calculate_source_score(file_node.source_context)
            
            # 综合评分
            total_score = (
                quality_score * self.strategy_weights["weight"] +
                naming_score * self.strategy_weights["naming"] +
                size_score * self.strategy_weights["extra"] +
                source_score * self.strategy_weights["extra"]
            )
            
            scored_candidates.append((total_score, file_node, video_meta))
            
            logger.debug(f"候选评分: {file_node.filename[:30]}... = {total_score:.1f} "
                        f"(质量:{quality_score}, 命名:{naming_score:.1f}, "
                        f"大小:{size_score:.1f}, 来源:{source_score:.1f})")
        
        # 选择评分最高的
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_file, best_meta = scored_candidates[0]
        
        logger.debug(f"最优选择: {best_file.filename[:30]}... (综合评分: {best_score:.1f})")
        
        return (best_file, best_meta)
    
    def _calculate_naming_score(self, file_node: RawFileNode, video_meta: VideoMeta, title: str) -> float:
        """
        计算命名匹配评分
        
        Args:
            file_node: 文件节点
            video_meta: 视频元数据
            title: 目标标题
            
        Returns:
            命名匹配评分 (0-100)
        """
        score = 50.0  # 基础分
        
        filename = file_node.filename.lower()
        source_context = file_node.source_context.lower()
        target_title = title.lower()
        
        # 标题匹配
        if target_title in filename or target_title in source_context:
            score += 20
        
        # 季集格式匹配
        season_episode_pattern = f"s{video_meta.season:02d}e{video_meta.episode:02d}"
        if season_episode_pattern in filename:
            score += 15
        
        # 分辨率匹配
        if video_meta.resolution.lower() in filename:
            score += 10
        
        # 编码格式匹配
        if any(codec in filename for codec in ['h265', 'hevc', 'x265']):
            score += 5
        
        return min(100.0, score)
    
    def _calculate_size_score(self, file_size: int) -> float:
        """
        计算文件大小评分
        
        Args:
            file_size: 文件大小(字节)
            
        Returns:
            大小评分 (0-100)
        """
        # 转换为GB
        size_gb = file_size / (1024 ** 3)
        
        # 大小评分曲线
        if size_gb >= 10:      # 10GB以上 - 超高质量
            return 100.0
        elif size_gb >= 5:     # 5-10GB - 高质量
            return 80.0
        elif size_gb >= 2:     # 2-5GB - 中等质量
            return 60.0
        elif size_gb >= 1:     # 1-2GB - 一般质量
            return 40.0
        else:                  # 1GB以下 - 低质量
            return 20.0
    
    def _calculate_source_score(self, source_context: str) -> float:
        """
        计算来源可信度评分
        
        Args:
            source_context: 来源上下文
            
        Returns:
            来源评分 (0-100)
        """
        if not source_context:
            return 50.0
        
        source_lower = source_context.lower()
        score = 50.0
        
        # 高质量来源关键词
        high_quality_keywords = ['remux', 'bluray', '4k', 'hdr', '杜比视界', '全景声']
        for keyword in high_quality_keywords:
            if keyword in source_lower:
                score += 10
        
        # 可信发布组
        trusted_groups = ['frds', 'hdctv', 'group', 'team']
        for group in trusted_groups:
            if group in source_lower:
                score += 5
        
        return min(100.0, score)
    
    def _check_upgrade_opportunities(self, context: AnalysisContext, 
                                   file_meta_pairs: List[Tuple[RawFileNode, VideoMeta]]) -> List[SelectedFile]:
        """
        检查洗版机会 - 寻找可以升级的本地文件
        
        Args:
            context: 分析上下文
            file_meta_pairs: 文件-元数据对列表
            
        Returns:
            可以洗版的文件列表
        """
        upgrade_files = []
        
        # 获取本地已有集数
        local_episodes = context.state.local_existing
        
        if not local_episodes:
            return upgrade_files
        
        # 按集数分组所有候选文件
        all_episode_groups = defaultdict(list)
        for file_node, video_meta in file_meta_pairs:
            all_episode_groups[video_meta.episode].append((file_node, video_meta))
        
        # 检查每个本地集数是否有更高质量的版本
        for episode in local_episodes:
            if episode in all_episode_groups:
                candidates = all_episode_groups[episode]
                
                # 寻找高质量候选
                for file_node, video_meta in candidates:
                    # 假设本地文件质量评分为70分（可以通过配置调整）
                    local_quality = 70
                    
                    # 如果新文件质量明显更高，考虑洗版
                    if video_meta.quality_score - local_quality >= self.upgrade_threshold:
                        selected_file = SelectedFile(
                            file_node=file_node,
                            video_meta=video_meta,
                            selection_reason=f"洗版升级: 本地{local_quality}分 → 新版{video_meta.quality_score}分",
                            priority=video_meta.quality_score + 10  # 洗版优先级稍低
                        )
                        
                        upgrade_files.append(selected_file)
                        logger.info(f"发现洗版机会 E{episode:02d}: {file_node.filename[:40]}... "
                                   f"(质量提升: {video_meta.quality_score - local_quality}分)")
                        break  # 每集只选一个最优洗版
        
        return upgrade_files
    
    def _generate_selection_reason(self, video_meta: VideoMeta, candidate_count: int) -> str:
        """
        生成选择原因
        
        Args:
            video_meta: 视频元数据
            candidate_count: 候选文件数量
            
        Returns:
            选择原因字符串
        """
        reasons = []
        
        # 质量评分
        if video_meta.quality_score >= 90:
            reasons.append("超高质量")
        elif video_meta.quality_score >= 80:
            reasons.append("高质量")
        else:
            reasons.append("合格质量")
        
        # 分辨率
        if video_meta.resolution in ["4K", "2160p"]:
            reasons.append("4K分辨率")
        elif video_meta.resolution == "1080p":
            reasons.append("1080p分辨率")
        
        # 竞争情况
        if candidate_count > 1:
            reasons.append(f"从{candidate_count}个候选中择优")
        else:
            reasons.append("唯一候选")
        
        return ", ".join(reasons)
    
    def get_statistics(self) -> Dict[str, any]:
        """
        获取决策引擎统计信息
        
        Returns:
            统计信息字典
        """
        return {
            "quality_threshold": self.quality_threshold,
            "upgrade_threshold": self.upgrade_threshold,
            "max_selections": self.max_selections,
            "strategy_weights": self.strategy_weights
        }


def create_decision_maker() -> DecisionMaker:
    """
    创建决策引擎实例的工厂函数
    
    Returns:
        配置好的决策引擎实例
    """
    return DecisionMaker()