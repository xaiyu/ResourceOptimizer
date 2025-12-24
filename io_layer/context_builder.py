"""
上下文构建器模块
负责整合爬虫、状态查询、文件过滤和去重功能，构建完整的分析上下文
"""

import logging
import re
from typing import List, Dict, Set, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.contracts import RawFileNode, AnalysisContext, SeriesState, RankedSource
from io_layer.crawler import QuarkCrawler, create_quark_crawler
from io_layer.state_provider import StateProvider, create_state_provider
from io_layer.source_manager import SourceManager
from config.config_loader import get_config_value

logger = logging.getLogger(__name__)


class ContextBuilder:
    """
    上下文构建器
    整合多个数据源，构建完整的分析上下文
    """
    
    def __init__(self):
        """初始化上下文构建器"""
        # 初始化各个组件
        self.crawler = create_quark_crawler()
        self.state_provider = create_state_provider()
        self.source_manager = SourceManager()
        
        # 获取配置
        self.min_file_size_mb = get_config_value("app.min_file_size_mb", 200)
        self.min_file_size_bytes = self.min_file_size_mb * 1024 * 1024
        self.max_concurrency = get_config_value("app.max_concurrency", 4)
        
        # 支持的视频格式
        self.video_extensions = {
            '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', 
            '.webm', '.ts', '.m2ts', '.m4v', '.3gp', '.f4v'
        }
        
        logger.info(f"上下文构建器初始化完成 (最小文件大小: {self.min_file_size_mb}MB)")
    
    def build_context(self, sources: List[Dict[str, str]], target_title: str) -> AnalysisContext:
        """
        构建分析上下文
        
        Args:
            sources: 源列表，每个源包含 title 和 url
            target_title: 目标剧名
            
        Returns:
            完整的分析上下文
        """
        logger.info(f"开始构建上下文: {target_title}")
        
        # 1. 源头竞价 - 选择最优源
        # 转换源格式以适配源管理器接口
        sources_dict = {
            target_title: [f"{source['title']},{source['url']}" for source in sources]
        }
        selected_sources = self.source_manager.rank_sources(sources_dict)
        
        logger.info(f"选择了 {len(selected_sources)} 个优质源进行爬取")
        for i, source in enumerate(selected_sources, 1):
            logger.info(f"  {i}. {source.title} (评分: {source.score})")
        
        # 2. 并发爬取文件
        all_files = self._crawl_sources_concurrent(selected_sources)
        logger.info(f"爬取到 {len(all_files)} 个原始文件")
        
        # 3. 物理过滤 - 大小和格式
        filtered_files = self._apply_physical_filters(all_files)
        logger.info(f"物理过滤后剩余 {len(filtered_files)} 个文件")
        
        # 4. 去重 - 基于file_id
        deduplicated_files = self._deduplicate_files(filtered_files)
        logger.info(f"去重后剩余 {len(deduplicated_files)} 个文件")
        
        # 5. 上下文注入 - 注入源标题信息
        context_injected_files = self._inject_source_context(deduplicated_files, selected_sources)
        logger.info(f"上下文注入完成，处理 {len(context_injected_files)} 个文件")
        
        # 6. 获取剧集状态
        series_state = self.state_provider.get_state_with_cache(target_title)
        missing_episodes = series_state.get_missing_episodes()
        logger.info(f"剧集状态: TMDB已播出 {len(series_state.tmdb_total_aired)} 集, "
                   f"本地已存储 {len(series_state.local_existing)} 集, "
                   f"缺失 {len(missing_episodes)} 集")
        
        # 7. 构建分析上下文
        context = AnalysisContext(
            standard_title=target_title,
            candidates=context_injected_files,
            state=series_state
        )
        
        logger.info(f"上下文构建完成: {target_title}, 候选文件 {len(context.candidates)} 个")
        return context
    
    def _crawl_sources_concurrent(self, sources: List[RankedSource]) -> List[RawFileNode]:
        """
        并发爬取多个源
        
        Args:
            sources: 排序后的源列表
            
        Returns:
            所有文件的列表
        """
        all_files = []
        
        # 使用线程池并发爬取
        with ThreadPoolExecutor(max_workers=min(len(sources), self.max_concurrency)) as executor:
            # 提交爬取任务
            future_to_source = {
                executor.submit(self._crawl_single_source, source): source 
                for source in sources
            }
            
            # 收集结果
            for future in as_completed(future_to_source):
                source = future_to_source[future]
                try:
                    files = future.result()
                    all_files.extend(files)
                    logger.info(f"源 '{source.title}' 爬取完成: {len(files)} 个文件")
                except Exception as e:
                    logger.error(f"爬取源 '{source.title}' 失败: {e}")
        
        return all_files
    
    def _crawl_single_source(self, source: RankedSource) -> List[RawFileNode]:
        """
        爬取单个源
        
        Args:
            source: 源信息
            
        Returns:
            该源的文件列表
        """
        try:
            # 使用源标题作为上下文
            source_context = f"[{source.title}]"
            files = self.crawler.fetch(source.url, source_context)
            return files
        except Exception as e:
            logger.error(f"爬取源失败: {source.title}, 错误: {e}")
            return []
    
    def _apply_physical_filters(self, files: List[RawFileNode]) -> List[RawFileNode]:
        """
        应用物理过滤规则
        
        Args:
            files: 原始文件列表
            
        Returns:
            过滤后的文件列表
        """
        filtered_files = []
        
        for file_node in files:
            # 检查文件大小
            if file_node.size < self.min_file_size_bytes:
                logger.debug(f"文件过小被过滤: {file_node.filename} "
                           f"({self._format_size(file_node.size)} < {self.min_file_size_mb}MB)")
                continue
            
            # 检查文件格式
            if not self._is_video_file(file_node.filename):
                logger.debug(f"非视频文件被过滤: {file_node.filename}")
                continue
            
            filtered_files.append(file_node)
        
        return filtered_files
    
    def _is_video_file(self, filename: str) -> bool:
        """
        检查是否为视频文件
        
        Args:
            filename: 文件名
            
        Returns:
            是否为视频文件
        """
        # 获取文件扩展名
        import os
        _, ext = os.path.splitext(filename.lower())
        return ext in self.video_extensions
    
    def _deduplicate_files(self, files: List[RawFileNode]) -> List[RawFileNode]:
        """
        基于file_id去重
        
        Args:
            files: 文件列表
            
        Returns:
            去重后的文件列表
        """
        seen_ids = set()
        deduplicated_files = []
        duplicate_count = 0
        
        for file_node in files:
            if file_node.file_id not in seen_ids:
                seen_ids.add(file_node.file_id)
                deduplicated_files.append(file_node)
            else:
                duplicate_count += 1
                logger.debug(f"重复文件被过滤: {file_node.filename} (ID: {file_node.file_id})")
        
        if duplicate_count > 0:
            logger.info(f"去重完成: 移除了 {duplicate_count} 个重复文件")
        
        return deduplicated_files
    
    def _inject_source_context(self, files: List[RawFileNode], sources: List[RankedSource]) -> List[RawFileNode]:
        """
        注入源上下文信息
        
        Args:
            files: 文件列表
            sources: 源列表
            
        Returns:
            注入上下文后的文件列表
        """
        # 创建源映射 (URL -> 源信息)
        source_map = {source.url: source for source in sources}
        
        for file_node in files:
            # 如果文件已经有上下文，跳过
            if file_node.source_context:
                continue
            
            # 根据share_token查找对应的源
            matching_source = None
            for source in sources:
                # 从URL中提取pwd_id进行匹配
                pwd_id_match = re.search(r"/s/(\w+)", source.url)
                if pwd_id_match and pwd_id_match.group(1) == file_node.share_token:
                    matching_source = source
                    break
            
            # 注入上下文
            if matching_source:
                file_node.source_context = f"[{matching_source.title}]"
                logger.debug(f"注入上下文: {file_node.filename} <- {matching_source.title}")
            else:
                # 如果找不到匹配的源，使用默认上下文
                file_node.source_context = f"[未知源-{file_node.share_token}]"
                logger.debug(f"使用默认上下文: {file_node.filename}")
        
        return files
    
    def _format_size(self, size_bytes: int) -> str:
        """
        格式化文件大小
        
        Args:
            size_bytes: 字节数
            
        Returns:
            格式化的大小字符串
        """
        if size_bytes == 0:
            return "0B"
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f}{unit}"
            size_bytes /= 1024.0
        
        return f"{size_bytes:.2f}PB"
    
    def refresh_context(self, sources: List[Dict[str, str]], target_title: str) -> AnalysisContext:
        """
        强制刷新上下文（清除缓存）
        
        Args:
            sources: 源列表
            target_title: 目标剧名
            
        Returns:
            刷新后的分析上下文
        """
        logger.info(f"强制刷新上下文: {target_title}")
        
        # 刷新剧集状态缓存
        self.state_provider.refresh_state(target_title)
        
        # 重新构建上下文
        return self.build_context(sources, target_title)
    
    def get_statistics(self) -> Dict[str, any]:
        """
        获取上下文构建器统计信息
        
        Returns:
            统计信息字典
        """
        return {
            "min_file_size_mb": self.min_file_size_mb,
            "max_concurrency": self.max_concurrency,
            "supported_video_formats": list(self.video_extensions),
            "crawler_stats": self.crawler.get_statistics(),
            "cache_stats": self.state_provider.local_provider.base_dir
        }


def create_context_builder() -> ContextBuilder:
    """
    创建上下文构建器实例的工厂函数
    
    Returns:
        配置好的上下文构建器实例
    """
    return ContextBuilder()