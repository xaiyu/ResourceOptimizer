"""
停止条件评估器
实现智能停止逻辑，优化动态漏斗的性能
"""

import logging
from typing import List, Set
from dataclasses import dataclass

from core.contracts import (
    StopDecision, StopConditionConfig, BatchResult, 
    RankedSource, FunnelContext
)

logger = logging.getLogger(__name__)


class StopConditionEvaluator:
    """
    停止条件评估器
    
    核心功能：
    1. 候选数量阈值检查
    2. 连续无效批次检查  
    3. 源评分阈值检查
    4. 智能停止决策
    """
    
    def __init__(self, config: StopConditionConfig):
        """
        初始化停止条件评估器
        
        Args:
            config: 停止条件配置
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        self.logger.info(f"停止条件评估器初始化:")
        self.logger.info(f"  候选倍数阈值: {config.candidate_multiplier}")
        self.logger.info(f"  质量阈值批次: {config.quality_threshold_batches}")
        self.logger.info(f"  评分阈值: {config.score_threshold}")
        self.logger.info(f"  提前停止: {config.enable_early_stop}")
    
    def should_stop(self, 
                   current_candidates: int,
                   missing_episodes: Set[int],
                   batch_history: List[BatchResult],
                   remaining_sources: List[RankedSource]) -> StopDecision:
        """
        评估是否应该停止处理
        
        Args:
            current_candidates: 当前候选文件数量
            missing_episodes: 缺失集数
            batch_history: 批次历史记录
            remaining_sources: 剩余源列表
            
        Returns:
            停止决策
        """
        if not self.config.enable_early_stop:
            # 如果禁用提前停止，只在达到最大源数时停止
            if not remaining_sources:
                return StopDecision(
                    should_stop=True,
                    reason="已处理所有可用源",
                    confidence=1.0
                )
            return StopDecision(
                should_stop=False,
                reason="提前停止已禁用",
                confidence=0.0
            )
        
        # 1. 候选数量阈值检查
        candidate_decision = self._check_candidate_threshold(
            current_candidates, len(missing_episodes)
        )
        if candidate_decision.should_stop:
            return candidate_decision
        
        # 2. 连续无效批次检查
        quality_decision = self._check_quality_threshold(batch_history)
        if quality_decision.should_stop:
            return quality_decision
        
        # 3. 源评分阈值检查
        score_decision = self._check_score_threshold(remaining_sources)
        if score_decision.should_stop:
            return score_decision
        
        # 4. 检查是否还有剩余源
        if not remaining_sources:
            return StopDecision(
                should_stop=True,
                reason="已处理所有可用源",
                confidence=1.0
            )
        
        # 继续处理
        return StopDecision(
            should_stop=False,
            reason="未达到任何停止条件",
            confidence=0.0
        )
    
    def _check_candidate_threshold(self, 
                                 current_candidates: int, 
                                 missing_count: int) -> StopDecision:
        """
        检查候选数量阈值
        
        Args:
            current_candidates: 当前候选数量
            missing_count: 缺失集数
            
        Returns:
            停止决策
        """
        # 修复逻辑漏洞：处理 missing_count 为 0 的情况
        # 在洗版/升级画质场景下，不应该立即停止
        min_candidates = getattr(self.config, 'min_candidates', 5)  # 默认最小5个候选
        
        if missing_count == 0:
            # 洗版/升级画质模式：使用最小候选数作为目标
            target_candidates = min_candidates
            self.logger.info(f"🔄 洗版/升级画质模式，目标候选数: {target_candidates}")
        else:
            # 正常模式：使用缺失集数计算目标
            raw_target = int(missing_count * self.config.candidate_multiplier)
            target_candidates = max(raw_target, min_candidates)
        
        if current_candidates >= target_candidates:
            confidence = min(1.0, current_candidates / target_candidates)
            
            self.logger.info(f"🎯 候选数量达到阈值:")
            self.logger.info(f"   当前候选: {current_candidates}")
            self.logger.info(f"   目标候选: {target_candidates}")
            if missing_count > 0:
                self.logger.info(f"   覆盖率: {current_candidates/missing_count:.1f}x")
            else:
                self.logger.info(f"   洗版模式覆盖率: {current_candidates}/{target_candidates}")
            
            return StopDecision(
                should_stop=True,
                reason=f"候选数量达到目标 ({current_candidates}/{target_candidates})",
                confidence=confidence
            )
        
        return StopDecision(
            should_stop=False,
            reason=f"候选数量不足 ({current_candidates}/{target_candidates})",
            confidence=0.0
        )
    
    def _check_quality_threshold(self, batch_history: List[BatchResult]) -> StopDecision:
        """
        检查连续无效批次阈值
        
        Args:
            batch_history: 批次历史记录
            
        Returns:
            停止决策
        """
        if len(batch_history) < self.config.quality_threshold_batches:
            return StopDecision(
                should_stop=False,
                reason="批次数量不足以评估质量阈值",
                confidence=0.0
            )
        
        # 检查最近的批次
        recent_batches = batch_history[-self.config.quality_threshold_batches:]
        
        # 计算连续无效批次数
        consecutive_empty = 0
        for batch in reversed(recent_batches):
            if batch.candidates_found == 0:
                consecutive_empty += 1
            else:
                break
        
        if consecutive_empty >= self.config.quality_threshold_batches:
            confidence = min(1.0, consecutive_empty / self.config.quality_threshold_batches)
            
            self.logger.warning(f"🚫 连续无效批次达到阈值:")
            self.logger.warning(f"   连续无效批次: {consecutive_empty}")
            self.logger.warning(f"   阈值: {self.config.quality_threshold_batches}")
            
            return StopDecision(
                should_stop=True,
                reason=f"连续 {consecutive_empty} 个批次无有效候选",
                confidence=confidence
            )
        
        return StopDecision(
            should_stop=False,
            reason=f"质量阈值未达到 (连续无效: {consecutive_empty}/{self.config.quality_threshold_batches})",
            confidence=0.0
        )
    
    def _check_score_threshold(self, remaining_sources: List[RankedSource]) -> StopDecision:
        """
        检查源评分阈值
        
        Args:
            remaining_sources: 剩余源列表
            
        Returns:
            停止决策
        """
        if not remaining_sources:
            return StopDecision(
                should_stop=True,
                reason="没有剩余源",
                confidence=1.0
            )
        
        # 计算剩余源的平均评分
        total_score = sum(source.score for source in remaining_sources)
        avg_score = total_score / len(remaining_sources)
        
        if avg_score < self.config.score_threshold:
            confidence = max(0.0, 1.0 - (avg_score / self.config.score_threshold))
            
            self.logger.warning(f"📉 剩余源评分过低:")
            self.logger.warning(f"   平均评分: {avg_score:.1f}")
            self.logger.warning(f"   评分阈值: {self.config.score_threshold}")
            self.logger.warning(f"   剩余源数: {len(remaining_sources)}")
            
            return StopDecision(
                should_stop=True,
                reason=f"剩余源平均评分过低 ({avg_score:.1f} < {self.config.score_threshold})",
                confidence=confidence
            )
        
        return StopDecision(
            should_stop=False,
            reason=f"源评分合格 (平均: {avg_score:.1f} >= {self.config.score_threshold})",
            confidence=0.0
        )
    
    def get_stop_reason_summary(self, 
                              current_candidates: int,
                              missing_episodes: Set[int],
                              batch_history: List[BatchResult],
                              remaining_sources: List[RankedSource]) -> str:
        """
        获取停止原因摘要
        
        Args:
            current_candidates: 当前候选数量
            missing_episodes: 缺失集数
            batch_history: 批次历史
            remaining_sources: 剩余源
            
        Returns:
            停止原因摘要
        """
        decision = self.should_stop(
            current_candidates, missing_episodes, batch_history, remaining_sources
        )
        
        summary_parts = [
            f"停止决策: {'是' if decision.should_stop else '否'}",
            f"原因: {decision.reason}",
            f"置信度: {decision.confidence:.2f}"
        ]
        
        if decision.should_stop:
            summary_parts.extend([
                f"当前候选: {current_candidates}",
                f"缺失集数: {len(missing_episodes)}",
                f"处理批次: {len(batch_history)}",
                f"剩余源数: {len(remaining_sources)}"
            ])
        
        return " | ".join(summary_parts)
    
    def get_statistics(self) -> dict:
        """获取评估器统计信息"""
        return {
            "config": {
                "candidate_multiplier": self.config.candidate_multiplier,
                "quality_threshold_batches": self.config.quality_threshold_batches,
                "score_threshold": self.config.score_threshold,
                "enable_early_stop": self.config.enable_early_stop
            }
        }


def create_stop_condition_evaluator() -> StopConditionEvaluator:
    """
    创建停止条件评估器实例的工厂函数
    
    Returns:
        配置好的停止条件评估器实例
    """
    from config.config_loader import create_dynamic_funnel_config
    
    funnel_config = create_dynamic_funnel_config()
    return StopConditionEvaluator(funnel_config.stop_config)