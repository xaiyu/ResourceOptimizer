"""
智能媒体资源治理系统 v4.1 增强版主程序
集成动态漏斗筛选、一致性洗码、标准化命名功能
"""

import asyncio
import logging
import time
from typing import List, Optional, Dict, Any
from dataclasses import asdict

from config.config_loader import get_config
from core.contracts import (
    RawFileNode, AnalysisContext, SeriesState, SeriesInfo,
    DynamicFunnelConfig, ConsistencyConfig, NamingConfig
)
from io_layer.source_manager import SourceManager
from io_layer.context_builder import ContextBuilder
from io_layer.dynamic_funnel_selector import DynamicFunnelSelector
from core.llm_client import LLMClient
from core.enhanced_decision_engine import EnhancedDecisionMaker
from core.consistency_checker import ConsistencyChecker
from core.naming_generator import StandardizedNamingGenerator
from executor.quark_auto_save_adapter import QuarkAutoSaveAdapter


class EnhancedSmartChaseSystem:
    """
    智能追剧系统 v4.1 增强版
    
    新增功能：
    1. 动态漏斗筛选 - 解决漏选问题
    2. 智能一致性洗码 - 解决品控粗糙
    3. 标准化重命名 - 解决命名混乱
    """
    
    def __init__(self):
        self.config = get_config()
        self.logger = logging.getLogger(__name__)
        
        # 原有组件
        self.source_manager = SourceManager()
        self.context_builder = ContextBuilder()
        self.llm_client = LLMClient()
        
        # v4.1 增强组件
        self._init_enhanced_components()
        
        # 执行器
        self.quark_adapter = QuarkAutoSaveAdapter()
        
        self.logger.info("🚀 智能追剧系统 v4.1 增强版已初始化")
    
    def _init_enhanced_components(self):
        """初始化v4.1增强组件"""
        # 动态漏斗筛选器
        funnel_config = DynamicFunnelConfig(**self.config.get('app.funnel', {}))
        self.funnel_selector = DynamicFunnelSelector(funnel_config)
        
        # 一致性检查器
        consistency_config = ConsistencyConfig(**self.config.get('weights.consistency', {}))
        self.consistency_checker = ConsistencyChecker(consistency_config)
        
        # 标准化命名生成器
        naming_config = NamingConfig(**self.config.get('weights.naming', {}))
        self.naming_generator = StandardizedNamingGenerator(naming_config)
        
        # 增强决策引擎
        self.enhanced_decision_maker = EnhancedDecisionMaker()
        self.enhanced_decision_maker.set_enhanced_components(
            self.consistency_checker, self.naming_generator
        )
        
        self.logger.info("🔧 v4.1 增强组件初始化完成")
    
    async def process_series_enhanced(self, sources: List[dict]) -> List[Dict[str, Any]]:
        """
        增强的剧集处理流程
        
        Args:
            sources: 源列表 [{"title": "...", "url": "..."}]
            
        Returns:
            处理结果列表
        """
        self.logger.info(f"🎬 开始增强处理 {len(sources)} 个资源")
        start_time = time.time()
        
        results = []
        
        try:
            # 阶段1: 源头竞价 (保持不变)
            self.logger.info("🏆 阶段1: 源头竞价")
            ranked_sources = self.source_manager.rank_sources(sources)
            
            if not ranked_sources:
                self.logger.warning("❌ 没有有效的源，处理结束")
                return results
            
            # 按剧集分组处理
            series_groups = self._group_sources_by_series(ranked_sources)
            
            for series_title, series_sources in series_groups.items():
                try:
                    result = await self._process_single_series_enhanced(
                        series_title, series_sources
                    )
                    if result:
                        results.append(result)
                        
                except Exception as e:
                    self.logger.error(f"❌ 处理剧集失败: {series_title} - {e}")
                    continue
            
            # 统计总结
            processing_time = time.time() - start_time
            self.logger.info(f"🎉 增强处理完成:")
            self.logger.info(f"   处理时间: {processing_time:.1f} 秒")
            self.logger.info(f"   成功剧集: {len(results)} 个")
            
            return results
            
        except Exception as e:
            self.logger.error(f"❌ 增强处理失败: {e}")
            return results
    
    async def _process_single_series_enhanced(self, 
                                            series_title: str, 
                                            sources: List[dict]) -> Optional[Dict[str, Any]]:
        """
        增强的单剧集处理流程
        
        Args:
            series_title: 剧集标题
            sources: 该剧集的源列表
            
        Returns:
            处理结果
        """
        self.logger.info(f"📺 处理剧集: {series_title}")
        
        try:
            # 构建剧集状态
            series_state = await self._build_series_state(series_title)
            if not series_state:
                self.logger.warning(f"❌ 无法构建剧集状态: {series_title}")
                return None
            
            missing_episodes = series_state.get_missing_episodes()
            if not missing_episodes:
                self.logger.info(f"✅ 剧集已完整，跳过: {series_title}")
                return {
                    "series_title": series_title,
                    "status": "complete",
                    "message": "剧集已完整"
                }
            
            self.logger.info(f"📋 缺失集数: {sorted(missing_episodes)}")
            
            # 阶段2: 动态漏斗筛选 (v4.1)
            self.logger.info("🎯 阶段2: 动态漏斗筛选")
            selected_sources, candidate_pool = await self.funnel_selector.select_with_funnel(
                sources, series_state
            )
            
            if not candidate_pool:
                self.logger.warning(f"❌ 动态筛选未找到候选文件: {series_title}")
                return {
                    "series_title": series_title,
                    "status": "no_candidates",
                    "message": "未找到候选文件"
                }
            
            # 阶段3: 上下文构建
            self.logger.info("🔧 阶段3: 上下文构建")
            context = await self.context_builder.build_context_from_files(
                candidate_pool, series_title, series_state
            )
            
            # 阶段4: LLM解析
            self.logger.info("🤖 阶段4: LLM智能解析")
            await self.llm_client.analyze_context(context)
            
            # 阶段5: 增强决策 (v4.1)
            self.logger.info("🧠 阶段5: 增强智能决策")
            series_info = SeriesInfo(
                title=series_title,
                season=1,  # TODO: 从上下文中提取
                total_episodes=len(series_state.tmdb_total_aired)
            )
            
            enhanced_result = await self.enhanced_decision_maker.make_enhanced_decision(
                context, series_info
            )
            
            if not enhanced_result or not enhanced_result.selected_files:
                self.logger.warning(f"❌ 增强决策未选中文件: {series_title}")
                return {
                    "series_title": series_title,
                    "status": "no_selection",
                    "message": "决策未选中文件"
                }
            
            # 阶段6: 生成转存配置
            self.logger.info("⚙️ 阶段6: 生成转存配置")
            save_config = self.quark_adapter.create_enhanced_save_config(
                enhanced_result.selected_files, series_title
            )
            
            # 构建结果
            result = {
                "series_title": series_title,
                "status": "success",
                "selected_files": len(enhanced_result.selected_files),
                "consistency_filtered": enhanced_result.consistency_filtered,
                "renamed_files": enhanced_result.renamed_files,
                "save_config_path": save_config,
                "statistics": enhanced_result.statistics,
                "missing_episodes": sorted(missing_episodes),
                "funnel_stats": self.funnel_selector.get_statistics()
            }
            
            self.logger.info(f"✅ 剧集处理成功: {series_title}")
            self.logger.info(f"   选中文件: {len(enhanced_result.selected_files)} 个")
            self.logger.info(f"   一致性过滤: {enhanced_result.consistency_filtered} 个")
            self.logger.info(f"   标准化命名: {enhanced_result.renamed_files} 个")
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ 单剧集处理失败: {series_title} - {e}")
            return {
                "series_title": series_title,
                "status": "error",
                "message": str(e)
            }
    
    async def _build_series_state(self, series_title: str) -> Optional[SeriesState]:
        """构建剧集状态"""
        try:
            # 使用上下文构建器的状态提供者
            state_provider = self.context_builder.state_provider
            
            # 获取TMDB信息
            tmdb_episodes = await state_provider.get_tmdb_episodes(series_title, season=1)
            
            # 获取本地状态 (这里简化处理，实际应该查询本地库)
            local_episodes = set()  # TODO: 实现本地状态查询
            
            return SeriesState(
                tmdb_total_aired=set(tmdb_episodes),
                local_existing=local_episodes
            )
            
        except Exception as e:
            self.logger.error(f"❌ 构建剧集状态失败: {series_title} - {e}")
            return None
    
    def _group_sources_by_series(self, sources: List[dict]) -> Dict[str, List[dict]]:
        """按剧集分组源"""
        # 简化实现，实际应该使用更智能的分组逻辑
        series_groups = {}
        
        for source in sources:
            # 提取剧集标题 (简化版)
            title = source.get('title', '未知剧集')
            
            # 清理标题，提取核心剧名
            clean_title = self._extract_series_title(title)
            
            if clean_title not in series_groups:
                series_groups[clean_title] = []
            
            series_groups[clean_title].append(source)
        
        return series_groups
    
    def _extract_series_title(self, raw_title: str) -> str:
        """从原始标题中提取剧集名称"""
        # 简化实现，移除常见的质量标识
        import re
        
        # 移除质量标识
        clean_title = re.sub(r'\[.*?\]', '', raw_title)
        clean_title = re.sub(r'4K|1080p|720p|HDR|杜比|Remux|BluRay', '', clean_title, flags=re.IGNORECASE)
        clean_title = re.sub(r'\s+', ' ', clean_title).strip()
        
        return clean_title or raw_title
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        return {
            "version": "v4.1_enhanced",
            "components": {
                "source_manager": True,
                "context_builder": True,
                "llm_client": True,
                "funnel_selector": True,
                "consistency_checker": True,
                "naming_generator": True,
                "enhanced_decision_maker": True,
                "quark_adapter": True
            },
            "config": {
                "funnel": self.funnel_selector.get_statistics(),
                "consistency": self.consistency_checker.get_statistics(),
                "naming": self.naming_generator.get_statistics()
            }
        }


async def main():
    """主函数 - 演示增强功能"""
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 创建增强系统
    system = EnhancedSmartChaseSystem()
    
    # 演示数据
    demo_sources = [
        {"title": "[4K Remux] 庆余年 第二季", "url": "https://pan.quark.cn/s/demo1"},
        {"title": "[1080p] 庆余年2 全集", "url": "https://pan.quark.cn/s/demo2"},
        {"title": "庆余年 S02 [HDR]", "url": "https://pan.quark.cn/s/demo3"},
    ]
    
    print("🚀 智能媒体资源治理系统 v4.1 增强版")
    print("=" * 50)
    
    # 显示系统状态
    status = system.get_system_status()
    print(f"📊 系统版本: {status['version']}")
    print(f"🔧 组件状态: 全部就绪")
    
    # 处理演示数据
    print("\n🎬 开始处理演示数据...")
    results = await system.process_series_enhanced(demo_sources)
    
    # 显示结果
    print(f"\n✅ 处理完成，共处理 {len(results)} 个剧集")
    for result in results:
        print(f"📺 {result['series_title']}: {result['status']}")


if __name__ == "__main__":
    asyncio.run(main())