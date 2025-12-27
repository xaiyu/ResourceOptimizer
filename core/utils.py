"""
核心工具函数模块
提供系统级别的通用工具函数
"""

import asyncio
import logging
import concurrent.futures
from typing import Coroutine, TypeVar, Any

logger = logging.getLogger(__name__)

T = TypeVar('T')


def run_async_in_sync_context(coro: Coroutine[Any, Any, T]) -> T:
    """
    在同步上下文中安全运行异步代码的工具函数
    
    这个函数解决了在同步代码中调用异步函数时的事件循环冲突问题。
    它会智能检测当前的事件循环状态，并选择最合适的执行方式。
    
    处理的场景：
    1. 没有事件循环：创建新的事件循环并运行
    2. 有事件循环但未运行：直接在当前循环中运行
    3. 有事件循环且正在运行：在新线程中创建独立的事件循环运行
    
    Args:
        coro: 要执行的协程对象
        
    Returns:
        协程的执行结果
        
    Raises:
        Exception: 协程执行过程中的任何异常
        
    Example:
        >>> async def async_task():
        ...     return "Hello, World!"
        >>> 
        >>> # 在同步函数中调用
        >>> result = run_async_in_sync_context(async_task())
        >>> print(result)  # "Hello, World!"
    """
    try:
        # 尝试获取当前事件循环
        loop = asyncio.get_event_loop()
        
        if loop.is_running():
            # 情况3: 事件循环正在运行中
            # 在这种情况下，我们不能直接调用 loop.run_until_complete()
            # 因为它会导致 "RuntimeError: This event loop is already running"
            # 解决方案：在新线程中创建独立的事件循环
            logger.debug("检测到运行中的事件循环，在新线程中执行异步任务")
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        else:
            # 情况2: 有事件循环但未运行
            # 可以直接使用 run_until_complete
            logger.debug("使用现有事件循环执行异步任务")
            return loop.run_until_complete(coro)
            
    except RuntimeError as e:
        if "There is no current event loop" in str(e):
            # 情况1: 没有事件循环
            # 创建新的事件循环并运行
            logger.debug("未检测到事件循环，创建新的事件循环")
            return asyncio.run(coro)
        else:
            # 其他 RuntimeError，尝试创建新的事件循环
            logger.debug(f"事件循环异常: {e}，尝试创建新的事件循环")
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()
                # 清理事件循环引用，避免内存泄漏
                asyncio.set_event_loop(None)


def run_async_in_sync_context_safe(coro: Coroutine[Any, Any, T], 
                                  fallback_result: T = None) -> T:
    """
    安全版本的异步执行函数，包含异常处理
    
    这是 run_async_in_sync_context 的安全包装版本，
    当异步执行失败时会返回默认值而不是抛出异常。
    
    Args:
        coro: 要执行的协程对象
        fallback_result: 执行失败时的默认返回值
        
    Returns:
        协程的执行结果，或失败时的默认值
        
    Example:
        >>> async def risky_task():
        ...     raise ValueError("Something went wrong")
        >>> 
        >>> result = run_async_in_sync_context_safe(
        ...     risky_task(), 
        ...     fallback_result="默认结果"
        ... )
        >>> print(result)  # "默认结果"
    """
    try:
        return run_async_in_sync_context(coro)
    except Exception as e:
        logger.error(f"异步任务执行失败: {e}", exc_info=True)
        return fallback_result


class AsyncContextManager:
    """
    异步上下文管理器，用于在同步代码中管理异步资源
    
    这个类可以帮助在同步代码中安全地管理需要异步初始化和清理的资源。
    
    Example:
        >>> async def create_resource():
        ...     return "resource"
        >>> 
        >>> async def cleanup_resource(resource):
        ...     print(f"Cleaning up {resource}")
        >>> 
        >>> with AsyncContextManager(create_resource(), cleanup_resource) as resource:
        ...     print(f"Using {resource}")
    """
    
    def __init__(self, create_coro: Coroutine, cleanup_func=None):
        """
        初始化异步上下文管理器
        
        Args:
            create_coro: 创建资源的协程
            cleanup_func: 清理资源的函数（可选）
        """
        self.create_coro = create_coro
        self.cleanup_func = cleanup_func
        self.resource = None
    
    def __enter__(self):
        """进入上下文，创建资源"""
        self.resource = run_async_in_sync_context(self.create_coro)
        return self.resource
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文，清理资源"""
        if self.cleanup_func and self.resource:
            if asyncio.iscoroutinefunction(self.cleanup_func):
                # 如果清理函数是异步的
                run_async_in_sync_context(self.cleanup_func(self.resource))
            else:
                # 如果清理函数是同步的
                self.cleanup_func(self.resource)


def get_event_loop_info() -> dict:
    """
    获取当前事件循环的详细信息，用于调试
    
    Returns:
        dict: 包含事件循环状态信息的字典
        
    Example:
        >>> info = get_event_loop_info()
        >>> print(info)
        {
            'has_loop': True,
            'is_running': False,
            'loop_type': 'ProactorEventLoop',
            'thread_id': 12345
        }
    """
    import threading
    
    info = {
        'thread_id': threading.get_ident(),
        'has_loop': False,
        'is_running': False,
        'loop_type': None,
        'loop_id': None
    }
    
    try:
        loop = asyncio.get_event_loop()
        info['has_loop'] = True
        info['is_running'] = loop.is_running()
        info['loop_type'] = type(loop).__name__
        info['loop_id'] = id(loop)
    except RuntimeError:
        pass
    
    return info


# 为了向后兼容，提供一个简化的别名
run_async = run_async_in_sync_context