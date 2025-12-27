"""
管道编排器
协调动态漏斗和增强组件的集成，实现新旧系统的无缝切换
"""

import logging
import time
from typing import List, Optional, Dict, Any
from enum import Enum

from core.contracts import (
    PipelineConfig, FunnelResult, EnhancedDecisionResult, 
    RecoveryAction, SeriesInfo
)
from core.enhanced_component_factory import (
    EnhancedComponentFactory, ErrorRecoveryManager,
    ComponentValidationError, DependencyInjectionError
)
from io_layer.dynamic_funnel_selector import DynamicFunnelSelector
from io_layer.source_manager import create_source_manager
from io_layer.context_builder import create_context_builder
from core.llm_client import create_llm_client
from core.decision_engine import create_decision_maker
from executor.quark_saver import create_quark_saver, save_files_sync

logger = logging.getLogger(__name__)


class PipelineMode(Enum):
    """管道模式枚举"""
    STATIC = "static"
    DYNAMIC = "dynamic"
    AUTO = "auto"


class PipelineOrchestrator:
    """
    管道编排器
    
    核心功能：
    1. 动态/静态模式切换
    2. 自动降级机制
    3. 向后兼容性
    4. 模式切换事件记录
    """
    
    def __init__(self, config: PipelineConfig):
        """
        初始化管道编排器
        
        Args:
            config: 管道配置
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 当前运行模式
        self.current_mode = PipelineMode.DYNAMIC if config.enable_dynamic_mode else PipelineMode.STATIC
        
        # 组件实例
        self.dynamic_funnel_selector: Optional[DynamicFunnelSelector] = None
        self.enhanced_component_factory: Optional[EnhancedComponentFactory] = None
        
        # 静态组件 (降级时使用)
        self.source_manager = None
        self.context_builder = None
        self.llm_client = None
        self.basic_decision_maker = None
        self.quark_saver = None
        
        # 统计信息
        self.orchestrator_statistics = {
            "total_requests": 0,
            "dynamic_mode_requests": 0,
            "static_mode_requests": 0,
            "fallback_events": 0,
            "mode_switches": 0
        }
        
        self.logger.info(f"🎭 管道编排器初始化:")
        self.logger.info(f"   当前模式: {self.current_mode.value}")
        self.logger.info(f"   降级启用: {config.fallback_to_static}")
        
        # 初始化组件
        self._initialize_components()
    
    def _initialize_components(self):
        """初始化管道组件"""
        try:
            if self.current_mode == PipelineMode.DYNAMIC:
                self._initialize_dynamic_components()
            
            # 始终初始化静态组件作为降级备份
            self._initialize_static_components()
            
        except Exception as e:
            self.logger.error(f"❌ 组件初始化失败: {e}")
            if self.config.fallback_to_static:
                self.logger.warning("🔄 降级到静态模式")
                self._fallback_to_static("组件初始化失败")
            else:
                raise
    
    def _initialize_dynamic_components(self):
        """初始化动态组件"""
        self.logger.info("🚀 初始化动态组件...")
        
        try:
            # 创建动态漏斗筛选器
            from io_layer.dynamic_funnel_selector import create_dynamic_funnel_selector
            self.dynamic_funnel_selector = create_dynamic_funnel_selector()
            
            # 创建增强组件工厂
            from core.enhanced_component_factory import create_enhanced_component_factory
            self.enhanced_component_factory = create_enhanced_component_factory()
            
            self.logger.info("✅ 动态组件初始化完成")
            
        except (ComponentValidationError, DependencyInjectionError) as e:
            self.logger.error(f"❌ 动态组件初始化失败: {e}")
            
            if self.config.fallback_to_static:
                recovery_action = ErrorRecoveryManager.handle_factory_error(e, "dynamic_components")
                recovery_message = ErrorRecoveryManager.get_fallback_message(recovery_action)
                
                self.logger.warning(f"🔄 {recovery_message}")
                self._fallback_to_static("动态组件初始化失败")
            else:
                raise
    
    def _initialize_static_components(self):
        """初始化静态组件"""
        self.logger.info("🔧 初始化静态组件...")
        
        try:
            self.source_manager = create_source_manager()
            self.context_builder = create_context_builder()
            self.llm_client = create_llm_client()
            self.basic_decision_maker = create_decision_maker()
            self.quark_saver = create_quark_saver()
            
            self.logger.info("✅ 静态组件初始化完成")
            
        except Exception as e:
            self.logger.error(f"❌ 静态组件初始化失败: {e}")
            raise
    
    async def process_series_enhanced(self, 
                                    series_title: str,
                                    source_urls: List[str],
                                    target_folder: Optional[str] = None) -> Dict[str, Any]:
        """
        增强版剧集处理流程
        
        Args:
            series_title: 剧集标题
            source_urls: 源链接列表
            target_folder: 目标文件夹名称
            
        Returns:
            处理结果
        """
        start_time = time.time()
        self.orchestrator_statistics["total_requests"] += 1
        
        self.logger.info(f"🎭 开始增强处理: {series_title} (模式: {self.current_mode.value})")
        
        try:
            if self.current_mode == PipelineMode.DYNAMIC:
                return await self._process_with_dynamic_mode(
                    series_title, source_urls, target_folder, start_time
                )
            else:
                return await self._process_with_static_mode(
                    series_title, source_urls, target_folder, start_time
                )
                
        except Exception as e:
            self.logger.error(f"❌ 处理异常: {e}")
            
            # 尝试降级处理
            if (self.current_mode == PipelineMode.DYNAMIC and 
                self.config.fallback_to_static):
                
                self.logger.warning("🔄 尝试降级到静态模式处理")
                self._fallback_to_static("处理异常")
                
                return await self._process_with_static_mode(
                    series_title, source_urls, target_folder, start_time
                )
            else:
                execution_time = time.time() - start_time
                return {
                    "success": False,
                    "error": str(e),
                    "execution_time": execution_time,
                    "mode": self.current_mode.value
                }
    
    async def _process_with_dynamic_mode(self, 
                                       series_title: str,
                                       source_urls: List[str],
                                       target_folder: Optional[str],
                                       start_time: float) -> Dict[str, Any]:
        """
        使用动态模式处理
        
        Args:
            series_title: 剧集标题
            source_urls: 源链接列表
            target_folder: 目标文件夹
            start_time: 开始时间
            
        Returns:
            处理结果
        """
        self.orchestrator_statistics["dynamic_mode_requests"] += 1
        self.logger.info("🚀 使用动态模式处理")
        
        try:
            # 步骤1: 快速状态查询
            from io_layer.state_provider import create_state_provider
            state_provider = create_state_provider()
            series_state = state_provider.get_state_with_cache(series_title)
            
            # 步骤2: 源头竞价 (使用静态组件)
            sources_dict = {series_title: [f"源{i+1},{url}" for i, url in enumerate(source_urls)]}
            ranked_sources = self.source_manager.rank_sources(sources_dict, len(series_state.get_missing_episodes()))
            
            if not ranked_sources:
                return {
                    "success": False,
                    "error": "没有有效的源链接",
                    "execution_time": time.time() - start_time,
                    "mode": "dynamic"
                }
            
            # 步骤3: 动态漏斗筛选
            funnel_result = await self.dynamic_funnel_selector.select_with_funnel(
                ranked_sources, series_state
            )
            
            if not funnel_result.candidate_files:
                return {
                    "success": False,
                    "error": "动态漏斗未找到候选文件",
                    "execution_time": time.time() - start_time,
                    "mode": "dynamic",
                    "funnel_result": funnel_result
                }
            
            # 步骤4: LLM解析
            parsed_results = self.llm_client.parse_files(funnel_result.candidate_files)
            
            if not parsed_results:
                return {
                    "success": False,
                    "error": "LLM解析失败",
                    "execution_time": time.time() - start_time,
                    "mode": "dynamic"
                }
            
            # 步骤5: 增强决策
            enhanced_decision_maker = self.enhanced_component_factory.create_enhanced_decision_maker()
            
            # 创建分析上下文
            from core.contracts import AnalysisContext
            context = AnalysisContext(
                standard_title=series_title,
                candidates=funnel_result.candidate_files,
                state=series_state
            )
            
            # 创建剧集信息
            series_info = SeriesInfo(
                title=series_title,
                season=1,  # 默认值，可以从解析结果中获取
                total_episodes=len(series_state.tmdb_total_aired)
            )
            
            enhanced_result = enhanced_decision_maker.make_enhanced_decision(
                context, parsed_results, series_info
            )
            
            if not enhanced_result or not enhanced_result.selected_files:
                return {
                    "success": False,
                    "error": "增强决策未选中任何文件",
                    "execution_time": time.time() - start_time,
                    "mode": "dynamic"
                }
            
            # 步骤6: 批量转存
            if not target_folder:
                target_folder = f"{series_title}_智能下载"
            
            save_result = save_files_sync(enhanced_result.selected_files, target_folder)
            
            execution_time = time.time() - start_time
            
            return {
                "success": True,
                "series_title": series_title,
                "mode": "dynamic",
                "funnel_result": {
                    "selected_sources": len(funnel_result.selected_sources),
                    "candidate_files": len(funnel_result.candidate_files),
                    "stop_reason": funnel_result.stop_reason
                },
                "enhanced_result": {
                    "total_candidates": enhanced_result.total_candidates,
                    "selected_files": len(enhanced_result.selected_files),
                    "consistency_filtered": enhanced_result.consistency_filtered,
                    "renamed_files": enhanced_result.renamed_files
                },
                "save_result": {
                    "total_files": save_result.total_files,
                    "success_count": save_result.success_count,
                    "success_rate": save_result.success_rate
                },
                "execution_time": execution_time
            }
            
        except Exception as e:
            self.logger.error(f"❌ 动态模式处理失败: {e}")
            raise
    
    async def _process_with_static_mode(self, 
                                      series_title: str,
                                      source_urls: List[str],
                                      target_folder: Optional[str],
                                      start_time: float) -> Dict[str, Any]:
        """
        使用静态模式处理 (降级模式)
        
        Args:
            series_title: 剧集标题
            source_urls: 源链接列表
            target_folder: 目标文件夹
            start_time: 开始时间
            
        Returns:
            处理结果
        """
        self.orchestrator_statistics["static_mode_requests"] += 1
        self.logger.info("🔧 使用静态模式处理")
        
        try:
            # 使用原有的静态处理逻辑
            from io_layer.state_provider import create_state_provider
            state_provider = create_state_provider()
            series_state = state_provider.get_state_with_cache(series_title)
            
            # 源头竞价
            sources_dict = {series_title: [f"源{i+1},{url}" for i, url in enumerate(source_urls)]}
            ranked_sources = self.source_manager.rank_sources(sources_dict, len(series_state.get_missing_episodes()))
            
            if not ranked_sources:
                return {
                    "success": False,
                    "error": "没有有效的源链接",
                    "execution_time": time.time() - start_time,
                    "mode": "static"
                }
            
            # 上下文构建
            sources_for_context = [{"title": s.title, "url": s.url} for s in ranked_sources]
            context = self.context_builder.build_context(sources_for_context, series_title)
            
            if not context or not context.candidates:
                return {
                    "success": False,
                    "error": "上下文构建失败",
                    "execution_time": time.time() - start_time,
                    "mode": "static"
                }
            
            # LLM解析
            parsed_results = self.llm_client.parse_files(context.candidates)
            
            if not parsed_results:
                return {
                    "success": False,
                    "error": "LLM解析失败",
                    "execution_time": time.time() - start_time,
                    "mode": "static"
                }
            
            # 基础决策
            selected_files = self.basic_decision_maker.decide(context, parsed_results)
            
            if not selected_files:
                return {
                    "success": False,
                    "error": "决策引擎未选中任何文件",
                    "execution_time": time.time() - start_time,
                    "mode": "static"
                }
            
            # 批量转存
            if not target_folder:
                target_folder = f"{series_title}_智能下载"
            
            save_result = save_files_sync(selected_files, target_folder)
            
            execution_time = time.time() - start_time
            
            return {
                "success": True,
                "series_title": series_title,
                "mode": "static",
                "source_count": len(ranked_sources),
                "candidate_count": len(context.candidates),
                "selected_count": len(selected_files),
                "save_result": {
                    "total_files": save_result.total_files,
                    "success_count": save_result.success_count,
                    "success_rate": save_result.success_rate
                },
                "execution_time": execution_time
            }
            
        except Exception as e:
            self.logger.error(f"❌ 静态模式处理失败: {e}")
            raise
    
    def _fallback_to_static(self, reason: str):
        """
        降级到静态模式
        
        Args:
            reason: 降级原因
        """
        if self.current_mode != PipelineMode.STATIC:
            self.logger.warning(f"🔄 管道模式切换: {self.current_mode.value} -> static")
            self.logger.warning(f"   降级原因: {reason}")
            
            self.current_mode = PipelineMode.STATIC
            self.orchestrator_statistics["fallback_events"] += 1
            self.orchestrator_statistics["mode_switches"] += 1
            
            # 记录模式切换事件
            self._log_mode_switch_event("static", reason)
    
    def switch_mode(self, new_mode: PipelineMode, reason: str = "手动切换") -> bool:
        """
        手动切换管道模式
        
        Args:
            new_mode: 新模式
            reason: 切换原因
            
        Returns:
            切换是否成功
        """
        if new_mode == self.current_mode:
            self.logger.info(f"模式已经是 {new_mode.value}，无需切换")
            return True
        
        try:
            if new_mode == PipelineMode.DYNAMIC:
                # 尝试初始化动态组件
                if not self.dynamic_funnel_selector or not self.enhanced_component_factory:
                    self._initialize_dynamic_components()
            
            old_mode = self.current_mode
            self.current_mode = new_mode
            self.orchestrator_statistics["mode_switches"] += 1
            
            self.logger.info(f"🔄 管道模式切换成功: {old_mode.value} -> {new_mode.value}")
            self.logger.info(f"   切换原因: {reason}")
            
            self._log_mode_switch_event(new_mode.value, reason)
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 模式切换失败: {e}")
            return False
    
    def _log_mode_switch_event(self, new_mode: str, reason: str):
        """记录模式切换事件"""
        event = {
            "timestamp": time.time(),
            "old_mode": self.current_mode.value if hasattr(self, 'current_mode') else "unknown",
            "new_mode": new_mode,
            "reason": reason
        }
        
        # 这里可以扩展为写入审计日志文件
        self.logger.info(f"📝 模式切换事件记录: {event}")
    
    def get_system_status(self) -> Dict[str, Any]:
        """
        获取系统状态
        
        Returns:
            系统状态信息
        """
        status = {
            "current_mode": self.current_mode.value,
            "config": {
                "enable_dynamic_mode": self.config.enable_dynamic_mode,
                "fallback_to_static": self.config.fallback_to_static
            },
            "components": {
                "dynamic_funnel_selector": self.dynamic_funnel_selector is not None,
                "enhanced_component_factory": self.enhanced_component_factory is not None,
                "static_components_ready": all([
                    self.source_manager is not None,
                    self.context_builder is not None,
                    self.llm_client is not None,
                    self.basic_decision_maker is not None,
                    self.quark_saver is not None
                ])
            },
            "statistics": self.orchestrator_statistics
        }
        
        # 添加组件详细状态
        if self.dynamic_funnel_selector:
            status["dynamic_funnel_status"] = self.dynamic_funnel_selector.get_statistics()
        
        if self.enhanced_component_factory:
            status["enhanced_factory_status"] = self.enhanced_component_factory.get_statistics()
        
        return status
    
    def get_statistics(self) -> dict:
        """获取编排器统计信息"""
        return {
            "current_mode": self.current_mode.value,
            "statistics": self.orchestrator_statistics,
            "config": {
                "enable_dynamic_mode": self.config.enable_dynamic_mode,
                "fallback_to_static": self.config.fallback_to_static
            }
        }


def create_pipeline_orchestrator() -> PipelineOrchestrator:
    """
    创建管道编排器实例的工厂函数
    
    Returns:
        配置好的管道编排器实例
    """
    from config.config_loader import create_pipeline_config
    
    pipeline_config = create_pipeline_config()
    return PipelineOrchestrator(pipeline_config)