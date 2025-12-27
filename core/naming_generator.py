"""
标准化命名生成器 v4.1
解决命名混乱问题，生成规范的文件名
"""

import logging
import re
from typing import Dict, List, Optional
from pathlib import Path

from core.contracts import RawFileNode, VideoMeta, SeriesInfo, NamingConfig


class StandardizedNamingGenerator:
    """
    标准化命名生成器
    
    核心功能：
    1. 生成符合媒体库标准的文件名
    2. 智能提取质量标识
    3. 清理非法字符
    """
    
    def __init__(self, config: NamingConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 文件系统非法字符
        self.invalid_chars = r'<>:"/\|?*'
        
        # 质量识别正则
        self.quality_patterns = {
            "resolution": {
                "4K": [r"4k", r"2160p", r"uhd"],
                "1080p": [r"1080p", r"fhd"],
                "720p": [r"720p", r"hd"]
            },
            "hdr": [r"hdr", r"hdr10", r"hdr10\+", r"杜比视界", r"dolby.?vision", r"dv"],
            "audio": {
                "Atmos": [r"atmos", r"全景声"],
                "TrueHD": [r"truehd", r"thd"],
                "DTS-HD": [r"dts.?hd", r"dts.?x", r"dtsx"],
                "DTS": [r"dts"],
                "AC3": [r"ac3", r"ac.3"]
            }
        }
    
    def generate_filename(self, 
                         series_info: SeriesInfo, 
                         file_node: RawFileNode, 
                         video_meta: VideoMeta) -> str:
        """
        生成标准化文件名
        
        Args:
            series_info: 剧集信息
            file_node: 文件节点
            video_meta: 视频元数据
            
        Returns:
            标准化的文件名
        """
        if not self.config.enable:
            self.logger.debug("🏷️ 标准化命名已禁用，保持原文件名")
            return file_node.filename
        
        try:
            # 提取基础信息
            title = self._clean_title(series_info.title)
            season = series_info.season or 1
            episode = video_meta.episode
            ext = self._extract_extension(file_node.filename)
            
            # 生成质量标识
            quality = self._generate_quality_tags(file_node.filename, video_meta)
            
            # 应用命名模板
            filename = self.config.format_template.format(
                title=title,
                season=season,
                episode=episode,
                quality=quality,
                ext=ext
            )
            
            # 清理文件名
            clean_filename = self._sanitize_filename(filename)
            
            self.logger.debug(f"🏷️ 标准化命名:")
            self.logger.debug(f"   原文件名: {file_node.filename}")
            self.logger.debug(f"   新文件名: {clean_filename}")
            
            return clean_filename
            
        except Exception as e:
            self.logger.error(f"❌ 命名生成失败: {e}")
            self.logger.error(f"   回退到原文件名: {file_node.filename}")
            return file_node.filename
    
    def _clean_title(self, title: str) -> str:
        """
        清理剧集标题
        
        Args:
            title: 原始标题
            
        Returns:
            清理后的标题
        """
        # 移除文件系统不支持的字符
        clean_title = title
        for char in self.invalid_chars:
            clean_title = clean_title.replace(char, '')
        
        # 移除多余空格
        clean_title = re.sub(r'\s+', ' ', clean_title).strip()
        
        return clean_title
    
    def _extract_extension(self, filename: str) -> str:
        """
        提取文件扩展名
        
        Args:
            filename: 文件名
            
        Returns:
            扩展名 (不含点号)
        """
        ext = Path(filename).suffix.lower()
        return ext[1:] if ext else "mkv"  # 默认使用mkv
    
    def _generate_quality_tags(self, filename: str, video_meta: VideoMeta) -> str:
        """
        生成质量标识
        
        Args:
            filename: 原文件名
            video_meta: 视频元数据
            
        Returns:
            质量标识字符串，如 "4K/HDR/Atmos"
        """
        tags = []
        filename_lower = filename.lower()
        
        # 分辨率标识
        resolution_tag = self._detect_resolution(filename_lower, video_meta)
        if resolution_tag:
            tags.append(resolution_tag)
        
        # HDR标识
        if self._detect_hdr(filename_lower):
            tags.append(self.config.quality_tags.get("hdr", "HDR"))
        
        # 音频标识
        audio_tag = self._detect_audio(filename_lower)
        if audio_tag:
            tags.append(audio_tag)
        
        return "/".join(tags) if tags else ""
    
    def _detect_resolution(self, filename_lower: str, video_meta: VideoMeta) -> Optional[str]:
        """检测分辨率"""
        # 优先使用元数据
        if hasattr(video_meta, 'resolution') and video_meta.resolution:
            if video_meta.resolution in self.config.quality_tags:
                return self.config.quality_tags[video_meta.resolution]
        
        # 从文件名检测
        for resolution, tag in [("4K", ["4k", "2160p", "uhd"]), 
                               ("1080p", ["1080p", "fhd"])]:
            for pattern in tag:
                if re.search(pattern, filename_lower):
                    return self.config.quality_tags.get(resolution.lower(), resolution)
        
        return None
    
    def _detect_hdr(self, filename_lower: str) -> bool:
        """检测HDR"""
        hdr_patterns = self.quality_patterns["hdr"]
        return any(re.search(pattern, filename_lower) for pattern in hdr_patterns)
    
    def _detect_audio(self, filename_lower: str) -> Optional[str]:
        """检测音频格式"""
        for audio_type, patterns in self.quality_patterns["audio"].items():
            for pattern in patterns:
                if re.search(pattern, filename_lower):
                    return self.config.quality_tags.get(audio_type.lower(), audio_type)
        
        return None
    
    def _sanitize_filename(self, filename: str) -> str:
        """
        清理文件名，移除非法字符
        
        Args:
            filename: 原文件名
            
        Returns:
            清理后的文件名
        """
        # 移除非法字符
        clean_name = filename
        for char in self.invalid_chars:
            clean_name = clean_name.replace(char, '')
        
        # 处理连续空格
        clean_name = re.sub(r'\s+', ' ', clean_name)
        
        # 移除首尾空格
        clean_name = clean_name.strip()
        
        # 确保不为空
        if not clean_name:
            clean_name = "unnamed_file.mkv"
        
        return clean_name
    
    def batch_generate_filenames(self, 
                                series_info: SeriesInfo,
                                file_nodes: List[RawFileNode],
                                video_metas: List[VideoMeta]) -> List[str]:
        """
        批量生成标准化文件名
        
        Args:
            series_info: 剧集信息
            file_nodes: 文件节点列表
            video_metas: 视频元数据列表
            
        Returns:
            标准化文件名列表
        """
        if len(file_nodes) != len(video_metas):
            raise ValueError("文件节点和元数据列表长度不匹配")
        
        filenames = []
        for file_node, video_meta in zip(file_nodes, video_metas):
            filename = self.generate_filename(series_info, file_node, video_meta)
            filenames.append(filename)
        
        self.logger.info(f"🏷️ 批量生成 {len(filenames)} 个标准化文件名")
        return filenames
    
    def get_statistics(self) -> dict:
        """获取命名统计信息"""
        return {
            "config": {
                "enable": self.config.enable,
                "format_template": self.config.format_template,
                "quality_tags": self.config.quality_tags
            }
        }