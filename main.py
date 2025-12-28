"""
智能媒体资源治理系统 v4.1 主程序
基于Pipeline + Map-Reduce + Context Injection架构
v4.1 新增: 动态漏斗循环 + 增强组件集成
"""

import logging
import sys
import os
import time
import argparse
from typing import List, Optional, Dict

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.config_loader import get_config, get_config_value
from io_layer.source_manager import create_source_manager
from io_layer.context_builder import create_context_builder
from core.llm_client import create_llm_client
from core.decision_engine import create_decision_maker
from executor.quark_saver import create_quark_saver, save_files_sync
from core.contracts import AnalysisContext, SelectedFile
from core.pipeline_orchestrator import create_pipeline_orchestrator

# 配置日志
def setup_logging():
    """设置日志系统"""
    log_level = get_config_value("logging.level", "INFO")
    log_format = get_config_value("logging.format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    log_file = get_config_value("logging.file", "instance/logs/smart_chase.log")
    
    # 确保日志目录存在
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # 配置根日志器
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding='utf-8')
        ]
    )

logger = logging.getLogger(__name__)


class SmartChaseSystem:
    """
    智能媒体资源治理系统主类
    编排完整的Pipeline流程
    """
    
    def __init__(self):
        """初始化系统组件"""
        logger.info("初始化智能媒体资源治理系统 v4.1")
        
        # v4.1+ 优先使用管道编排器
        try:
            self.pipeline_orchestrator = create_pipeline_orchestrator()
            self.use_enhanced_pipeline = True
            logger.info("✅ 管道编排器初始化成功, 启用增强模式")
        except Exception as e:
            logger.warning(f"⚠️ 管道编排器初始化失败: {e}")
            logger.warning("🔄 降级到传统组件模式")
            self.use_enhanced_pipeline = False
            
            # 降级到传统组件初始化
            self.source_manager = create_source_manager()
            self.context_builder = create_context_builder()
            self.llm_client = create_llm_client()
            self.decision_maker = create_decision_maker()
            self.quark_saver = create_quark_saver()
        
        logger.info("所有模块初始化完成")
    
    @staticmethod
    def run_async_safely(coro, fallback_result=None):
        """
        在同步上下文中安全运行异步代码的静态方法
        
        这是一个便捷的静态方法，封装了复杂的事件循环检测逻辑。
        其他模块可以直接调用此方法来执行异步代码，无需创建 SmartChaseSystem 实例。
        
        Args:
            coro: 要执行的协程对象
            fallback_result: 执行失败时的默认返回值
            
        Returns:
            协程的执行结果，或失败时的默认值
            
        Example:
            >>> async def fetch_data():
            ...     return "data"
            >>> 
            >>> result = SmartChaseSystem.run_async_safely(fetch_data())
            >>> print(result)  # "data"
        """
        from core.utils import run_async_in_sync_context_safe
        return run_async_in_sync_context_safe(coro, fallback_result)
    
    def process_series(self, series_title: str, sources: Dict[str, str], 
                      target_folder: Optional[str] = None) -> dict:
        """
        处理单个剧集的完整流程 - v4.1 多源异构标题适配
        
        核心功能：
        1. 接收官方标题和分享标题字典
        2. 基于分享标题进行源头竞价
        3. 使用官方标题作为LLM识别基准
        4. 动态漏斗筛选优化API调用
        5. 增强决策引擎确保质量一致性
        
        Args:
            series_title: 剧集官方正规标题（如"庆余年第二季"）
            sources: 源字典，Key为资源分享标题（如"[4K Remux] QYN.S02.2160p"），
                    Value为资源链接（如"https://pan.quark.cn/s/xxx"）
            target_folder: 目标文件夹名称，默认为"{series_title}_智能下载"
            
        Returns:
            dict: 处理结果统计，包含：
                - success: 是否成功
                - series_title: 剧集标题
                - source_count: 处理的源数量
                - selected_count: 选择的文件数量
                - save_result: 转存结果统计
                - execution_time: 执行时间
                - mode: 处理模式（enhanced/legacy）
                
        Example:
            >>> system = SmartChaseSystem()
            >>> sources = {
            ...     "[4K Remux] QYN.S02.2160p.ZhangSan": "https://pan.quark.cn/s/demo1",
            ...     "庆余年2.1080p.HDR.LiSi": "https://pan.quark.cn/s/demo2"
            ... }
            >>> result = system.process_series("庆余年第二季", sources)
            >>> print(f"成功处理: {result['success']}")
        """
        start_time = time.time()
        logger.info(f"开始处理剧集: {series_title}")
        logger.info(f"接收到 {len(sources)} 个源，使用多源异构标题适配模式")
        
        try:
            # v4.1+ 优先使用增强管道
            if self.use_enhanced_pipeline:
                logger.info("🚀 使用增强管道处理")
                
                # 保持完整的源信息 (标题+URL) 传递给增强管道
                # 不再丢弃分享标题，确保评分系统和LLM上下文完整
                
                # 使用工具函数在同步上下文中运行异步代码
                from core.utils import run_async_in_sync_context
                
                result = run_async_in_sync_context(
                    self.pipeline_orchestrator.process_series_enhanced(
                        series_title, sources, target_folder
                    )
                )
                
                return result
            
            # 降级到传统处理流程
            logger.info("🔧 使用传统管道处理")
            return self._process_series_legacy(series_title, sources, target_folder, start_time)
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"处理剧集时发生异常: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "execution_time": execution_time
            }
    
    def _process_series_legacy(self, series_title: str, sources: Dict[str, str], 
                              target_folder: Optional[str], start_time: float) -> dict:
        """
        传统剧集处理流程 (降级模式) - 支持多源异构标题适配
        
        Args:
            series_title: 剧集标题（官方正规标题）
            sources: 源字典，Key为资源分享标题，Value为资源链接
            target_folder: 目标文件夹名称
            start_time: 开始时间
            
        Returns:
            处理结果统计
        """
        # 预步骤: 快速状态查询 - 获取缺失集数用于动态漏斗筛选
        logger.info("=" * 50)
        logger.info("预步骤: 快速状态查询")
        logger.info("=" * 50)
        
        # 快速获取剧集状态以计算缺失集数
        from io_layer.state_provider import create_state_provider
        state_provider = create_state_provider()
        series_state = state_provider.get_state_with_cache(series_title)
        
        missing_episodes = len(series_state.tmdb_total_aired) - len(series_state.local_existing)
        logger.info(f"剧集状态: TMDB {len(series_state.tmdb_total_aired)} 集, "
                   f"本地 {len(series_state.local_existing)} 集, "
                   f"缺失 {missing_episodes} 集")
        
        # 第一步: 源头竞价 - v4.1 动态漏斗筛选 + 多源异构标题适配
        logger.info("\n" + "=" * 50)
        logger.info("第一步: 源头竞价 (v4.1 动态漏斗筛选 + 多源异构标题适配)")
        logger.info("=" * 50)
        
        # 构建格式: "分享标题,URL" - 使用分享标题而非自动生成的"源{i+1}"
        sources_dict = {
            series_title: [f"{share_title},{url}" for share_title, url in sources.items()]
        }
        
        logger.info(f"构建源字典完成，包含 {len(sources)} 个分享标题:")
        for i, (share_title, url) in enumerate(list(sources.items())[:3], 1):  # 显示前3个
            logger.info(f"  {i}. {share_title[:50]}...")
        
        ranked_sources = self.source_manager.rank_sources(sources_dict, missing_episodes)
        if not ranked_sources:
            logger.error("没有有效的源链接")
            return {"success": False, "error": "没有有效的源链接"}
        
        logger.info(f"源头竞价完成: 选择了 {len(ranked_sources)} 个优质源")
        for i, source in enumerate(ranked_sources[:5], 1):  # 显示前5个
            logger.info(f"  {i}. {source.title} (评分: {source.score})")
        
        # 第二步: 上下文构建 - 爬取文件并构建分析上下文
        logger.info("\n" + "=" * 50)
        logger.info("第二步: 上下文构建")
        logger.info("=" * 50)
        
        # 将RankedSource对象转换为字典格式
        sources_for_context = [{"title": s.title, "url": s.url} for s in ranked_sources]
        context = self.context_builder.build_context(sources_for_context, series_title)
        if not context or not context.candidates:
            logger.error("上下文构建失败或没有找到候选文件")
            return {"success": False, "error": "没有找到候选文件"}
        
        logger.info(f"上下文构建完成: 找到 {len(context.candidates)} 个候选文件")
        logger.info(f"剧集状态: TMDB {len(context.state.tmdb_total_aired)} 集, "
                   f"本地 {len(context.state.local_existing)} 集")
        
        # 第三步: LLM智能解析 - 解析文件元数据 + 官方标题基准
        logger.info("\n" + "=" * 50)
        logger.info("第三步: LLM智能解析 (官方标题基准)")
        logger.info("=" * 50)
        
        # 传递官方标题给LLM客户端作为基准锚点
        logger.info(f"使用官方标题作为基准: {series_title}")
        parsed_results = self.llm_client.parse_files(context.candidates, standard_title=series_title)
        if not parsed_results:
            logger.error("LLM解析失败")
            return {"success": False, "error": "LLM解析失败"}
        
        valid_results = [r for r in parsed_results if r.is_valid_video]
        logger.info(f"LLM解析完成: {len(parsed_results)} 个文件, "
                   f"{len(valid_results)} 个有效视频")
        
        # 第四步: 逻辑裁决 - v4.1 智能一致性洗码 + 选择最优文件
        logger.info("\n" + "=" * 50)
        logger.info("第四步: 逻辑裁决 (v4.1 智能一致性洗码)")
        logger.info("=" * 50)
        
        selected_files = self.decision_maker.decide(context, parsed_results)
        if not selected_files:
            logger.warning("没有选择到任何文件")
            return {"success": True, "selected_count": 0, "message": "没有需要下载的文件"}
        
        logger.info(f"逻辑裁决完成: 选择了 {len(selected_files)} 个文件")
        
        # 显示选择结果
        total_size = sum(f.file_node.size for f in selected_files)
        logger.info(f"选择文件总大小: {total_size/(1024**3):.1f} GB")
        
        for i, selected in enumerate(selected_files[:5], 1):  # 显示前5个
            video_meta = selected.video_meta
            logger.info(f"  {i}. E{video_meta.episode:02d}: {video_meta.resolution} "
                       f"({video_meta.quality_score}分)")
        
        # 第五步: 批量转存 - v4.1 标准化重命名
        logger.info("\n" + "=" * 50)
        logger.info("第五步: 批量转存 (v4.1 标准化重命名)")
        logger.info("=" * 50)
        
        if not target_folder:
            target_folder = f"{series_title}_智能下载"
        
        save_result = save_files_sync(selected_files, target_folder)
        
        logger.info(f"批量转存完成: 成功 {save_result.success_count}/{save_result.total_files} "
                   f"({save_result.success_rate:.1%})")
        
        # 处理完成
        execution_time = time.time() - start_time
        
        result = {
            "success": True,
            "series_title": series_title,
            "missing_episodes": missing_episodes,
            "source_count": len(ranked_sources),
            "candidate_count": len(context.candidates),
            "parsed_count": len(parsed_results),
            "valid_count": len(valid_results),
            "selected_count": len(selected_files),
            "save_result": {
                "total_files": save_result.total_files,
                "success_count": save_result.success_count,
                "failed_count": save_result.failed_count,
                "success_rate": save_result.success_rate
            },
            "execution_time": execution_time,
            "total_size_gb": total_size / (1024**3),
            "mode": "legacy"
        }
        
        logger.info(f"\n🎉 剧集处理完成: {series_title}")
        logger.info(f"总耗时: {execution_time:.1f} 秒")
        logger.info(f"转存成功率: {save_result.success_rate:.1%}")
        
        return result
    
    def batch_process(self, series_list: List[dict]) -> List[dict]:
        """
        批量处理多个剧集
        
        Args:
            series_list: 剧集列表, 每个元素包含 title 和 sources (Dict[str, str])
            
        Returns:
            处理结果列表
        """
        logger.info(f"开始批量处理: {len(series_list)} 个剧集")
        
        results = []
        for i, series_info in enumerate(series_list, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"处理第 {i}/{len(series_list)} 个剧集")
            logger.info(f"{'='*60}")
            
            title = series_info.get("title", f"未知剧集{i}")
            sources = series_info.get("sources", {})  # 现在是Dict而不是List
            target_folder = series_info.get("target_folder")
            
            result = self.process_series(title, sources, target_folder)
            results.append(result)
            
            # 简短休息, 避免API过载
            if i < len(series_list):
                time.sleep(1)
        
        # 批量处理统计
        successful = [r for r in results if r.get("success", False)]
        total_files = sum(r.get("save_result", {}).get("total_files", 0) for r in successful)
        total_success = sum(r.get("save_result", {}).get("success_count", 0) for r in successful)
        
        logger.info(f"\n🎊 批量处理完成:")
        logger.info(f"  处理剧集: {len(successful)}/{len(series_list)} 成功")
        logger.info(f"  转存文件: {total_success}/{total_files} 成功")
        
        return results
    
    def get_system_status(self) -> dict:
        """
        获取系统状态
        
        Returns:
            系统状态信息
        """
        if self.use_enhanced_pipeline:
            # 使用管道编排器的状态
            return self.pipeline_orchestrator.get_system_status()
        else:
            # 传统组件状态
            return {
                "source_manager": self.source_manager.get_statistics(),
                "context_builder": self.context_builder.get_statistics(),
                "llm_client": self.llm_client.get_statistics(),
                "decision_maker": self.decision_maker.get_statistics(),
                "quark_saver": self.quark_saver.get_statistics(),
                "mode": "legacy"
            }


def create_demo_series_list() -> List[dict]:
    """
    创建演示用的剧集列表 - 展示多源异构标题适配功能
    
    演示场景：
    1. 庆余年第二季 - 展示缩写识别（QYN=庆余年）
    2. 不同质量标识符的识别（4K Remux, 1080p HDR, 720p）
    3. 分享标题与官方标题的智能匹配
    
    Returns:
        List[dict]: 演示剧集列表，每个元素包含：
            - title: 官方正规标题
            - sources: 分享标题到链接的映射
            - target_folder: 目标文件夹（可选）
    """
    return [
        {
            "title": "庆余年第二季",
            "sources": {
                "[4K Remux] QYN.S02.2160p.ZhangSan": "https://pan.quark.cn/s/demo123456",
                "庆余年2.1080p.HDR.LiSi": "https://pan.quark.cn/s/demo789012", 
                "QYN第二季.720p.WangWu": "https://pan.quark.cn/s/demo345678"
            },
            "target_folder": "庆余年第二季_智能下载"
        }
    ]


def main():
    """主程序入口"""
    # 设置日志
    setup_logging()
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="智能媒体资源治理系统 v4.1")
    parser.add_argument("--title", type=str, help="剧集标题")
    parser.add_argument("--sources", type=str, nargs="+", help="源链接列表")
    parser.add_argument("--target", type=str, help="目标文件夹名称")
    parser.add_argument("--demo", action="store_true", help="运行演示模式")
    parser.add_argument("--status", action="store_true", help="显示系统状态")
    
    args = parser.parse_args()
    
    logger.info("智能媒体资源治理系统 v4.1 启动")
    
    # 加载配置
    config = get_config()
    logger.info("配置加载完成")
    
    # 创建系统实例
    system = SmartChaseSystem()
    
    try:
        if args.status:
            # 显示系统状态
            status = system.get_system_status()
            print("\n" + "=" * 60)
            print("系统状态")
            print("=" * 60)
            
            for module_name, module_status in status.items():
                print(f"\n{module_name}:")
                if isinstance(module_status, dict):
                    for key, value in module_status.items():
                        print(f"  {key}: {value}")
                else:
                    print(f"  {module_status}")
        
        elif args.demo:
            # 演示模式
            logger.info("运行演示模式")
            series_list = create_demo_series_list()
            results = system.batch_process(series_list)
            
            print("\n" + "=" * 60)
            print("演示模式处理结果")
            print("=" * 60)
            
            for result in results:
                if result.get("success"):
                    print(f"\n✅ {result['series_title']}: 成功")
                    print(f"   转存: {result['save_result']['success_count']}/{result['save_result']['total_files']}")
                    print(f"   耗时: {result['execution_time']:.1f}s")
                else:
                    print(f"\n❌ 处理失败: {result.get('error', '未知错误')}")
        
        elif args.title and args.sources:
            # 单个剧集处理 - 兼容旧格式，自动转换为新格式
            logger.info("检测到命令行模式，将URL列表转换为多源异构格式")
            
            # 将List[str]转换为Dict[str, str]以兼容新接口
            sources_dict = {}
            for i, url in enumerate(args.sources, 1):
                # 为兼容性生成简单的分享标题
                share_title = f"命令行源{i}"
                sources_dict[share_title] = url
            
            logger.info(f"转换完成: {len(args.sources)} 个URL -> {len(sources_dict)} 个源")
            
            result = system.process_series(args.title, sources_dict, args.target)
            
            if result.get("success"):
                print(f"\n✅ 处理成功: {args.title}")
                save_result = result.get("save_result", {})
                print(f"转存结果: {save_result.get('success_count', 0)}/{save_result.get('total_files', 0)} 成功")
            else:
                print(f"\n❌ 处理失败: {result.get('error', '未知错误')}")
        
        else:
            # 显示帮助信息
            parser.print_help()
            print("\n使用示例:")
            print("  python main.py --demo                    # 运行演示模式（多源异构标题适配）")
            print("  python main.py --status                  # 显示系统状态")
            print("  python main.py --title '庆余年第二季' --sources 'url1' 'url2'  # 处理单个剧集（兼容模式）")
            print("\n注意: 新版本支持多源异构标题适配，建议使用演示模式体验完整功能")
    
    except KeyboardInterrupt:
        logger.info("用户中断程序")
    except Exception as e:
        logger.error(f"程序执行异常: {str(e)}", exc_info=True)
    finally:
        logger.info("智能媒体资源治理系统退出")


if __name__ == "__main__":
    main()