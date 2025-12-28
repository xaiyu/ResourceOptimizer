"""
状态提供者模块
负责查询TMDB剧集信息和本地存储状态
"""

import logging
import os
import re
from typing import Set, Optional, Dict, Any
import requests

from core.contracts import SeriesState
from config.config_service import TMDBConfig, get_tmdb_config
from io_layer.cache_utils import cache_manager

logger = logging.getLogger(__name__)


class TMDBProvider:
    """TMDB API提供者

    支持两种初始化方式：
    1. 传统方式：直接传入api_key
    2. 配置注入：传入TMDBConfig配置对象（推荐）
    """

    def __init__(self, api_key: str = "", config: Optional[TMDBConfig] = None):
        """
        初始化TMDB提供者

        Args:
            api_key: TMDB API密钥（优先级高于config）
            config: 集中式配置对象（推荐使用config_service.get_tmdb_config()获取）
        """
        # 获取配置（如果未传入则从 config_service 加载）
        if config is None:
            from config.config_service import get_tmdb_config
            config = get_tmdb_config()
        
        # 从配置对象读取
        self.api_key = api_key or config.api_key
        self.base_url = config.base_url
        self.language = config.language

        if not self.api_key:
            logger.warning("TMDB API密钥未配置，剧集信息查询将不可用")
        else:
            logger.info("TMDB提供者初始化完成")
    
    def search_tv_show(self, title: str) -> Optional[Dict[str, Any]]:
        """
        搜索电视剧
        
        Args:
            title: 剧名
            
        Returns:
            剧集信息字典，如果未找到则返回None
        """
        if not self.api_key:
            logger.error("TMDB API密钥未配置")
            return None
        
        # 检查缓存
        cache_key = f"tmdb_search:{title}"
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            logger.debug(f"TMDB搜索缓存命中: {title}")
            return cached_result
        
        # 调用API
        url = f"{self.base_url}/search/tv"
        params = {
            "api_key": self.api_key,
            "language": self.language,
            "query": title,
            "page": 1
        }
        
        try:
            logger.info(f"搜索TMDB剧集: {title}")
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            results = data.get("results", [])
            
            if not results:
                logger.warning(f"未找到剧集: {title}")
                return None
            
            # 返回第一个结果
            tv_show = results[0]
            logger.info(f"找到剧集: {tv_show.get('name')} (ID: {tv_show.get('id')})")
            
            # 缓存结果
            cache_manager.set(cache_key, tv_show)
            
            return tv_show
            
        except Exception as e:
            logger.error(f"搜索TMDB剧集失败: {title}, 错误: {e}")
            return None
    
    def get_aired_episodes(self, tv_id: int, target_season: int = 1) -> Set[int]:
        """
        获取指定季已播出的集数
        
        Args:
            tv_id: TMDB剧集ID
            target_season: 目标季数，默认为第1季
            
        Returns:
            已播出集数的集合
        """
        if not self.api_key:
            logger.error("TMDB API密钥未配置")
            return set()
        
        # 检查缓存（包含季数信息）
        cache_key = f"tmdb_episodes:{tv_id}:s{target_season}"
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            logger.debug(f"TMDB集数缓存命中: TV ID {tv_id}, Season {target_season}")
            return set(cached_result)
        
        # 获取剧集详情
        url = f"{self.base_url}/tv/{tv_id}"
        params = {
            "api_key": self.api_key,
            "language": self.language
        }
        
        try:
            logger.info(f"获取TMDB剧集详情: TV ID {tv_id}, 目标季 {target_season}")
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # 获取指定季的集数
            aired_episodes = set()
            seasons = data.get("seasons", [])
            
            for season in seasons:
                season_number = season.get("season_number", 0)
                if season_number == 0:  # 跳过特别篇
                    continue
                
                # 只获取目标季的集数
                if season_number == target_season:
                    episode_count = season.get("episode_count", 0)
                    # 添加该季的所有集数
                    for ep in range(1, episode_count + 1):
                        aired_episodes.add(ep)
                    logger.info(f"季 {target_season}: 共 {episode_count} 集已播出")
                    break
            
            if not aired_episodes:
                # 如果没找到目标季，记录警告并尝试获取所有季度信息
                logger.warning(f"未找到季 {target_season} 的信息，可能是季数错误")
                # 列出可用的季度
                available_seasons = [s.get("season_number") for s in seasons if s.get("season_number", 0) > 0]
                logger.info(f"可用季度: {available_seasons}")
            
            logger.info(f"获取到 {len(aired_episodes)} 集已播出集数 (季 {target_season})")
            
            # 缓存结果（转换为列表以便JSON序列化）
            cache_manager.set(cache_key, list(aired_episodes))
            
            return aired_episodes
            
        except Exception as e:
            logger.error(f"获取TMDB集数失败: TV ID {tv_id}, 错误: {e}")
            return set()


class LocalStateProvider:
    """本地状态提供者"""
    
    def __init__(self, base_dir: str = ""):
        """
        初始化本地状态提供者
        
        Args:
            base_dir: 本地存储基础目录，如果为空则从配置读取
        """
        if not base_dir:
            from config.config_loader import get_config_value
            base_dir = get_config_value("output.base_dir", "instance/output")
        self.base_dir = base_dir
        logger.info(f"本地状态提供者初始化完成: {self.base_dir}")
    
    def get_existing_episodes(self, title: str) -> Set[int]:
        """
        获取本地已存储的集数
        
        Args:
            title: 剧名
            
        Returns:
            已存储集数的集合
        """
        # 检查缓存
        cache_key = f"local_episodes:{title}"
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            logger.debug(f"本地集数缓存命中: {title}")
            return set(cached_result)
        
        existing_episodes = set()
        
        # 如果目录不存在，返回空集合
        if not os.path.exists(self.base_dir):
            logger.debug(f"本地目录不存在: {self.base_dir}")
            return existing_episodes
        
        try:
            # 遍历目录查找视频文件
            for root, dirs, files in os.walk(self.base_dir):
                for filename in files:
                    # 检查是否为视频文件
                    if not self._is_video_file(filename):
                        continue
                    
                    # 从文件名提取集数
                    episode_numbers = self._extract_episode_numbers(filename)
                    existing_episodes.update(episode_numbers)
            
            logger.info(f"本地已存储 {len(existing_episodes)} 集: {title}")
            
            # 缓存结果（转换为列表以便JSON序列化）
            cache_manager.set(cache_key, list(existing_episodes), ttl=3600)  # 1小时缓存
            
            return existing_episodes
            
        except Exception as e:
            logger.error(f"获取本地集数失败: {title}, 错误: {e}")
            return existing_episodes
    
    def _is_video_file(self, filename: str) -> bool:
        """检查是否为视频文件"""
        video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.ts', '.m2ts']
        return any(filename.lower().endswith(ext) for ext in video_extensions)
    
    def _extract_episode_numbers(self, filename: str) -> Set[int]:
        """
        从文件名提取集数
        
        Args:
            filename: 文件名
            
        Returns:
            集数集合
        """
        episode_numbers = set()
        
        # 常见的集数模式
        patterns = [
            r'[Ee](\d{1,3})',           # E01, e01
            r'EP?(\d{1,3})',            # EP01, E01
            r'第(\d{1,3})[集话]',        # 第01集, 第01话
            r'[\[\(](\d{1,3})[\]\)]',   # [01], (01)
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, filename)
            for match in matches:
                try:
                    ep_num = int(match)
                    if 1 <= ep_num <= 999:  # 合理的集数范围
                        episode_numbers.add(ep_num)
                except ValueError:
                    continue
        
        return episode_numbers


class StateProvider:
    """
    状态提供者
    整合TMDB和本地状态查询，提供带缓存的状态信息

    支持两种初始化方式：
    1. 传统方式：使用默认配置
    2. 配置注入：传入TMDBConfig配置对象（推荐）
    """

    def __init__(self, config: Optional[TMDBConfig] = None):
        """
        初始化状态提供者

        Args:
            config: 集中式配置对象（推荐使用config_service.get_tmdb_config()获取）
        """
        self.tmdb_provider = TMDBProvider(config=config)
        self.local_provider = LocalStateProvider()
        logger.info("状态提供者初始化完成")
    
    def _extract_season_from_title(self, title: str) -> int:
        """
        从标题中自动提取季数
        
        支持的格式：
        - "剧名第二季" -> 2
        - "剧名 S02" -> 2
        - "剧名 Season 2" -> 2
        - "剧名2" (结尾数字) -> 2
        
        Args:
            title: 剧集标题
            
        Returns:
            提取的季数，默认为1
        """
        import re
        
        # 中文数字映射
        cn_numbers = {
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10
        }
        
        # 模式1: 第X季 (中文)
        match = re.search(r'第([一二三四五六七八九十]+)季', title)
        if match:
            cn_num = match.group(1)
            if cn_num in cn_numbers:
                return cn_numbers[cn_num]
        
        # 模式2: 第N季 (数字)
        match = re.search(r'第(\d+)季', title)
        if match:
            return int(match.group(1))
        
        # 模式3: S01, S02 等
        match = re.search(r'[Ss](\d{1,2})', title)
        if match:
            return int(match.group(1))
        
        # 模式4: Season 1, Season 2 等
        match = re.search(r'[Ss]eason\s*(\d+)', title, re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        # 模式5: 标题结尾的数字 (如 "庆余年2")
        match = re.search(r'(\d+)$', title.strip())
        if match:
            num = int(match.group(1))
            if 1 <= num <= 20:  # 合理的季数范围
                return num
        
        # 默认返回第1季
        return 1
    
    def get_state_with_cache(self, title: str, season: int = None) -> SeriesState:
        """
        获取剧集状态（带缓存）
        
        Args:
            title: 剧名
            season: 季数，如果不传则从标题自动提取或默认为1
            
        Returns:
            剧集状态对象
        """
        # 自动从标题提取季数
        if season is None:
            season = self._extract_season_from_title(title)
        
        # 检查缓存（包含季数）
        cache_key = f"series_state:{title}:s{season}"
        cached_state = cache_manager.get(cache_key)
        
        if cached_state:
            # 从缓存恢复SeriesState对象
            state = SeriesState(
                tmdb_total_aired=set(cached_state['tmdb_total_aired']),
                local_existing=set(cached_state['local_existing']),
                last_updated=cached_state['last_updated']
            )
            
            # 检查缓存是否仍然有效（12小时）
            if state.is_cache_valid(ttl_seconds=43200):
                logger.debug(f"剧集状态缓存有效: {title} (季 {season})")
                return state
            else:
                logger.debug(f"剧集状态缓存已过期: {title} (季 {season})")
        
        # 缓存无效或不存在，重新查询
        logger.info(f"查询剧集状态: {title} (季 {season})")
        
        # 查询TMDB已播出集数
        tmdb_aired = set()
        tv_show = self.tmdb_provider.search_tv_show(title)
        if tv_show:
            tv_id = tv_show.get("id")
            if tv_id:
                tmdb_aired = self.tmdb_provider.get_aired_episodes(tv_id, target_season=season)
        
        # 查询本地已存储集数
        local_existing = self.local_provider.get_existing_episodes(title)
        
        # 创建状态对象
        state = SeriesState(
            tmdb_total_aired=tmdb_aired,
            local_existing=local_existing
        )
        
        # 缓存状态（转换为可序列化的格式）
        cache_data = {
            'tmdb_total_aired': list(state.tmdb_total_aired),
            'local_existing': list(state.local_existing),
            'last_updated': state.last_updated
        }
        cache_manager.set(cache_key, cache_data)
        
        # 记录缺失集数
        missing = state.get_missing_episodes()
        if missing:
            logger.info(f"缺失集数: {sorted(missing)}")
        else:
            logger.info("没有缺失集数")
        
        return state
    
    def refresh_state(self, title: str) -> SeriesState:
        """
        强制刷新剧集状态（清除缓存）
        
        Args:
            title: 剧名
            
        Returns:
            刷新后的剧集状态
        """
        # 清除相关缓存
        cache_manager.delete(f"series_state:{title}")
        cache_manager.delete(f"local_episodes:{title}")
        
        logger.info(f"强制刷新剧集状态: {title}")
        return self.get_state_with_cache(title)


def create_state_provider(config: Optional[TMDBConfig] = None) -> StateProvider:
    """
    创建状态提供者实例的工厂函数

    Args:
        config: TMDBConfig配置对象，如果不传则从全局配置加载

    Returns:
        配置好的状态提供者实例
    """
    return StateProvider(config=config)


def create_tmdb_provider(config: Optional[TMDBConfig] = None) -> TMDBProvider:
    """
    创建TMDB提供者实例的工厂函数

    Args:
        config: TMDBConfig配置对象，如果不传则从全局配置加载

    Returns:
        配置好的TMDB提供者实例
    """
    return TMDBProvider(config=config)