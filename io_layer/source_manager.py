"""
源数据预处理模块
负责源头竞价，极速剔除劣质源，降低后续IO和API压力
"""

import logging
import re
from typing import Dict, List, Union, Any, Optional
from dataclasses import dataclass

from core.contracts import RankedSource
from config.config_loader import get_config_value

logger = logging.getLogger(__name__)


@dataclass
class SourceInfo:
    """源信息数据结构"""
    title: str                # 源标题
    url: str                  # 源链接
    user: str = ""            # 发布用户
    time: str = ""            # 发布时间
    raw_data: Dict[str, Any] = None  # 原始数据


class SourceManager:
    """
    源数据预处理管理器
    实现源头竞价算法，筛选优质资源
    """
    
    def __init__(self):
        """初始化源管理器"""
        # 从配置加载权重
        self.keyword_weights = get_config_value("weights.keyword_score", {})
        self.aliases = get_config_value("aliases", {})
        
        # 默认权重（防止配置缺失）
        self.default_weights = {
            "Remux": 50, "BluRay": 40, "4K": 30, "2160p": 30, "1080p": 10,
            "HDR": 20, "杜比视界": 25, "全景声": 15, "HEVC": 10, "H265": 10,
            "WEB-DL": 8, "TrueHD": 12, "DTS-HD": 12, "60fps": 8,
            "中字": 5, "内嵌": 5, "无水印": 3, "纯净": 3,
            # 负分关键词
            "720p": -20, "Trailer": -100, "预告": -100, "广告": -100,
            "测试": -50, "假4K": -80, "机翻": -60, "删减版": -70
        }
        
        # 合并配置权重和默认权重
        self.weights = {**self.default_weights, **self.keyword_weights}
        
        logger.info(f"源管理器初始化完成，加载了 {len(self.weights)} 个关键词权重")
    
    def rank_sources(self, sources: Union[Dict[str, List[str]], List[Dict[str, str]]], missing_episodes: int = 0) -> List[RankedSource]:
        """
        对源进行竞价排序 - v4.1 动态漏斗筛选
        
        Args:
            sources: 源数据，支持两种格式：
                     1. 字典格式 Dict[str, List[str]] - {"影视名": ["标题1,链接1", "标题2,链接2", ...]}
                     2. 列表格式 List[Dict[str, str]] - [{"title": "标题", "url": "链接"}, ...]
            missing_episodes: 缺失集数，用于动态停止条件
            
        Returns:
            排序后的源列表，动态数量（不再限制Top 3）
        """
        # 获取动态漏斗配置
        batch_size = get_config_value("app.funnel.batch_size", 3)
        max_sources = get_config_value("app.funnel.max_sources", 10)
        stop_multiplier = get_config_value("app.funnel.stop_multiplier", 3.0)
        enable_early_stop = get_config_value("app.funnel.enable_early_stop", True)
        
        all_sources = []
        
        # 统一转换为字典格式: {resource_title: [source_items]}
        if isinstance(sources, list):
            sources_dict = {"默认资源": sources}
        else:
            sources_dict = sources
        
        # 解析所有源
        for resource_title, source_list in sources_dict.items():
            logger.info(f"开始处理资源: {resource_title}, 源数量: {len(source_list)}")
            
            for source_str in source_list:
                try:
                    # 解析源字符串 "标题,链接" 或 {"title": "标题", "url": "链接", ...}
                    if isinstance(source_str, str):
                        if "," in source_str:
                            title, url = source_str.split(",", 1)
                            source_info = SourceInfo(title=title.strip(), url=url.strip())
                        else:
                            # 如果没有逗号，假设整个字符串是标题
                            source_info = SourceInfo(title=source_str.strip(), url="")
                    elif isinstance(source_str, dict):
                        source_info = SourceInfo(
                            title=source_str.get("title", source_str.get("name", "")),
                            url=source_str.get("url", source_str.get("link", "")),
                            user=source_str.get("user", ""),
                            time=source_str.get("time", ""),
                            raw_data=source_str
                        )
                    else:
                        logger.warning(f"无法解析源格式: {source_str}")
                        continue
                    
                    # 计算评分
                    score = self._calculate_source_score(source_info.title)
                    
                    # 时间加分
                    time_bonus = self._calculate_time_bonus(source_info.time)
                    total_score = score + time_bonus
                    
                    all_sources.append((total_score, source_info, resource_title))
                    
                    logger.debug(f"源评分: {source_info.title[:50]}... = {total_score} "
                               f"(关键词: {score}, 时间: {time_bonus})")
                    
                except Exception as e:
                    logger.error(f"解析源时出错: {source_str}, 错误: {e}")
                    continue
        
        # 按分数降序排序
        all_sources.sort(key=lambda x: x[0], reverse=True)
        
        # v4.1 动态漏斗筛选逻辑
        if enable_early_stop and missing_episodes > 0:
            # 计算动态停止阈值
            stop_threshold = int(missing_episodes * stop_multiplier)
            logger.info(f"动态漏斗筛选: 缺失 {missing_episodes} 集, "
                       f"目标候选数 {stop_threshold}, 批次大小 {batch_size}")
            
            # 分批处理
            selected_sources = []
            for batch_start in range(0, min(len(all_sources), max_sources), batch_size):
                batch_end = min(batch_start + batch_size, len(all_sources), max_sources)
                batch_sources = all_sources[batch_start:batch_end]
                
                logger.info(f"处理批次 {batch_start//batch_size + 1}: "
                           f"源 {batch_start+1}-{batch_end}")
                
                selected_sources.extend(batch_sources)
                
                # 检查是否达到停止条件
                if len(selected_sources) >= stop_threshold:
                    logger.info(f"达到停止条件: 已选择 {len(selected_sources)} 个源 "
                               f"(>= {stop_threshold}), 提前结束")
                    break
                
                # 检查是否已处理完所有源
                if batch_end >= len(all_sources):
                    logger.info(f"已处理完所有 {len(all_sources)} 个源")
                    break
            
            kept_sources = len(selected_sources)
            discarded_count = len(all_sources) - kept_sources
        else:
            # 传统模式：保留Top 3
            kept_sources = min(3, len(all_sources))
            selected_sources = all_sources[:kept_sources]
            discarded_count = len(all_sources) - kept_sources
            logger.info("使用传统模式: 保留Top 3源")
        
        # 记录被丢弃的低分源
        if discarded_count > 0:
            logger.info(f"源头竞价完成: 保留 {kept_sources} 个优质源，丢弃 {discarded_count} 个低分源")
            
            # 记录被丢弃的源（用于排查）
            for i, (score, source_info, resource_title) in enumerate(all_sources[kept_sources:], kept_sources + 1):
                logger.debug(f"丢弃源 #{i}: {source_info.title[:30]}... (评分: {score})")
        
        # 转换为RankedSource并返回
        ranked_sources = []
        for rank, (score, source_info, resource_title) in enumerate(selected_sources, 1):
            ranked_source = RankedSource(
                title=source_info.title,
                url=source_info.url,
                score=score,
                rank=rank
            )
            ranked_sources.append(ranked_source)
            
            logger.info(f"Top {rank}: {source_info.title[:50]}... (评分: {score})")
        
        return ranked_sources
    
    def _calculate_source_score(self, title: str) -> int:
        """
        计算源标题的关键词评分
        
        Args:
            title: 源标题
            
        Returns:
            评分（可能为负数）
        """
        if not title:
            return 0
        
        title_lower = title.lower()
        total_score = 0
        matched_keywords = []
        
        # 遍历所有权重关键词
        for keyword, weight in self.weights.items():
            if self._keyword_matches(title_lower, keyword.lower()):
                total_score += weight
                matched_keywords.append(f"{keyword}({weight:+d})")
        
        # 记录匹配的关键词（调试用）
        if matched_keywords:
            logger.debug(f"标题 '{title[:30]}...' 匹配关键词: {', '.join(matched_keywords)}")
        
        return total_score
    
    def _keyword_matches(self, text: str, keyword: str) -> bool:
        """
        检查关键词是否匹配（支持别名）
        
        Args:
            text: 待检查文本（已转小写）
            keyword: 关键词（已转小写）
            
        Returns:
            是否匹配
        """
        # 直接匹配
        if keyword in text:
            return True
        
        # 检查别名
        for alias_key, alias_list in self.aliases.items():
            if alias_key.lower() == keyword:
                for alias in alias_list:
                    if alias.lower() in text:
                        return True
        
        return False
    
    def _calculate_time_bonus(self, time_str: str) -> int:
        """
        计算时间加分
        
        Args:
            time_str: 时间字符串（如 "今天", "昨天", "3天前"）
            
        Returns:
            时间加分
        """
        if not time_str:
            return 0
        
        time_str = time_str.strip()
        
        # 今天发布
        if "今天" in time_str:
            return 5
        
        # 昨天发布
        if "昨天" in time_str:
            return 3
        
        # 前天发布
        if "前天" in time_str:
            return 2
        
        # N天前发布
        match = re.search(r'(\d+)天前', time_str)
        if match:
            days = int(match.group(1))
            if days <= 3:
                return max(0, 3 - days)  # 3天内递减加分
        
        return 0
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取源管理器统计信息
        
        Returns:
            统计信息字典
        """
        return {
            "total_keywords": len(self.weights),
            "positive_keywords": len([k for k, v in self.weights.items() if v > 0]),
            "negative_keywords": len([k for k, v in self.weights.items() if v < 0]),
            "aliases_count": len(self.aliases),
            "max_weight": max(self.weights.values()) if self.weights else 0,
            "min_weight": min(self.weights.values()) if self.weights else 0
        }


def create_source_manager() -> SourceManager:
    """
    创建源管理器实例的工厂函数
    
    Returns:
        配置好的源管理器实例
    """
    return SourceManager()