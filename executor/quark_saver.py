"""
执行器模块 - 夸克转存器
负责将选中的文件批量转存到夸克网盘
"""

import logging
import time
import asyncio
import aiohttp
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import json

from core.contracts import SelectedFile, SaveResult
from config.config_loader import get_config_value

logger = logging.getLogger(__name__)


class QuarkSaver:
    """
    夸克转存器
    实现批量文件转存功能，支持并发控制和错误处理
    """
    
    def __init__(self):
        """初始化夸克转存器"""
        # 获取夸克配置
        self.cookie = get_config_value("provider.quark_cookie", "")
        self.user_agent = get_config_value("provider.quark_user_agent", "")
        self.base_url = get_config_value("provider.quark_base_url", "")
        self.timeout = get_config_value("provider.quark_timeout", 30)
        self.retry_count = get_config_value("provider.quark_retry_count", 3)
        self.retry_delay = get_config_value("provider.quark_retry_delay", 1)
        
        # 并发控制
        self.max_concurrency = get_config_value("app.max_concurrency", 4)
        
        # 验证配置
        if not self.cookie:
            logger.warning("未配置夸克网盘Cookie，转存功能将不可用")
            self.enabled = False
        else:
            self.enabled = True
            logger.info(f"夸克转存器初始化完成 (并发数: {self.max_concurrency})")
    
    async def save_files(self, selected_files: List[SelectedFile], 
                        target_folder: str = "智能下载") -> SaveResult:
        """
        批量转存文件
        
        Args:
            selected_files: 选中的文件列表
            target_folder: 目标文件夹名称
            
        Returns:
            转存结果统计
        """
        if not self.enabled:
            logger.error("夸克转存器未启用，无法执行转存操作")
            return SaveResult(
                total_files=len(selected_files),
                success_count=0,
                failed_count=len(selected_files),
                failed_files=[f.file_node.filename for f in selected_files],
                execution_time=0.0
            )
        
        start_time = time.time()
        logger.info(f"开始批量转存: {len(selected_files)} 个文件 → {target_folder}")
        
        # 创建目标文件夹
        folder_id = await self._ensure_folder_exists(target_folder)
        if not folder_id:
            logger.error(f"无法创建目标文件夹: {target_folder}")
            return SaveResult(
                total_files=len(selected_files),
                success_count=0,
                failed_count=len(selected_files),
                failed_files=[f.file_node.filename for f in selected_files],
                execution_time=time.time() - start_time
            )
        
        # 并发转存文件
        success_count = 0
        failed_files = []
        
        # 使用信号量控制并发数
        semaphore = asyncio.Semaphore(self.max_concurrency)
        
        async def save_single_file(selected_file: SelectedFile) -> bool:
            """转存单个文件"""
            async with semaphore:
                try:
                    success = await self._save_single_file(selected_file, folder_id)
                    if success:
                        logger.info(f"转存成功: {selected_file.file_node.filename}")
                        return True
                    else:
                        logger.error(f"转存失败: {selected_file.file_node.filename}")
                        return False
                except Exception as e:
                    logger.error(f"转存异常: {selected_file.file_node.filename} - {str(e)}")
                    return False
        
        # 并发执行转存任务
        tasks = [save_single_file(sf) for sf in selected_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 统计结果
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed_files.append(selected_files[i].file_node.filename)
                logger.error(f"转存任务异常: {selected_files[i].file_node.filename} - {str(result)}")
            elif result:
                success_count += 1
            else:
                failed_files.append(selected_files[i].file_node.filename)
        
        execution_time = time.time() - start_time
        
        # 记录转存失败的文件
        if failed_files:
            await self._log_failed_files(failed_files, target_folder)
        
        result = SaveResult(
            total_files=len(selected_files),
            success_count=success_count,
            failed_count=len(failed_files),
            failed_files=failed_files,
            execution_time=execution_time
        )
        
        logger.info(f"批量转存完成: 成功 {success_count}/{len(selected_files)} "
                   f"({result.success_rate:.1%}), 耗时 {execution_time:.1f}s")
        
        return result
    
    async def _ensure_folder_exists(self, folder_name: str) -> Optional[str]:
        """
        确保目标文件夹存在，如果不存在则创建
        
        Args:
            folder_name: 文件夹名称
            
        Returns:
            文件夹ID，失败返回None
        """
        try:
            # 首先检查文件夹是否已存在
            folder_id = await self._find_folder(folder_name)
            if folder_id:
                logger.debug(f"文件夹已存在: {folder_name} (ID: {folder_id})")
                return folder_id
            
            # 创建新文件夹
            folder_id = await self._create_folder(folder_name)
            if folder_id:
                logger.info(f"创建文件夹成功: {folder_name} (ID: {folder_id})")
                return folder_id
            
            logger.error(f"创建文件夹失败: {folder_name}")
            return None
            
        except Exception as e:
            logger.error(f"文件夹操作异常: {folder_name} - {str(e)}")
            return None
    
    async def _find_folder(self, folder_name: str) -> Optional[str]:
        """
        查找指定名称的文件夹
        
        Args:
            folder_name: 文件夹名称
            
        Returns:
            文件夹ID，未找到返回None
        """
        # TODO: 实现文件夹查找逻辑
        # 这里需要调用夸克API获取文件夹列表并查找匹配的文件夹
        logger.debug(f"查找文件夹: {folder_name}")
        
        # 模拟API调用 - 实际实现需要根据夸克API文档
        await asyncio.sleep(0.1)  # 模拟网络延迟
        
        # 返回模拟的文件夹ID
        return f"folder_{hash(folder_name) % 10000}"
    
    async def _create_folder(self, folder_name: str) -> Optional[str]:
        """
        创建新文件夹
        
        Args:
            folder_name: 文件夹名称
            
        Returns:
            新文件夹ID，失败返回None
        """
        # TODO: 实现文件夹创建逻辑
        # 这里需要调用夸克API创建文件夹
        logger.debug(f"创建文件夹: {folder_name}")
        
        # 模拟API调用 - 实际实现需要根据夸克API文档
        await asyncio.sleep(0.2)  # 模拟网络延迟
        
        # 返回模拟的文件夹ID
        return f"new_folder_{hash(folder_name) % 10000}"
    
    async def _save_single_file(self, selected_file: SelectedFile, folder_id: str) -> bool:
        """
        转存单个文件 - v4.1 支持标准化重命名
        
        Args:
            selected_file: 选中的文件
            folder_id: 目标文件夹ID
            
        Returns:
            转存是否成功
        """
        file_node = selected_file.file_node
        
        # v4.1 检查是否需要重命名
        target_filename = selected_file.target_filename or file_node.filename
        needs_rename = (selected_file.target_filename and 
                       selected_file.target_filename != file_node.filename)
        
        if needs_rename:
            logger.info(f"将重命名文件: {file_node.filename} → {target_filename}")
        
        # 重试机制
        for attempt in range(self.retry_count):
            try:
                logger.debug(f"转存文件 (尝试 {attempt + 1}/{self.retry_count}): {file_node.filename}")
                
                # TODO: 实现实际的转存API调用
                # 这里需要根据夸克API文档实现文件转存逻辑
                success = await self._call_save_api(file_node, folder_id, target_filename)
                
                if success:
                    if needs_rename:
                        logger.info(f"转存并重命名成功: {target_filename}")
                    return True
                
                # 如果不是最后一次尝试，等待后重试
                if attempt < self.retry_count - 1:
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))  # 指数退避
                
            except Exception as e:
                logger.warning(f"转存尝试 {attempt + 1} 失败: {file_node.filename} - {str(e)}")
                
                # 如果不是最后一次尝试，等待后重试
                if attempt < self.retry_count - 1:
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))
        
        return False
    
    async def _call_save_api(self, file_node, folder_id: str, target_filename: str = None) -> bool:
        """
        调用夸克转存API - v4.1 支持重命名参数
        
        Args:
            file_node: 文件节点
            folder_id: 目标文件夹ID
            target_filename: 目标文件名（可选，用于重命名）
            
        Returns:
            API调用是否成功
        """
        # TODO: 实现实际的夸克API调用
        # 这里需要根据夸克API文档构造请求
        # 如果API支持rename参数，直接在转存时重命名
        # 否则需要先转存，再调用重命名API
        
        # 模拟API调用
        await asyncio.sleep(0.5)  # 模拟网络延迟
        
        # 记录重命名信息
        if target_filename and target_filename != file_node.filename:
            logger.debug(f"API调用包含重命名: {file_node.filename} → {target_filename}")
        
        # 模拟成功率 (90%)
        import random
        return random.random() > 0.1
    
    async def _log_failed_files(self, failed_files: List[str], target_folder: str):
        """
        记录转存失败的文件
        
        Args:
            failed_files: 失败文件列表
            target_folder: 目标文件夹
        """
        try:
            failed_log_path = get_config_value("output.failed_tasks_log", "instance/logs/failed_tasks.log")
            
            # 确保日志目录存在
            import os
            os.makedirs(os.path.dirname(failed_log_path), exist_ok=True)
            
            # 记录失败信息
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(failed_log_path, "a", encoding="utf-8") as f:
                f.write(f"\n=== 转存失败记录 {timestamp} ===\n")
                f.write(f"目标文件夹: {target_folder}\n")
                f.write(f"失败文件数: {len(failed_files)}\n")
                for filename in failed_files:
                    f.write(f"  - {filename}\n")
                f.write("\n")
            
            logger.info(f"转存失败日志已记录: {failed_log_path}")
            
        except Exception as e:
            logger.error(f"记录失败日志异常: {str(e)}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取转存器统计信息
        
        Returns:
            统计信息字典
        """
        return {
            "enabled": self.enabled,
            "max_concurrency": self.max_concurrency,
            "timeout": self.timeout,
            "retry_count": self.retry_count,
            "retry_delay": self.retry_delay,
            "has_cookie": bool(self.cookie)
        }


def create_quark_saver() -> QuarkSaver:
    """
    创建夸克转存器实例的工厂函数
    
    Returns:
        配置好的夸克转存器实例
    """
    return QuarkSaver()


# 同步包装器，用于在非异步环境中调用
def save_files_sync(selected_files: List[SelectedFile], 
                   target_folder: str = "智能下载") -> SaveResult:
    """
    同步版本的文件转存函数
    
    Args:
        selected_files: 选中的文件列表
        target_folder: 目标文件夹名称
        
    Returns:
        转存结果统计
    """
    saver = create_quark_saver()
    
    # 在新的事件循环中运行异步函数
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        return loop.run_until_complete(saver.save_files(selected_files, target_folder))
    finally:
        # 不关闭循环，因为可能被其他地方使用
        pass