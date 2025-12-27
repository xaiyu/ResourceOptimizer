"""
重试循环引擎
处理批次失败和重试逻辑，实现指数退避策略
"""

import asyncio
import logging
import time
from typing import Callable, List, Any, Dict, Optional
from dataclasses import dataclass

from core.contracts import RetryConfig, RetryResult

logger = logging.getLogger(__name__)


class RetryLoopEngine:
    """
    重试循环引擎
    
    核心功能：
    1. 指数退避重试策略
    2. 最大重试次数限制
    3. 失败原因记录
    4. 部分结果返回机制
    """
    
    def __init__(self, config: RetryConfig):
        """
        初始化重试循环引擎
        
        Args:
            config: 重试配置
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        self.logger.info(f"重试循环引擎初始化:")
        self.logger.info(f"  最大重试次数: {config.max_retries}")
        self.logger.info(f"  退避因子: {config.backoff_factor}")
        self.logger.info(f"  初始延迟: {config.initial_delay}s")
        self.logger.info(f"  最大延迟: {config.max_delay}s")
    
    async def execute_with_retry(self, 
                                batch_processor: Callable,
                                batches: List[Any],
                                context: Optional[Dict[str, Any]] = None) -> RetryResult:
        """
        执行带重试的批次处理
        
        Args:
            batch_processor: 批次处理函数
            batches: 批次列表
            context: 处理上下文
            
        Returns:
            重试结果
        """
        retry_history = []
        total_delay = 0.0
        final_result = None
        
        self.logger.info(f"🔄 开始重试循环处理: {len(batches)} 个批次")
        
        for attempt in range(self.config.max_retries + 1):  # +1 for initial attempt
            try:
                start_time = time.time()
                
                self.logger.info(f"📦 尝试 {attempt + 1}/{self.config.max_retries + 1}")
                
                # 执行批次处理
                result = await batch_processor(batches, context)
                
                execution_time = time.time() - start_time
                
                # 记录成功的尝试
                retry_history.append({
                    "attempt": attempt + 1,
                    "success": True,
                    "execution_time": execution_time,
                    "result_summary": self._summarize_result(result),
                    "error": None,
                    "delay_before": 0.0 if attempt == 0 else self._calculate_delay(attempt - 1)
                })
                
                self.logger.info(f"✅ 批次处理成功 (尝试 {attempt + 1}, 耗时: {execution_time:.2f}s)")
                
                return RetryResult(
                    success=True,
                    total_attempts=attempt + 1,
                    final_result=result,
                    retry_history=retry_history,
                    total_delay=total_delay
                )
                
            except Exception as e:
                execution_time = time.time() - start_time
                
                self.logger.warning(f"❌ 批次处理失败 (尝试 {attempt + 1}): {str(e)}")
                
                # 记录失败的尝试
                retry_history.append({
                    "attempt": attempt + 1,
                    "success": False,
                    "execution_time": execution_time,
                    "result_summary": None,
                    "error": str(e),
                    "delay_before": 0.0 if attempt == 0 else self._calculate_delay(attempt - 1)
                })
                
                # 如果还有重试机会
                if attempt < self.config.max_retries:
                    delay = self._calculate_delay(attempt)
                    total_delay += delay
                    
                    self.logger.info(f"⏳ 等待 {delay:.2f}s 后重试...")
                    await asyncio.sleep(delay)
                else:
                    # 达到最大重试次数
                    self.logger.error(f"🚫 达到最大重试次数 ({self.config.max_retries}), 处理失败")
                    
                    return RetryResult(
                        success=False,
                        total_attempts=attempt + 1,
                        final_result=final_result,
                        retry_history=retry_history,
                        total_delay=total_delay
                    )
        
        # 这里不应该到达，但为了安全起见
        return RetryResult(
            success=False,
            total_attempts=self.config.max_retries + 1,
            final_result=final_result,
            retry_history=retry_history,
            total_delay=total_delay
        )
    
    def _calculate_delay(self, attempt: int) -> float:
        """
        计算指数退避延迟
        
        Args:
            attempt: 尝试次数 (从0开始)
            
        Returns:
            延迟时间(秒)
        """
        # 指数退避公式: initial_delay * (backoff_factor ^ attempt)
        delay = self.config.initial_delay * (self.config.backoff_factor ** attempt)
        
        # 限制最大延迟
        delay = min(delay, self.config.max_delay)
        
        return delay
    
    def _summarize_result(self, result: Any) -> str:
        """
        总结处理结果
        
        Args:
            result: 处理结果
            
        Returns:
            结果摘要字符串
        """
        if result is None:
            return "None"
        
        if isinstance(result, (list, tuple)):
            return f"列表/元组 (长度: {len(result)})"
        elif isinstance(result, dict):
            return f"字典 (键数: {len(result)})"
        elif hasattr(result, '__dict__'):
            # 对象类型
            return f"{type(result).__name__} 对象"
        else:
            return str(type(result).__name__)
    
    async def execute_single_batch_with_retry(self, 
                                            batch_processor: Callable,
                                            single_batch: Any,
                                            context: Optional[Dict[str, Any]] = None) -> RetryResult:
        """
        执行单个批次的重试处理
        
        Args:
            batch_processor: 批次处理函数
            single_batch: 单个批次
            context: 处理上下文
            
        Returns:
            重试结果
        """
        return await self.execute_with_retry(batch_processor, [single_batch], context)
    
    def get_retry_statistics(self, retry_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        获取重试统计信息
        
        Args:
            retry_history: 重试历史
            
        Returns:
            统计信息
        """
        if not retry_history:
            return {}
        
        total_attempts = len(retry_history)
        successful_attempts = sum(1 for attempt in retry_history if attempt["success"])
        failed_attempts = total_attempts - successful_attempts
        
        total_execution_time = sum(attempt["execution_time"] for attempt in retry_history)
        total_delay_time = sum(attempt["delay_before"] for attempt in retry_history)
        
        return {
            "total_attempts": total_attempts,
            "successful_attempts": successful_attempts,
            "failed_attempts": failed_attempts,
            "success_rate": successful_attempts / total_attempts if total_attempts > 0 else 0.0,
            "total_execution_time": total_execution_time,
            "total_delay_time": total_delay_time,
            "average_execution_time": total_execution_time / total_attempts if total_attempts > 0 else 0.0,
            "final_success": retry_history[-1]["success"] if retry_history else False
        }
    
    def get_statistics(self) -> dict:
        """获取引擎统计信息"""
        return {
            "config": {
                "max_retries": self.config.max_retries,
                "backoff_factor": self.config.backoff_factor,
                "initial_delay": self.config.initial_delay,
                "max_delay": self.config.max_delay
            }
        }


class BatchProcessor:
    """
    批次处理器基类
    提供标准的批次处理接口
    """
    
    async def process_batch(self, batch: Any, context: Optional[Dict[str, Any]] = None) -> Any:
        """
        处理单个批次
        
        Args:
            batch: 批次数据
            context: 处理上下文
            
        Returns:
            处理结果
        """
        raise NotImplementedError("子类必须实现 process_batch 方法")
    
    async def process_batches(self, batches: List[Any], context: Optional[Dict[str, Any]] = None) -> List[Any]:
        """
        处理多个批次
        
        Args:
            batches: 批次列表
            context: 处理上下文
            
        Returns:
            处理结果列表
        """
        results = []
        for batch in batches:
            result = await self.process_batch(batch, context)
            results.append(result)
        return results


def create_retry_loop_engine() -> RetryLoopEngine:
    """
    创建重试循环引擎实例的工厂函数
    
    Returns:
        配置好的重试循环引擎实例
    """
    from config.config_loader import create_dynamic_funnel_config
    
    funnel_config = create_dynamic_funnel_config()
    return RetryLoopEngine(funnel_config.retry_config)


# 便捷的重试装饰器
def with_retry(retry_config: Optional[RetryConfig] = None):
    """
    重试装饰器
    
    Args:
        retry_config: 重试配置，如果为None则使用默认配置
        
    Returns:
        装饰器函数
    """
    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            if retry_config is None:
                engine = create_retry_loop_engine()
            else:
                engine = RetryLoopEngine(retry_config)
            
            async def single_call(batches, context):
                return await func(*args, **kwargs)
            
            result = await engine.execute_with_retry(single_call, [None])
            
            if result.success:
                return result.final_result
            else:
                # 抛出最后一个错误
                last_error = None
                for attempt in reversed(result.retry_history):
                    if attempt["error"]:
                        last_error = attempt["error"]
                        break
                
                raise Exception(f"重试失败: {last_error}")
        
        return wrapper
    return decorator