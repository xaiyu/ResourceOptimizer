"""
一致性检查器 v4.1
解决品控粗糙问题，基于统计学方法剔除异常文件
"""

import logging
import statistics
from typing import List, Dict, Optional
from collections import defaultdict

from core.contracts import RawFileNode, ConsistencyConfig, VideoMeta


class ConsistencyChecker:
    """
    一致性检查器
    
    核心功能：
    1. 基于文件大小的统计学分析
    2. 剔除偏差过大的异常文件
    3. 确保同一剧集版本的一致性
    """
    
    def __init__(self, config: ConsistencyConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def check_size_consistency(self, 
                              candidates: List[RawFileNode], 
                              video_metas: List[VideoMeta]) -> List[RawFileNode]:
        """
        执行大小一致性检查
        
        Args:
            candidates: 候选文件列表
            video_metas: 对应的视频元数据列表
            
        Returns:
            通过一致性检查的文件列表
        """
        if not self.config.enable:
            self.logger.info("🔄 一致性检查已禁用，跳过")
            return candidates
        
        if len(candidates) < self.config.min_samples:
            self.logger.info(f"📊 样本数不足 ({len(candidates)} < {self.config.min_samples})，跳过一致性检查")
            return candidates
        
        self.logger.info(f"📊 开始一致性检查: {len(candidates)} 个候选文件")
        
        # 按集数分组
        episode_groups = self._group_by_episode(candidates, video_metas)
        
        # 选出每集最佳候选
        best_per_episode = self._select_best_per_episode(episode_groups)
        
        if len(best_per_episode) < self.config.min_samples:
            self.logger.info(f"📊 有效集数不足 ({len(best_per_episode)} < {self.config.min_samples})，跳过检查")
            return candidates
        
        # 执行统计分析
        consistent_files = self._analyze_and_filter(best_per_episode)
        
        # 记录结果
        removed_count = len(best_per_episode) - len(consistent_files)
        self.logger.info(f"📊 一致性检查完成:")
        self.logger.info(f"   输入文件: {len(candidates)} 个")
        self.logger.info(f"   有效集数: {len(best_per_episode)} 集")
        self.logger.info(f"   保留文件: {len(consistent_files)} 个")
        self.logger.info(f"   剔除文件: {removed_count} 个")
        
        return consistent_files
    
    def _group_by_episode(self, 
                         candidates: List[RawFileNode], 
                         video_metas: List[VideoMeta]) -> Dict[int, List[tuple]]:
        """
        按集数分组文件
        
        Returns:
            {episode_num: [(file, meta), ...]}
        """
        episode_groups = defaultdict(list)
        
        for file_node, meta in zip(candidates, video_metas):
            if meta.is_valid_video and meta.episode > 0:
                episode_groups[meta.episode].append((file_node, meta))
        
        self.logger.debug(f"🔢 按集数分组: {len(episode_groups)} 个不同集数")
        return episode_groups
    
    def _select_best_per_episode(self, 
                                episode_groups: Dict[int, List[tuple]]) -> List[tuple]:
        """
        每集选出评分最高的候选
        
        Returns:
            [(file, meta), ...] 每集最佳文件
        """
        best_per_episode = []
        
        for episode, files_metas in episode_groups.items():
            # 按质量评分排序，选择最高分
            best_file_meta = max(files_metas, key=lambda x: x[1].quality_score)
            best_per_episode.append(best_file_meta)
            
            self.logger.debug(f"📺 第{episode}集最佳: {best_file_meta[0].filename[:30]} "
                            f"(评分: {best_file_meta[1].quality_score})")
        
        return best_per_episode
    
    def _analyze_and_filter(self, best_per_episode: List[tuple]) -> List[RawFileNode]:
        """
        统计分析并过滤异常文件
        
        Args:
            best_per_episode: [(file, meta), ...] 每集最佳文件
            
        Returns:
            通过一致性检查的文件列表
        """
        # 提取文件大小
        sizes = [file_meta[0].size for file_meta in best_per_episode]
        
        # 计算统计指标
        median_size = statistics.median(sizes)
        mean_size = statistics.mean(sizes)
        
        self.logger.info(f"📏 大小统计:")
        self.logger.info(f"   中位数: {median_size/1024/1024:.1f} MB")
        self.logger.info(f"   平均值: {mean_size/1024/1024:.1f} MB")
        self.logger.info(f"   偏差阈值: ±{self.config.size_deviation:.0%}")
        
        # 过滤异常文件
        consistent_files = []
        
        for file_node, meta in best_per_episode:
            deviation = abs(file_node.size - median_size) / median_size
            
            if deviation <= self.config.size_deviation:
                # 通过检查，添加一致性评分
                consistency_score = 1.0 - deviation
                consistent_files.append(file_node)
                
                self.logger.debug(f"✅ 保留: {file_node.filename[:30]} "
                                f"(大小: {file_node.size/1024/1024:.1f}MB, "
                                f"偏差: {deviation:.1%}, "
                                f"一致性: {consistency_score:.2f})")
            else:
                # 异常文件，剔除
                self.logger.warning(f"🚫 剔除异常文件: {file_node.filename[:30]}")
                self.logger.warning(f"   大小: {file_node.size/1024/1024:.1f} MB")
                self.logger.warning(f"   偏差: {deviation:.1%} (超过阈值 {self.config.size_deviation:.0%})")
        
        return consistent_files
    
    def get_statistics(self) -> dict:
        """获取检查统计信息"""
        return {
            "config": {
                "enable": self.config.enable,
                "size_deviation": self.config.size_deviation,
                "min_samples": self.config.min_samples
            }
        }
    
    def _calculate_consistency_score(self, file_size: int, median_size: int) -> float:
        """
        计算一致性评分
        
        Args:
            file_size: 文件大小
            median_size: 中位数大小
            
        Returns:
            一致性评分 (0.0-1.0)，越接近1.0越一致
        """
        if median_size == 0:
            return 0.0
        
        deviation = abs(file_size - median_size) / median_size
        return max(0.0, 1.0 - deviation)