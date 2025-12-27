"""
动态漏斗筛选器 v4.1+
解决漏选问题，实现智能的源选择策略
集成停止条件评估器和重试循环引擎
"""

import logging
import asyncio
import time
from typing import List, Tuple, Set, Dict, Any
from dataclasses import dataclass

from core.contracts import (
    RawFileNode, DynamicFunnelConfig, SeriesState, RankedSource,
    FunnelResult, FunnelMetrics, BatchResult, FunnelContext
)
from core.stop_condition_evaluator import StopConditionEvaluator
from core.retry_loop_engine import RetryLoopEngine, BatchProcessor
from io_layer.crawler import QuarkCrawler


class SourceBatchProcessor(BatchProcessor):
    """源批次处理器"""
    
    def __init__(self, crawler: QuarkCrawler):
        self.crawler = crawler
        self.logger = logging.getLogger(__name__)
    
    async def process_batch(self, batch: List[RankedSource], context: Dict[str, Any] = None) -> List[RawFileNode]:
        """
        处理源批次，获取候选文件
        
        Args:
            batch: 源批次
            context: 处理上下文
            
        Returns:
            从当前批次获取的所有文件
        """
        batch_files = []
        
        for source in batch:
            try:
                self.logger.debug(f"🔍 爬取源: {source.title[:30]}...")
                
                # 爬取文件
                files = await self.crawler.crawl_share_link(
                    source.url, 
                    source.title  # 作为source_context注入
                )
                
                if files:
                    batch_files.extend(files)
                    self.logger.debug(f"   获得文件: {len(files)} 个")
                else:
                    self.logger.debug(f"   空源，跳过")
                    
            except Exception as e:
                self.logger.warning(f"❌ 爬取失败: {source.title[:30]} - {e}")
                continue
        
        return batch_files


class DynamicFunnelSelector:
    """
    动态漏斗筛选器 v4.1+
    
    核心功能：
    1. 分批处理源，避免一次性处理过多
    2. 动态扩容，直到找到足够的候选文件
    3. 智能提前停止，优化API调用次数
    4. 集成重试循环和停止条件评估
    """
    
    def __init__(self, config: DynamicFunnelConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 初始化组件
        self.crawler = QuarkCrawler()
        self.batch_processor = SourceBatchProcessor(self.crawler)
        self.stop_evaluator = StopConditionEvaluator(config.stop_config)
        self.retry_engine = RetryLoopEngine(config.retry_config)
        
        # 性能指标
        self.metrics = FunnelMetrics(
            total_batches=0,
            successful_batches=0,
            total_api_calls=0,
            total_processing_time=0.0,
            candidates_per_batch=[],
            stop_condition_triggered=""
        )
        
        self.logger.info(f"🎯 动态漏斗筛选器初始化完成")
        self.logger.info(f"   批次大小: {config.batch_size}")
        self.logger.info(f"   最大源数: {config.max_sources}")
        self.logger.info(f"   停止倍数: {config.stop_multiplier}")
    
    async def select_with_funnel(self, 
                                sources: List[RankedSource], 
                                series_state: SeriesState) -> FunnelResult:
        """
        使用动态漏斗策略选择源和文件
        
        Args:
            sources: 排序后的源列表
            series_state: 剧集状态信息
            
        Returns:
            漏斗处理结果
        """
        start_time = time.time()
        missing_episodes = series_state.get_missing_episodes()
        missing_count = len(missing_episodes)
        target_candidates = int(missing_count * self.config.stop_multiplier)
        
        candidate_pool = []
        selected_sources = []
        batch_history = []
        
        self.logger.info(f"🎯 动态漏斗筛选开始")
        self.logger.info(f"   缺失集数: {missing_count}")
        self.logger.info(f"   目标候选数: {target_candidates}")
        self.logger.info(f"   可用源数: {len(sources)}")
        
        # 创建处理上下文
        context = FunnelContext(
            series_title=getattr(series_state, 'series_title', 'Unknown'),
            missing_episodes=missing_episodes,
            target_candidates=target_candidates
        )
        
        # 分批处理源 - 完整的While循环逻辑
        batch_index = 0
        processed_sources = 0
        
        while processed_sources < min(len(sources), self.config.max_sources):
            # 计算当前批次
            batch_start = processed_sources
            batch_end = min(batch_start + self.config.batch_size, 
                          len(sources), 
                          self.config.max_sources)
            
            if batch_start >= batch_end:
                break
            
            current_batch = sources[batch_start:batch_end]
            batch_index += 1
            
            self.logger.info(f"📦 处理批次 {batch_index}: 源 {batch_start+1}-{batch_end}")
            
            # 使用重试引擎处理当前批次
            batch_start_time = time.time()
            
            try:
                retry_result = await self.retry_engine.execute_single_batch_with_retry(
                    self._process_single_batch,
                    current_batch,
                    {"context": context}
                )
                
                batch_processing_time = time.time() - batch_start_time
                
                if retry_result.success:
                    batch_files = retry_result.final_result
                    candidate_pool.extend(batch_files)
                    selected_sources.extend(current_batch)
                    
                    # 记录成功的批次
                    batch_result = BatchResult(
                        batch_index=batch_index,
                        sources_processed=len(current_batch),
                        candidates_found=len(batch_files),
                        processing_time=batch_processing_time,
                        success=True
                    )
                    
                    self.logger.info(f"   新增候选文件: {len(batch_files)} 个")
                    self.logger.info(f"   累计候选文件: {len(candidate_pool)} 个")
                    
                else:
                    # 记录失败的批次
                    batch_result = BatchResult(
                        batch_index=batch_index,
                        sources_processed=len(current_batch),
                        candidates_found=0,
                        processing_time=batch_processing_time,
                        success=False,
                        error_message=f"重试失败: {retry_result.retry_history[-1].get('error', 'Unknown')}"
                    )
                    
                    self.logger.warning(f"   批次处理失败，继续下一批次")
                
                batch_history.append(batch_result)
                
                # 更新性能指标
                self.metrics.total_batches += 1
                if batch_result.success:
                    self.metrics.successful_batches += 1
                self.metrics.candidates_per_batch.append(batch_result.candidates_found)
                self.metrics.total_api_calls += len(current_batch)
                
                # 检查停止条件
                remaining_sources = sources[batch_end:self.config.max_sources]
                stop_decision = self.stop_evaluator.should_stop(
                    len(candidate_pool),
                    missing_episodes,
                    batch_history,
                    remaining_sources
                )
                
                if stop_decision.should_stop:
                    self.metrics.stop_condition_triggered = stop_decision.reason
                    self.logger.info(f"✅ {stop_decision.reason}，提前停止")
                    break
                
                processed_sources = batch_end
                
            except Exception as e:
                self.logger.error(f"❌ 批次处理异常: {e}")
                
                # 记录异常批次
                batch_result = BatchResult(
                    batch_index=batch_index,
                    sources_processed=len(current_batch),
                    candidates_found=0,
                    processing_time=time.time() - batch_start_time,
                    success=False,
                    error_message=str(e)
                )
                batch_history.append(batch_result)
                
                processed_sources = batch_end
                continue
        
        # 处理完成统计
        total_processing_time = time.time() - start_time
        self.metrics.total_processing_time = total_processing_time
        
        if not self.metrics.stop_condition_triggered:
            if processed_sources >= min(len(sources), self.config.max_sources):
                self.metrics.stop_condition_triggered = "已处理所有可用源"
            else:
                self.metrics.stop_condition_triggered = "处理中断"
        
        # 构建结果
        result = FunnelResult(
            selected_sources=selected_sources,
            candidate_files=candidate_pool,
            stop_reason=self.metrics.stop_condition_triggered,
            performance_metrics=self.metrics,
            batch_history=batch_history
        )
        
        self.logger.info(f"🎉 动态漏斗筛选完成:")
        self.logger.info(f"   选中源数: {len(selected_sources)}")
        self.logger.info(f"   候选文件数: {len(candidate_pool)}")
        self.logger.info(f"   覆盖率: {len(candidate_pool)/max(missing_count, 1):.1f}x")
        self.logger.info(f"   总耗时: {total_processing_time:.2f}s")
        self.logger.info(f"   停止原因: {self.metrics.stop_condition_triggered}")
        
        return result
    
    async def _process_single_batch(self, batches: List[Any], context: Dict[str, Any] = None) -> List[RawFileNode]:
        """
        处理单个批次的内部方法
        
        Args:
            batches: 批次列表 (这里只有一个批次)
            context: 处理上下文
            
        Returns:
            批次处理结果
        """
        if not batches:
            return []
        
        batch = batches[0]  # 取第一个批次
        return await self.batch_processor.process_batch(batch, context)
    
    def get_performance_report(self) -> Dict[str, Any]:
        """
        获取性能报告
        
        Returns:
            性能报告字典
        """
        if self.metrics.total_batches == 0:
            return {"error": "没有处理任何批次"}
        
        success_rate = self.metrics.successful_batches / self.metrics.total_batches
        avg_candidates_per_batch = (
            sum(self.metrics.candidates_per_batch) / len(self.metrics.candidates_per_batch)
            if self.metrics.candidates_per_batch else 0
        )
        
        return {
            "summary": {
                "total_batches": self.metrics.total_batches,
                "successful_batches": self.metrics.successful_batches,
                "success_rate": success_rate,
                "total_processing_time": self.metrics.total_processing_time,
                "stop_reason": self.metrics.stop_condition_triggered
            },
            "performance": {
                "total_api_calls": self.metrics.total_api_calls,
                "avg_candidates_per_batch": avg_candidates_per_batch,
                "candidates_per_batch": self.metrics.candidates_per_batch,
                "api_calls_per_second": (
                    self.metrics.total_api_calls / self.metrics.total_processing_time
                    if self.metrics.total_processing_time > 0 else 0
                )
            },
            "config": {
                "batch_size": self.config.batch_size,
                "max_sources": self.config.max_sources,
                "stop_multiplier": self.config.stop_multiplier,
                "enable_early_stop": self.config.enable_early_stop
            }
        }
    
    def get_statistics(self) -> dict:
        """获取筛选统计信息"""
        return {
            "config": {
                "batch_size": self.config.batch_size,
                "max_sources": self.config.max_sources,
                "stop_multiplier": self.config.stop_multiplier,
                "enable_early_stop": self.config.enable_early_stop
            },
            "metrics": {
                "total_batches": self.metrics.total_batches,
                "successful_batches": self.metrics.successful_batches,
                "total_api_calls": self.metrics.total_api_calls,
                "total_processing_time": self.metrics.total_processing_time,
                "stop_condition_triggered": self.metrics.stop_condition_triggered
            }
        }


def create_dynamic_funnel_selector() -> DynamicFunnelSelector:
    """
    创建动态漏斗筛选器实例的工厂函数
    
    Returns:
        配置好的动态漏斗筛选器实例
    """
    from config.config_loader import create_dynamic_funnel_config
    
    config = create_dynamic_funnel_config()
    return DynamicFunnelSelector(config)