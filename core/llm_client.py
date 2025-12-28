"""
LLM智能解析模块
负责将文件名解析为结构化的视频元数据
"""

import asyncio
import logging
import json
import re
import time
from typing import List, Optional, Dict, Any
from dataclasses import asdict
import aiohttp
from tenacity import Retrying, stop_after_attempt, wait_exponential, retry_if_exception_type

from core.contracts import RawFileNode, VideoMeta
from config.config_service import LLMConfig, get_llm_config

logger = logging.getLogger(__name__)


class LLMClient:
    """
    LLM客户端
    使用SiliconFlow API进行智能视频元数据解析

    支持两种初始化方式：
    1. 传统方式：直接传入参数
    2. 配置注入：传入LLMConfig配置对象（推荐）
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "",
        max_concurrency: int = 4,
        config: Optional[LLMConfig] = None
    ):
        """
        初始化LLM客户端

        Args:
            api_key: SiliconFlow API密钥（优先级高于config）
            model: 模型名称（优先级高于config）
            max_concurrency: 最大并发数（优先级高于config）
            config: 集中式配置对象（推荐使用config_service.get_llm_config()获取）
        """
        if config is not None:
            self.api_key = api_key or config.api_key
            self.base_url = config.base_url
            self.model = model or config.model
            self.max_concurrency = max_concurrency or config.max_concurrency
            self.timeout = config.timeout
            self.retry_count = config.retry_count
            self.circuit_breaker_threshold = config.circuit_breaker_threshold
        else:
            # 使用 config_service 获取默认配置
            default_config = get_llm_config()
            self.api_key = api_key or default_config.api_key
            self.base_url = default_config.base_url
            self.model = model or default_config.model
            self.max_concurrency = max_concurrency or default_config.max_concurrency
            self.timeout = default_config.timeout
            self.retry_count = default_config.retry_count
            self.circuit_breaker_threshold = default_config.circuit_breaker_threshold

        self.semaphore = asyncio.Semaphore(self.max_concurrency)

        self.failure_count = 0
        self.last_failure_time = 0
        self.circuit_open = False

        self._current_standard_title = None

        if not self.api_key:
            logger.warning("SiliconFlow API密钥未配置，LLM解析功能将不可用")
        else:
            logger.info(f"LLM客户端初始化完成: {self.model}, 最大并发: {self.max_concurrency}")
    
    async def parse_video_metadata(self, file_node: RawFileNode) -> VideoMeta:
        """
        解析视频文件元数据
        
        Args:
            file_node: 原始文件节点
            
        Returns:
            解析后的视频元数据
        """
        if not self.api_key:
            logger.warning("API密钥未配置，使用规则解析降级")
            return self._fallback_parse(file_node)
        
        # 检查熔断器
        if self._is_circuit_open():
            logger.warning("熔断器开启，使用规则解析降级")
            return self._fallback_parse(file_node)
        
        # 并发控制
        async with self.semaphore:
            try:
                # 调用LLM API
                result = await self._call_llm_api(file_node)
                
                # 重置失败计数
                self.failure_count = 0
                self.circuit_open = False
                
                return result
                
            except Exception as e:
                logger.error(f"LLM解析失败: {file_node.filename}, 错误: {e}")
                
                # 更新失败计数
                self._record_failure()
                
                # 降级到规则解析
                return self._fallback_parse(file_node)
    
    async def batch_parse(self, file_nodes: List[RawFileNode]) -> List[VideoMeta]:
        """
        批量解析视频文件元数据
        
        Args:
            file_nodes: 文件节点列表
            
        Returns:
            解析结果列表
        """
        logger.info(f"开始批量解析 {len(file_nodes)} 个文件")
        
        # 创建异步任务
        tasks = [
            self.parse_video_metadata(file_node) 
            for file_node in file_nodes
        ]
        
        # 并发执行
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        parsed_results = []
        success_count = 0
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"解析文件失败: {file_nodes[i].filename}, 错误: {result}")
                # 使用降级解析
                fallback_result = self._fallback_parse(file_nodes[i])
                parsed_results.append(fallback_result)
            else:
                parsed_results.append(result)
                success_count += 1
        
        logger.info(f"批量解析完成: 成功 {success_count}/{len(file_nodes)} 个文件")
        return parsed_results
    
    def parse_files(self, file_nodes: List[RawFileNode], standard_title: str = None) -> List[VideoMeta]:
        """
        解析文件列表 - v4.1 多源异构标题适配核心方法
        
        核心功能：
        1. 支持官方标题作为解析基准锚点
        2. 智能识别缩写、拼音、谐音等变体形式
        3. 基于官方标题判断文件有效性
        4. 异步批量处理提高效率
        
        Args:
            file_nodes: 文件节点列表，包含文件名、路径、大小等信息
            standard_title: 官方正规标题（如"庆余年第二季"），用作解析基准锚点。
                          LLM将基于此标题识别文件是否相关，并解析缩写形式。
            
        Returns:
            List[VideoMeta]: 解析结果列表，包含：
                - filename: 文件名
                - episode: 集数
                - season: 季数
                - resolution: 分辨率
                - quality_score: 质量评分
                - is_valid_video: 是否为有效视频
                
        Example:
            >>> client = LLMClient()
            >>> files = [RawFileNode(filename="QYN.S02.E01.4K.mp4", ...)]
            >>> results = client.parse_files(files, standard_title="庆余年第二季")
            >>> print(f"识别到集数: {results[0].episode}")  # 输出: 1
            
        Note:
            - 当standard_title为None时，使用通用解析模式
            - 官方标题基准能显著提高识别准确率
            - 支持识别QYN=庆余年、ZHZ=甄嬛传等常见缩写
        """
        logger.info(f"开始解析 {len(file_nodes)} 个文件")
        if standard_title:
            logger.info(f"使用官方标题基准: {standard_title}")
        
        # 临时存储standard_title以供_build_prompt使用
        self._current_standard_title = standard_title
        
        try:
            # 使用asyncio运行异步批量解析
            import asyncio
            
            # 检查是否已有事件循环
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果已有运行中的事件循环，创建新任务
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, self.batch_parse(file_nodes))
                        result = future.result()
                else:
                    # 没有运行中的事件循环，直接运行
                    result = asyncio.run(self.batch_parse(file_nodes))
            except RuntimeError:
                # 创建新的事件循环
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(self.batch_parse(file_nodes))
                finally:
                    loop.close()
            
            return result
            
        finally:
            # 清理临时存储的standard_title
            self._current_standard_title = None
    
    async def _call_llm_api(self, file_node: RawFileNode) -> VideoMeta:
        """
        调用LLM API进行解析
        
        Args:
            file_node: 文件节点
            
        Returns:
            解析结果
        """
        # 构建提示词
        prompt = self._build_prompt(file_node)
        
        # 准备请求数据
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.1,  # 低温度确保一致性
            "max_tokens": 200,   # 限制token使用
            "stream": False
        }
        
        # 重试机制
        retrier = Retrying(
            stop=stop_after_attempt(self.retry_count),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
        )
        
        async def _do_request():
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                async with session.post(f"{self.base_url}/chat/completions", 
                                       headers=headers, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise aiohttp.ClientError(f"API调用失败: {response.status}, {error_text}")
                    
                    data = await response.json()
                    return data
        
        # 执行请求
        response_data = await retrier(_do_request)
        
        # 解析响应
        return self._parse_llm_response(response_data, file_node)
    
    def _build_prompt(self, file_node: RawFileNode) -> str:
        """
        构建增强提示词模板 - 支持官方标题基准
        
        Args:
            file_node: 文件节点
            
        Returns:
            提示词字符串
        """
        # 基础提示词
        base_prompt = f"""解析视频文件信息，返回JSON格式：
文件名: {file_node.filename}
路径: {file_node.full_path}
来源: {file_node.source_context}"""
        
        # 如果有官方标题，注入基准信息
        if hasattr(self, '_current_standard_title') and self._current_standard_title:
            base_prompt += f"""

【重要】官方正规剧名是 "{self._current_standard_title}"。
请以此为基准处理文件名中的缩写、拼音或谐音（例如 QYN = 庆余年）。
如果文件名明显不属于该剧集，请标记 is_valid_video=False。"""
        
        # 完整提示词
        full_prompt = base_prompt + """

返回格式：
{
  "title_cn": "中文剧名",
  "season": 季数(数字),
  "episode": 集数(数字),
  "resolution": "分辨率(如4K/2160p/1080p/720p)",
  "quality_score": 质量评分(0-100),
  "is_valid_video": true/false
}

只返回JSON，不要其他内容。"""
        
        return full_prompt
    
    def _parse_llm_response(self, response_data: Dict[str, Any], file_node: RawFileNode) -> VideoMeta:
        """
        解析LLM响应数据
        
        Args:
            response_data: API响应数据
            file_node: 原始文件节点
            
        Returns:
            视频元数据
        """
        try:
            # 提取响应内容
            content = response_data["choices"][0]["message"]["content"].strip()
            
            # 尝试解析JSON
            # 移除可能的markdown代码块标记
            content = re.sub(r'```json\s*|\s*```', '', content)
            content = content.strip()
            
            parsed_data = json.loads(content)
            
            # 验证和清理数据
            title_cn = parsed_data.get("title_cn", "未知剧集")
            season = max(0, int(parsed_data.get("season", 1)))
            episode = max(0, int(parsed_data.get("episode", 0)))
            resolution = parsed_data.get("resolution", "未知")
            quality_score = max(0, min(100, int(parsed_data.get("quality_score", 50))))
            is_valid_video = bool(parsed_data.get("is_valid_video", True))
            
            return VideoMeta(
                title_cn=title_cn,
                season=season,
                episode=episode,
                resolution=resolution,
                quality_score=quality_score,
                is_valid_video=is_valid_video
            )
            
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
            logger.warning(f"LLM响应解析失败: {e}, 内容: {response_data}")
            # 降级到规则解析
            return self._fallback_parse(file_node)
    
    def _fallback_parse(self, file_node: RawFileNode) -> VideoMeta:
        """
        规则解析降级方案
        
        Args:
            file_node: 文件节点
            
        Returns:
            基于规则解析的视频元数据
        """
        filename = file_node.filename
        full_path = file_node.full_path
        source_context = file_node.source_context
        
        # 从源上下文提取剧名
        title_cn = "未知剧集"
        if source_context:
            # 移除方括号和常见标记
            clean_title = re.sub(r'\[.*?\]|\(.*?\)|【.*?】', '', source_context).strip()
            if clean_title:
                title_cn = clean_title
        
        # 提取季数
        season = 1
        season_patterns = [
            r'[Ss](\d+)',           # S01, s01
            r'第(\d+)季',           # 第1季
            r'Season\s*(\d+)',      # Season 1
        ]
        
        for pattern in season_patterns:
            match = re.search(pattern, filename + full_path + source_context)
            if match:
                season = int(match.group(1))
                break
        
        # 提取集数
        episode = 0
        episode_patterns = [
            r'[Ee](\d+)',           # E01, e01
            r'EP?(\d+)',            # EP01, E01
            r'第(\d+)[集话]',        # 第01集, 第01话
            r'[\[\(](\d+)[\]\)]',   # [01], (01)
        ]
        
        for pattern in episode_patterns:
            match = re.search(pattern, filename)
            if match:
                episode = int(match.group(1))
                break
        
        # 提取分辨率
        resolution = "未知"
        if re.search(r'4K|2160p', filename + source_context, re.IGNORECASE):
            resolution = "4K"
        elif re.search(r'1080p', filename + source_context, re.IGNORECASE):
            resolution = "1080p"
        elif re.search(r'720p', filename + source_context, re.IGNORECASE):
            resolution = "720p"
        
        # 计算质量评分（基于关键词）
        quality_score = 50  # 基础分
        
        # 分辨率加分
        if "4K" in resolution:
            quality_score += 30
        elif "1080p" in resolution:
            quality_score += 20
        elif "720p" in resolution:
            quality_score += 10
        
        # 编码格式加分
        if re.search(r'HEVC|H265|x265', filename + source_context, re.IGNORECASE):
            quality_score += 15
        
        # HDR加分
        if re.search(r'HDR|杜比视界|Dolby Vision', filename + source_context, re.IGNORECASE):
            quality_score += 20
        
        # 音频加分
        if re.search(r'Atmos|全景声|TrueHD|DTS', filename + source_context, re.IGNORECASE):
            quality_score += 10
        
        # 限制评分范围
        quality_score = max(0, min(100, quality_score))
        
        # 检查是否为有效视频
        is_valid_video = True
        invalid_keywords = ['预告', 'trailer', '广告', '测试', '花絮']
        for keyword in invalid_keywords:
            if keyword in filename.lower() or keyword in source_context.lower():
                is_valid_video = False
                break
        
        logger.debug(f"规则解析结果: {filename} -> {title_cn} S{season:02d}E{episode:02d} {resolution} ({quality_score}分)")
        
        return VideoMeta(
            title_cn=title_cn,
            season=season,
            episode=episode,
            resolution=resolution,
            quality_score=quality_score,
            is_valid_video=is_valid_video
        )
    
    def _is_circuit_open(self) -> bool:
        """检查熔断器是否开启"""
        if not self.circuit_open:
            return False
        
        # 检查是否可以尝试恢复
        if time.time() - self.last_failure_time > 60:  # 1分钟后尝试恢复
            self.circuit_open = False
            self.failure_count = 0
            logger.info("熔断器恢复，重新启用LLM解析")
            return False
        
        return True
    
    def _record_failure(self):
        """记录失败并检查是否需要开启熔断器"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.circuit_breaker_threshold:
            self.circuit_open = True
            logger.warning(f"LLM解析连续失败 {self.failure_count} 次，开启熔断器")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取LLM客户端统计信息
        
        Returns:
            统计信息字典
        """
        return {
            "has_api_key": bool(self.api_key),
            "model": self.model,
            "max_concurrency": self.max_concurrency,
            "failure_count": self.failure_count,
            "circuit_open": self.circuit_open,
            "base_url": self.base_url,
            "timeout": self.timeout,
            "retry_count": self.retry_count
        }


def create_llm_client(api_key: str = "", model: str = "", max_concurrency: int = 4) -> LLMClient:
    """
    创建LLM客户端实例的工厂函数

    Args:
        api_key: API密钥
        model: 模型名称
        max_concurrency: 最大并发数

    Returns:
        配置好的LLM客户端实例
    """
    return LLMClient(api_key, model, max_concurrency)


def create_llm_client_with_config(config: Optional[LLMConfig] = None) -> LLMClient:
    """
    创建LLM客户端实例的工厂函数（使用集中式配置）

    Args:
        config: LLMConfig配置对象，如果不传则从全局配置加载

    Returns:
        配置好的LLM客户端实例
    """
    if config is None:
        config = get_llm_config()
    return LLMClient(config=config)