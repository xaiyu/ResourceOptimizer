"""
增强的决策引擎 v4.1
集成一致性检查和标准化命名功能
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from core.contracts import (
    AnalysisContext, SelectedFile, RawFileNode, VideoMeta, SeriesInfo,
    DynamicFunnelConfig, ConsistencyConfig, NamingConfig
)
from core.decision_engine import DecisionMaker
from core.consistency_checker import ConsistencyChecker
from core.naming_generator import StandardizedNamingGenerator


@dataclass
class EnhancedDecisionResult:
    """增强的决策结果"""
    selected_files: List[SelectedFile]
    series_title: str
    total_candidates: int
    consistency_filtered: int
    renamed_files: int
    statistics: Dict[str, Any]


class EnhancedDecisionMaker(DecisionMaker):
    """
    增强的决策引擎
    
    在原有决策逻辑基础上增加：
    1. 一致性洗码检查
    2. 标准化命名生成
    3. 增强的统计信息
    """
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        
        # v4.1 增强组件
        self.consistency_checker: Optional[ConsistencyChecker] = None
        self.naming_generator: Optional[StandardizedNamingGenerator] = None
    
    def set_enhanced_components(self, 
                               consistency_checker: ConsistencyChecker,
                               naming_generator: StandardizedNamingGenerator):
        """设置增强组件"""
        self.consistency_checker = consistency_checker
        self.naming_generator = naming_generator
        self.logger.info("🔧 增强组件已配置")
    
    async def make_enhanced_decision(self, 
                                   context: AnalysisContext,
                                   series_info: SeriesInfo) -> Optional[EnhancedDecisionResult]:
        """
        执行增强的决策流程
        
        Args:
            context: 分析上下文
            series_info: 剧集信息
            
        Returns:
            增强的决策结果
        """
        self.logger.info(f"🧠 开始增强决策: {context.standard_title}")
        
        # 统计信息
        stats = {
            "input_candidates": len(context.candidates),
            "consistency_filtered": 0,
            "renamed_files": 0,
            "processing_stages": []
        }
        
        try:
            # 阶段1: 原有决策逻辑
            self.logger.info("📊 阶段1: 基础决策分析")
            basic_result = self.decide(context)
            
            if not basic_result or not basic_result.selected_files:
                self.logger.warning("❌ 基础决策未选中任何文件")
                return None
            
            stats["processing_stages"].append("basic_decision")
            selected_files = basic_result.selected_files.copy()
            
            # 阶段2: 一致性洗码 (v4.1)
            if self.consistency_checker:
                self.logger.info("🔍 阶段2: 一致性洗码检查")
                
                # 提取文件和元数据
                file_nodes = [sf.file_node for sf in selected_files]
                video_metas = [sf.video_meta for sf in selected_files]
                
                # 执行一致性检查
                consistent_files = self.consistency_checker.check_size_consistency(
                    file_nodes, video_metas
                )
                
                # 更新选中文件列表
                consistent_selected = []
                for selected_file in selected_files:
                    if selected_file.file_node in consistent_files:
                        consistent_selected.append(selected_file)
                
                stats["consistency_filtered"] = len(selected_files) - len(consistent_selected)
                selected_files = consistent_selected
                stats["processing_stages"].append("consistency_check")
                
                self.logger.info(f"🔍 一致性检查: {len(basic_result.selected_files)} -> {len(selected_files)}")
            
            # 阶段3: 标准化命名 (v4.1)
            if self.naming_generator:
                self.logger.info("🏷️ 阶段3: 标准化命名生成")
                
                renamed_count = 0
                for selected_file in selected_files:
                    # 生成标准化文件名
                    target_filename = self.naming_generator.generate_filename(
                        series_info, selected_file.file_node, selected_file.video_meta
                    )
                    
                    # 更新选中文件
                    selected_file.target_filename = target_filename
                    selected_file.rename_metadata = {
                        "original_filename": selected_file.file_node.filename,
                        "generated_at": "enhanced_decision_v4.1"
                    }
                    
                    renamed_count += 1
                
                stats["renamed_files"] = renamed_count
                stats["processing_stages"].append("standardized_naming")
                
                self.logger.info(f"🏷️ 标准化命名: {renamed_count} 个文件")
            
            # 构建增强结果
            enhanced_result = EnhancedDecisionResult(
                selected_files=selected_files,
                series_title=context.standard_title,
                total_candidates=stats["input_candidates"],
                consistency_filtered=stats["consistency_filtered"],
                renamed_files=stats["renamed_files"],
                statistics=stats
            )
            
            self.logger.info(f"✅ 增强决策完成:")
            self.logger.info(f"   输入候选: {stats['input_candidates']} 个")
            self.logger.info(f"   最终选中: {len(selected_files)} 个")
            self.logger.info(f"   一致性过滤: {stats['consistency_filtered']} 个")
            self.logger.info(f"   标准化命名: {stats['renamed_files']} 个")
            
            return enhanced_result
            
        except Exception as e:
            self.logger.error(f"❌ 增强决策失败: {e}")
            return None
    
    def _add_consistency_scores(self, selected_files: List[SelectedFile]):
        """为选中文件添加一致性评分"""
        if not selected_files:
            return
        
        # 计算文件大小的中位数
        sizes = [sf.file_node.size for sf in selected_files]
        if not sizes:
            return
        
        import statistics
        median_size = statistics.median(sizes)
        
        # 为每个文件计算一致性评分
        for selected_file in selected_files:
            if median_size > 0:
                deviation = abs(selected_file.file_node.size - median_size) / median_size
                consistency_score = max(0.0, 1.0 - deviation)
                selected_file.consistency_score = consistency_score
    
    def get_enhanced_statistics(self) -> Dict[str, Any]:
        """获取增强统计信息"""
        base_stats = super().get_statistics()
        
        enhanced_stats = {
            "version": "v4.1_enhanced",
            "base_engine": base_stats,
            "enhanced_features": {
                "consistency_checker": self.consistency_checker is not None,
                "naming_generator": self.naming_generator is not None
            }
        }
        
        if self.consistency_checker:
            enhanced_stats["consistency_config"] = self.consistency_checker.get_statistics()
        
        if self.naming_generator:
            enhanced_stats["naming_config"] = self.naming_generator.get_statistics()
        
        return enhanced_stats