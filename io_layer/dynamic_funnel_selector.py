"""
动态漏斗筛选器 v4.1
解决漏选问题，实现智能的源选择策略
"""

import logging
import asyncio
from typing import List, Tuple, Set
from dataclasses import dataclass

from core.contracts import RawFileNode, DynamicFunnelConfig, SeriesState
from io_layer.crawler import QuarkCrawler


class DynamicFunnelSelector:
    """
    动态漏斗筛选器
    
    核心功能：
    1. 分批处理源，避免一次性处理过多
    2. 动态扩容，直到找到足够的候选文件
    3. 智能提前停止，优化API调用次数
    """
    
    def __init__(self, config: DynamicFunnelConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.crawler = QuarkCrawler()
    
    async def select_with_funnel(self, 
                                sources: List[dict], 
                                series_state: SeriesState) -> Tuple[List[dict], List[RawFileNode]]:
        """
        使用动态漏斗策略选择源和文件
        
        Args:
            sources: 排序后的源列表 [{"title": "...", "url": "...", "score": ...}]
            series_state: 剧集状态信息
            
        Returns:
            (selected_sources, candidate_pool): 选中的源和候选文件池
        """
        missing_count = len(series_state.get_missing_episodes())
        target_candidates = int(missing_count * self.config.stop_multiplier)
        
        candidate_pool = []
        selected_sources = []
        
        self.logger.info(f"🎯 动态漏斗筛选开始")
        self.logger.info(f"   缺失集数: {missing_count}")
        self.logger.info(f"   目标候选数: {target_candidates}")
        self.logger.info(f"   可用源数: {len(sources)}")
        
        # 分批处理源
        for batch_idx in range(0, min(len(sources), self.config.max_sources), 
                              self.config.batch_size):
            batch_end = min(batch_idx + self.config.batch_size, len(sources))
            batch = sources[batch_idx:batch_end]
            
            self.logger.info(f"📦 处理批次 {batch_idx//self.config.batch_size + 1}: "
                           f"源 {batch_idx+1}-{batch_end}")
            
            # 处理当前批次
            batch_files = await self._process_batch(batch)
            candidate_pool.extend(batch_files)
            selected_sources.extend(batch)
            
            self.logger.info(f"   新增候选文件: {len(batch_files)} 个")
            self.logger.info(f"   累计候选文件: {len(candidate_pool)} 个")
            
            # 检查提前停止条件
            if (self.config.enable_early_stop and 
                len(candidate_pool) >= target_candidates):
                self.logger.info(f"✅ 达到目标候选数 ({target_candidates})，提前停止")
                break
            
            # 如果是最后一批，记录日志
            if batch_end >= min(len(sources), self.config.max_sources):
                self.logger.info(f"📋 已处理所有可用源 ({batch_end} 个)")
        
        # 统计结果
        self.logger.info(f"🎉 动态漏斗筛选完成:")
        self.logger.info(f"   选中源数: {len(selected_sources)}")
        self.logger.info(f"   候选文件数: {len(candidate_pool)}")
        self.logger.info(f"   覆盖率: {len(candidate_pool)/max(missing_count, 1):.1f}x")
        
        return selected_sources, candidate_pool
    
    async def _process_batch(self, batch: List[dict]) -> List[RawFileNode]:
        """
        处理一批源，获取候选文件
        
        Args:
            batch: 当前批次的源列表
            
        Returns:
            从当前批次获取的所有文件
        """
        batch_files = []
        
        for source in batch:
            try:
                self.logger.debug(f"🔍 爬取源: {source['title'][:30]}...")
                
                # 爬取文件
                files = await self.crawler.crawl_share_link(
                    source['url'], 
                    source['title']  # 作为source_context注入
                )
                
                if files:
                    batch_files.extend(files)
                    self.logger.debug(f"   获得文件: {len(files)} 个")
                else:
                    self.logger.debug(f"   空源，跳过")
                    
            except Exception as e:
                self.logger.warning(f"❌ 爬取失败: {source['title'][:30]} - {e}")
                continue
        
        return batch_files
    
    def _calculate_missing_episodes(self, series_state: SeriesState) -> int:
        """计算缺失集数"""
        return len(series_state.get_missing_episodes())
    
    def get_statistics(self) -> dict:
        """获取筛选统计信息"""
        return {
            "config": {
                "batch_size": self.config.batch_size,
                "max_sources": self.config.max_sources,
                "stop_multiplier": self.config.stop_multiplier,
                "enable_early_stop": self.config.enable_early_stop
            }
        }