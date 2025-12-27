"""
夸克网盘爬虫模块
负责与夸克云盘API交互，获取文件结构信息
"""

import re
import logging
import requests
import time
import json
import asyncio
from typing import Optional, Dict, Any, Tuple, List
from tenacity import Retrying, stop_after_attempt, wait_exponential, retry_if_exception_type
import aiohttp

from core.contracts import RawFileNode
from config.config_loader import get_config_value

logger = logging.getLogger(__name__)


class QuarkCrawler:
    """
    夸克网盘爬虫
    处理链接解析、有效性检查和获取文件详情
    """
    
    def __init__(self, cookie: str = ""):
        """
        初始化夸克爬虫
        
        Args:
            cookie: 夸克网盘Cookie，如果为空则从配置读取
        """
        # 获取配置
        self.cookie = cookie or get_config_value("provider.quark_cookie", "")
        self.base_url = get_config_value("provider.quark_base_url", "https://drive-pc.quark.cn")
        self.base_url_app = get_config_value("provider.quark_base_url_app", "https://drive-m.quark.cn")
        self.user_agent = get_config_value("provider.quark_user_agent", 
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) quark-cloud-drive/3.14.2 Chrome/112.0.5615.165 Electron/24.1.3.8 Safari/537.36 Channel/pckk_other_ch")
        self.timeout = get_config_value("provider.quark_timeout", 30)
        self.retry_count = get_config_value("provider.quark_retry_count", 3)
        self.retry_delay = get_config_value("provider.quark_retry_delay", 1)
        
        # 提取移动端参数
        self.mparam = self._extract_mobile_params(self.cookie)
        
        # 创建会话
        self.session = requests.Session()
        
        if not self.cookie:
            logger.warning("夸克网盘Cookie未配置，爬虫功能将不可用")
        else:
            logger.info("夸克爬虫初始化完成")
    
    def _extract_mobile_params(self, cookie: str) -> Dict[str, str]:
        """
        从Cookie中提取移动端参数
        
        Args:
            cookie: Cookie字符串
            
        Returns:
            移动端参数字典
        """
        mparam = {}
        if not cookie:
            return mparam
            
        # 提取移动端必需的参数
        patterns = {
            "kps": r"(?<!\\w)kps=([a-zA-Z0-9%+/=]+)[;&]?",
            "sign": r"(?<!\\w)sign=([a-zA-Z0-9%+/=]+)[;&]?", 
            "vcode": r"(?<!\\w)vcode=([a-zA-Z0-9%+/=]+)[;&]?"
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, cookie)
            if match:
                mparam[key] = match.group(1).replace("%25", "%")
        
        if len(mparam) == 3:
            logger.debug("成功提取移动端参数")
        else:
            logger.debug("未找到完整的移动端参数")
        
        return mparam
    
    def _send_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        发送HTTP请求（带重试机制）
        
        Args:
            method: HTTP方法
            url: 请求URL
            **kwargs: 其他请求参数
            
        Returns:
            响应对象
            
        Raises:
            requests.RequestException: 请求失败
        """
        retrier = Retrying(
            stop=stop_after_attempt(self.retry_count),
            wait=wait_exponential(multiplier=self.retry_delay, min=1, max=10),
            retry=retry_if_exception_type(requests.exceptions.RequestException)
        )
        
        def _do_request():
            headers = {
                "cookie": self.cookie,
                "content-type": "application/json",
                "user-agent": self.user_agent,
            }
            
            # 合并自定义headers
            if "headers" in kwargs:
                headers.update(kwargs["headers"])
                del kwargs["headers"]
            
            # 处理移动端分享链接
            request_url = url
            if self.mparam and "share" in url and self.base_url in url:
                request_url = url.replace(self.base_url, self.base_url_app)
                params = kwargs.get("params", {})
                params.update({
                    "device_model": "M2011K2C",
                    "entry": "default_clouddrive", 
                    "fr": "android",
                    **self.mparam,
                    "app": "clouddrive",
                })
                kwargs["params"] = params
            
            try:
                response = self.session.request(method, request_url, headers=headers, 
                                              timeout=self.timeout, **kwargs)
                response.raise_for_status()
                return response
            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP错误: {e} (URL: {request_url})")
                raise
            except requests.exceptions.RequestException as e:
                logger.error(f"请求失败: {e} (URL: {request_url})")
                raise
        
        return retrier(_do_request)
    
    def parse_share_url(self, url: str) -> Tuple[Optional[str], str, str]:
        """
        解析分享链接，提取关键参数
        
        Args:
            url: 分享链接
            
        Returns:
            (pwd_id, passcode, pdir_fid) 元组
        """
        logger.debug(f"解析分享链接: {url}")
        
        # 提取pwd_id
        match_id = re.search(r"/s/(\w+)", url)
        pwd_id = match_id.group(1) if match_id else None
        
        # 提取密码
        match_pwd = re.search(r"pwd=(\w+)", url)
        passcode = match_pwd.group(1) if match_pwd else ""
        
        # 默认父目录ID
        pdir_fid = "0"
        
        logger.debug(f"解析结果: pwd_id={pwd_id}, passcode={'有' if passcode else '无'}")
        return pwd_id, passcode, pdir_fid
    
    def get_share_token(self, pwd_id: str, passcode: str = "") -> Dict[str, Any]:
        """
        获取分享令牌
        
        Args:
            pwd_id: 分享ID
            passcode: 分享密码
            
        Returns:
            API响应字典
        """
        url = f"{self.base_url}/1/clouddrive/share/sharepage/token"
        querystring = {"pr": "ucpro", "fr": "pc"}
        payload = {"pwd_id": pwd_id, "passcode": passcode}
        
        logger.info(f"获取分享令牌: pwd_id={pwd_id}")
        
        try:
            response = self._send_request("POST", url, json=payload, params=querystring)
            response_json = response.json()
            
            if response_json.get("status") == 200:
                logger.info("成功获取分享令牌")
            else:
                logger.warning(f"获取分享令牌失败: {response_json.get('message')}")
            
            return response_json
        except Exception as e:
            logger.error(f"获取分享令牌异常: {e}")
            return {"status": 500, "message": f"请求异常: {str(e)}"}
    
    def fetch_files_recursive(self, pwd_id: str, stoken: str, pdir_fid: str = "0", 
                             current_path: str = "", depth: int = 0, max_depth: int = 5) -> List[RawFileNode]:
        """
        递归获取文件列表
        
        Args:
            pwd_id: 分享ID
            stoken: 分享令牌
            pdir_fid: 父目录ID
            current_path: 当前路径
            depth: 当前深度
            max_depth: 最大深度
            
        Returns:
            文件节点列表
        """
        if depth >= max_depth:
            logger.warning(f"达到最大递归深度 {max_depth}, 路径: {current_path}")
            return []
        
        files = []
        url = f"{self.base_url}/1/clouddrive/share/sharepage/detail"
        querystring = {
            "pr": "ucpro", "fr": "pc", "pwd_id": pwd_id, "stoken": stoken,
            "pdir_fid": pdir_fid, "force": "0", "_page": 1, "_size": 2000,
            "_fetch_total": "1", "_sort": "file_type:asc,updated_at:desc",
        }
        
        logger.debug(f"获取文件列表: 深度={depth}, 路径='{current_path}', 父ID={pdir_fid}")
        
        try:
            response = self._send_request("GET", url, params=querystring)
            data = response.json()
            
            if data.get("code") != 0:
                logger.warning(f"获取目录失败: {data.get('message')}")
                return []
            
            item_list = data.get("data", {}).get("list", [])
            logger.debug(f"在路径 '{current_path}' 下找到 {len(item_list)} 个项目")
            
            for item in item_list:
                name = item.get("file_name", "Unknown")
                fid = item.get("fid", "")
                item_path = f"{current_path}/{name}" if current_path else f"/{name}"
                item_size = int(item.get("size", 0))
                
                if item.get("is_dir"):
                    # 递归处理文件夹
                    logger.debug(f"进入文件夹: {name}")
                    time.sleep(0.5)  # 限制请求频率
                    sub_files = self.fetch_files_recursive(
                        pwd_id, stoken, fid, item_path, depth + 1, max_depth
                    )
                    files.extend(sub_files)
                else:
                    # 创建文件节点
                    file_node = RawFileNode(
                        file_id=fid,
                        filename=name,
                        size=item_size,
                        full_path=f"/夸克分享{item_path}",
                        share_token=pwd_id,
                        source_context=""  # 将在上下文构建时注入
                    )
                    files.append(file_node)
                    logger.debug(f"添加文件: {name} ({self._format_size(item_size)})")
        
        except Exception as e:
            logger.error(f"遍历路径 '{current_path}' 时出错: {e}", exc_info=True)
        
        return files
    
    async def crawl_share_link(self, share_url: str, source_context: str = "") -> List[RawFileNode]:
        """
        从分享链接爬取文件列表 (异步版本)
        
        Args:
            share_url: 分享链接
            source_context: 源上下文信息
            
        Returns:
            文件节点列表
        """
        # 调用同步版本的fetch方法
        return self.fetch(share_url, source_context)
    
    def fetch(self, share_url: str, source_context: str = "") -> List[RawFileNode]:
        """
        从分享链接获取文件列表 (同步版本)
        
        Args:
            share_url: 分享链接
            source_context: 源上下文信息
            
        Returns:
            文件节点列表
        """
        if not self.cookie:
            logger.error("夸克网盘Cookie未配置，无法爬取文件")
            return []
        
        # 解析链接
        pwd_id, passcode, pdir_fid = self.parse_share_url(share_url)
        if not pwd_id:
            logger.warning(f"无效的分享链接格式: {share_url}")
            return []
        
        # 获取分享令牌
        stoken_resp = self.get_share_token(pwd_id, passcode)
        if stoken_resp.get("status") != 200:
            logger.warning(f"链接验证失败: {stoken_resp.get('message')}")
            return []
        
        stoken = stoken_resp.get("data", {}).get("stoken")
        if not stoken:
            logger.error("获取分享令牌失败")
            return []
        
        # 递归获取文件
        logger.info(f"开始爬取文件: {share_url}")
        files = self.fetch_files_recursive(pwd_id, stoken, pdir_fid)
        
        # 注入源上下文
        for file_node in files:
            file_node.source_context = source_context
        
        logger.info(f"爬取完成: 共获取 {len(files)} 个文件")
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
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取爬虫统计信息
        
        Returns:
            统计信息字典
        """
        return {
            "has_cookie": bool(self.cookie),
            "has_mobile_params": len(self.mparam) == 3,
            "base_url": self.base_url,
            "timeout": self.timeout,
            "retry_count": self.retry_count
        }


def create_quark_crawler(cookie: str = "") -> QuarkCrawler:
    """
    创建夸克爬虫实例的工厂函数
    
    Args:
        cookie: 夸克网盘Cookie
        
    Returns:
        配置好的夸克爬虫实例
    """
    return QuarkCrawler(cookie)