"""
增强的决策引擎 v4.1+
集成一致性检查和标准化命名功能
确保自动执行增强功能
"""

import logging
from typing import List, Optional, Dict, Any

from core.contracts import (
    AnalysisContext, SelectedFile, RawFileNode, VideoMeta, SeriesInfo,
    DynamicFunnelConfig, ConsistencyConfig, NamingConfig, EnhancedDecisionResult
)
from core.decision_engine import DecisionMaker
from core.consistency_checker import ConsistencyChecker
from core.naming_generator import StandardizedNamingGenerator


class EnhancedDecisionMaker(DecisionMaker):
    """
    增强的决策引擎
    
    在原有决策逻辑基础上增加：
    1. 一致性洗码检查 - 自动执行
    2. 标准化命名生成 - 自动执行
    3. 增强的统计信息
    4. 错误恢复机制
    """
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        
        # v4.1+ 增强组件
        self.consistency_checker: Optional[ConsistencyChecker] = None
        self.naming_generator: Optional[StandardizedNamingGenerator] = None
        
        # 统计信息
        self.decision_statistics = {
            "total_decisions": 0,
            "consistency_checks_performed": 0,
            "naming_generations_performed": 0,
            "consistency_filtered_files": 0,
            "renamed_files": 0
        }
        
        self.logger.info("🧠 增强决策引擎初始化完成")
    
    def set_enhanced_components(self, 
                               consistency_checker: ConsistencyChecker,
                               naming_generator: StandardizedNamingGenerator):
        """
        设置增强组件
        
        Args:
            consistency_checker: 一致性检查器
            naming_generator: 命名生成器
        """
        self.consistency_checker = consistency_checker
        self.naming_generator = naming_generator
        self.logger.info("🔧 增强组件已配置:")
        self.logger.info(f"   一致性检查器: {consistency_checker is not None}")
        self.logger.info(f"   命名生成器: {naming_generator is not None}")
    
    def decide(self, context: AnalysisContext, parsed_results: List[VideoMeta] = None) -> List[SelectedFile]:
        """
        增强决策函数 - 自动执行一致性检查和标准化命名
        
        Args:
            context: 分析上下文
            parsed_results: LLM解析结果列表 (可选，兼容旧接口)
            
        Returns:
            选中的文件列表
        """
        self.decision_statistics["total_decisions"] += 1
        
        # 如果没有提供parsed_results，需要从其他地方获取或调用LLM解析
        if parsed_results is None:
            self.logger.warning("未提供解析结果，使用基础决策逻辑")
            return super().decide(context, [])
        
        self.logger.info(f"🧠 开始增强决策: {context.standard_title}")
        
        # 阶段1: 基础决策逻辑
        self.logger.info("📊 阶段1: 基础决策分析")
        basic_selected_files = super().decide(context, parsed_results)
        
        if not basic_selected_files:
            self.logger.warning("❌ 基础决策未选中任何文件")
            return []
        
        self.logger.info(f"基础决策选中 {len(basic_selected_files)} 个文件")
        
        # 阶段2: 一致性洗码检查 (自动执行)
        consistent_files = self._auto_consistency_check(basic_selected_files)
        
        # 阶段3: 标准化命名生成 (自动执行)
        final_files = self._auto_naming_generation(consistent_files, context.standard_title)
        
        self.logger.info(f"✅ 增强决策完成: 最终选中 {len(final_files)} 个文件")
        
        return final_files
    
    def make_enhanced_decision(self, 
                             context: AnalysisContext,
                             parsed_results: List[VideoMeta],
                             series_info: SeriesInfo) -> Optional[EnhancedDecisionResult]:
        """
        执行增强的决策流程 - 返回详细结果
        
        Args:
            context: 分析上下文
            parsed_results: LLM解析结果
            series_info: 剧集信息
            
        Returns:
            增强的决策结果
        """
        self.logger.info(f"🧠 开始增强决策流程: {context.standard_title}")
        
        # 统计信息
        stats = {
            "input_candidates": len(context.candidates),
            "input_parsed_results": len(parsed_results),
            "consistency_filtered": 0,
            "renamed_files": 0,
            "processing_stages": []
        }
        
        try:
            # 执行决策
            selected_files = self.decide(context, parsed_results)
            
            if not selected_files:
                self.logger.warning("❌ 增强决策未选中任何文件")
                return None
            
            # 更新统计信息
            stats["consistency_filtered"] = self.decision_statistics.get("consistency_filtered_files", 0)
            stats["renamed_files"] = self.decision_statistics.get("renamed_files", 0)
            stats["processing_stages"] = ["basic_decision", "consistency_check", "standardized_naming"]
            
            # 构建增强结果
            enhanced_result = EnhancedDecisionResult(
                selected_files=selected_files,
                series_title=context.standard_title,
                total_candidates=stats["input_candidates"],
                consistency_filtered=stats["consistency_filtered"],
                renamed_files=stats["renamed_files"],
                statistics=stats
            )
            
            self.logger.info(f"✅ 增强决策流程完成:")
            self.logger.info(f"   输入候选: {stats['input_candidates']} 个")
            self.logger.info(f"   最终选中: {len(selected_files)} 个")
            self.logger.info(f"   一致性过滤: {stats['consistency_filtered']} 个")
            self.logger.info(f"   标准化命名: {stats['renamed_files']} 个")
            
            return enhanced_result
            
        except Exception as e:
            self.logger.error(f"❌ 增强决策流程失败: {e}")
            return None
    
    def _auto_consistency_check(self, selected_files: List[SelectedFile]) -> List[SelectedFile]:
        """
        自动执行一致性检查
        
        Args:
            selected_files: 初步选择的文件列表
            
        Returns:
            经过一致性检查的文件列表
        """
        if not self.consistency_checker:
            self.logger.warning("⚠️ 一致性检查器未配置，跳过一致性检查")
            return selected_files
        
        self.logger.info("🔍 自动执行一致性检查")
        self.decision_statistics["consistency_checks_performed"] += 1
        
        try:
            # 提取文件和元数据
            file_nodes = [sf.file_node for sf in selected_files]
            video_metas = [sf.video_meta for sf in selected_files]
            
            # 执行一致性检查
            consistent_file_nodes = self.consistency_checker.check_size_consistency(
                file_nodes, video_metas
            )
            
            # 更新选中文件列表
            consistent_selected = []
            for selected_file in selected_files:
                if selected_file.file_node in consistent_file_nodes:
                    # 更新选择原因
                    if selected_file.selection_reason:
                        selected_file.selection_reason += ", 通过一致性检查"
                    else:
                        selected_file.selection_reason = "通过一致性检查"
                    
                    consistent_selected.append(selected_file)
            
            filtered_count = len(selected_files) - len(consistent_selected)
            self.decision_statistics["consistency_filtered_files"] += filtered_count
            
            self.logger.info(f"🔍 一致性检查完成: {len(selected_files)} -> {len(consistent_selected)} "
                           f"(过滤 {filtered_count} 个)")
            
            return consistent_selected
            
        except Exception as e:
            self.logger.error(f"❌ 一致性检查失败: {e}")
            self.logger.warning("降级到原始选择结果")
            return selected_files
    
    def _auto_naming_generation(self, selected_files: List[SelectedFile], 
                              series_title: str) -> List[SelectedFile]:
        """
        自动执行标准化命名生成
        
        Args:
            selected_files: 选中的文件列表
            series_title: 剧集标题
            
        Returns:
            添加了标准文件名的文件列表
        """
        if not self.naming_generator:
            self.logger.warning("⚠️ 命名生成器未配置，跳过标准化命名")
            return selected_files
        
        self.logger.info("🏷️ 自动执行标准化命名生成")
        self.decision_statistics["naming_generations_performed"] += 1
        
        try:
            renamed_count = 0
            
            for selected_file in selected_files:
                # 创建SeriesInfo对象
                series_info = SeriesInfo(
                    title=series_title,
                    season=selected_file.video_meta.season,
                    total_episodes=0  # 这里可以从context获取更多信息
                )
                
                # 生成标准化文件名
                target_filename = self.naming_generator.generate_filename(
                    series_info, selected_file.file_node, selected_file.video_meta
                )
                
                # 更新选中文件
                selected_file.target_filename = target_filename
                selected_file.rename_metadata = {
                    "original_filename": selected_file.file_node.filename,
                    "generated_at": "enhanced_decision_auto",
                    "generator_version": "v4.1+"
                }
                
                # 更新选择原因
                if selected_file.selection_reason:
                    selected_file.selection_reason += ", 标准化命名"
                else:
                    selected_file.selection_reason = "标准化命名"
                
                renamed_count += 1
            
            self.decision_statistics["renamed_files"] += renamed_count
            
            self.logger.info(f"🏷️ 标准化命名完成: {renamed_count} 个文件")
            
            return selected_files
            
        except Exception as e:
            self.logger.error(f"❌ 标准化命名失败: {e}")
            self.logger.warning("保持原始文件名")
            return selected_files
    
    def get_enhanced_statistics(self) -> Dict[str, Any]:
        """获取增强统计信息"""
        base_stats = super().get_statistics()
        
        enhanced_stats = {
            "version": "v4.1+_enhanced",
            "base_engine": base_stats,
            "enhanced_features": {
                "consistency_checker": self.consistency_checker is not None,
                "naming_generator": self.naming_generator is not None
            },
            "decision_statistics": self.decision_statistics.copy()
        }
        
        if self.consistency_checker:
            enhanced_stats["consistency_config"] = self.consistency_checker.get_statistics()
        
        if self.naming_generator:
            enhanced_stats["naming_config"] = self.naming_generator.get_statistics()
        
        return enhanced_stats
    
    def reset_statistics(self) -> None:
        """重置统计信息"""
        self.decision_statistics = {
            "total_decisions": 0,
            "consistency_checks_performed": 0,
            "naming_generations_performed": 0,
            "consistency_filtered_files": 0,
            "renamed_files": 0
        }
        self.logger.info("📊 统计信息已重置")
    
    def is_enhanced_features_available(self) -> bool:
        """检查增强功能是否可用"""
        return (self.consistency_checker is not None and 
                self.naming_generator is not None)
    
    def get_component_status(self) -> Dict[str, Any]:
        """获取组件状态"""
        return {
            "enhanced_features_available": self.is_enhanced_features_available(),
            "components": {
                "consistency_checker": {
                    "available": self.consistency_checker is not None,
                    "enabled": (self.consistency_checker.config.enable 
                              if self.consistency_checker else False)
                },
                "naming_generator": {
                    "available": self.naming_generator is not None,
                    "enabled": (self.naming_generator.config.enable 
                              if self.naming_generator else False)
                }
            },
            "statistics": self.decision_statistics
        }