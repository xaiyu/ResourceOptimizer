"""
智能媒体资源治理系统 v4.1 增强功能演示
展示动态漏斗筛选、一致性洗码、标准化命名的完整流程
"""

import asyncio
import logging
import json
from typing import List
from dataclasses import dataclass

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from core.contracts import (
    RawFileNode, VideoMeta, SelectedFile, SeriesState, SeriesInfo,
    DynamicFunnelConfig, ConsistencyConfig, NamingConfig
)
from io_layer.dynamic_funnel_selector import DynamicFunnelSelector
from core.consistency_checker import ConsistencyChecker
from core.naming_generator import StandardizedNamingGenerator
from executor.quark_auto_save_adapter import QuarkAutoSaveAdapter


def create_demo_data():
    """创建演示数据"""
    
    # 模拟源列表 (已排序)
    demo_sources = [
        {"title": "[4K Remux] 庆余年 第二季 全集", "url": "https://pan.quark.cn/s/demo1", "score": 95},
        {"title": "[1080p HDR] 庆余年2 完整版", "url": "https://pan.quark.cn/s/demo2", "score": 85},
        {"title": "庆余年 S02 [杜比视界]", "url": "https://pan.quark.cn/s/demo3", "score": 80},
        {"title": "[720p] 庆余年第二季", "url": "https://pan.quark.cn/s/demo4", "score": 60},
        {"title": "庆余年2 预告片合集", "url": "https://pan.quark.cn/s/demo5", "score": 30},
    ]
    
    # 模拟候选文件池 (包含不同大小的文件，测试一致性检查)
    demo_files = [
        # 正常大小的文件 (2GB左右)
        RawFileNode(
            file_id="file_001",
            filename="Joy.of.Life.S02E01.2160p.HDR.mkv",
            size=2100 * 1024 * 1024,  # 2.1GB
            full_path="/庆余年2/S02/Joy.of.Life.S02E01.2160p.HDR.mkv",
            share_token="https://pan.quark.cn/s/demo1",
            source_context="[4K Remux] 庆余年 第二季 全集"
        ),
        RawFileNode(
            file_id="file_002", 
            filename="Joy.of.Life.S02E02.2160p.HDR.mkv",
            size=1950 * 1024 * 1024,  # 1.95GB
            full_path="/庆余年2/S02/Joy.of.Life.S02E02.2160p.HDR.mkv",
            share_token="https://pan.quark.cn/s/demo1",
            source_context="[4K Remux] 庆余年 第二季 全集"
        ),
        RawFileNode(
            file_id="file_003",
            filename="Joy.of.Life.S02E03.2160p.HDR.mkv", 
            size=2050 * 1024 * 1024,  # 2.05GB
            full_path="/庆余年2/S02/Joy.of.Life.S02E03.2160p.HDR.mkv",
            share_token="https://pan.quark.cn/s/demo1",
            source_context="[4K Remux] 庆余年 第二季 全集"
        ),
        # 异常大小的文件 (应该被一致性检查剔除)
        RawFileNode(
            file_id="file_004",
            filename="Joy.of.Life.S02E04.Trailer.mkv",
            size=500 * 1024 * 1024,   # 500MB - 明显偏小
            full_path="/庆余年2/S02/Joy.of.Life.S02E04.Trailer.mkv", 
            share_token="https://pan.quark.cn/s/demo2",
            source_context="[1080p HDR] 庆余年2 完整版"
        ),
        RawFileNode(
            file_id="file_005",
            filename="Joy.of.Life.S02E05.2160p.HDR.mkv",
            size=2000 * 1024 * 1024,  # 2GB
            full_path="/庆余年2/S02/Joy.of.Life.S02E05.2160p.HDR.mkv",
            share_token="https://pan.quark.cn/s/demo3", 
            source_context="庆余年 S02 [杜比视界]"
        )
    ]
    
    # 模拟视频元数据
    demo_metas = [
        VideoMeta(title_cn="庆余年", season=2, episode=1, resolution="2160p", quality_score=95, is_valid_video=True),
        VideoMeta(title_cn="庆余年", season=2, episode=2, resolution="2160p", quality_score=93, is_valid_video=True),
        VideoMeta(title_cn="庆余年", season=2, episode=3, resolution="2160p", quality_score=94, is_valid_video=True),
        VideoMeta(title_cn="庆余年", season=2, episode=4, resolution="1080p", quality_score=30, is_valid_video=False),  # 预告片
        VideoMeta(title_cn="庆余年", season=2, episode=5, resolution="2160p", quality_score=92, is_valid_video=True),
    ]
    
    # 模拟剧集状态
    series_state = SeriesState(
        tmdb_total_aired={1, 2, 3, 4, 5, 6, 7, 8, 9, 10},  # 总共10集
        local_existing={6, 7, 8, 9, 10}  # 本地已有后5集
    )
    
    # 模拟剧集信息
    series_info = SeriesInfo(
        title="庆余年",
        season=2,
        total_episodes=10
    )
    
    return demo_sources, demo_files, demo_metas, series_state, series_info


async def demo_dynamic_funnel_selector():
    """演示动态漏斗筛选功能"""
    print("\n" + "="*60)
    print("🎯 演示1: 动态漏斗筛选器")
    print("="*60)
    
    # 创建配置
    config = DynamicFunnelConfig(
        batch_size=2,           # 每批2个源
        max_sources=6,          # 最多6个源
        stop_multiplier=2.0,    # 当候选数 > 缺集数 * 2 时停止
        enable_early_stop=True
    )
    
    # 创建筛选器
    selector = DynamicFunnelSelector(config)
    
    # 获取演示数据
    demo_sources, demo_files, demo_metas, series_state, series_info = create_demo_data()
    
    print(f"📊 输入源数量: {len(demo_sources)}")
    print(f"📊 缺失集数: {sorted(series_state.get_missing_episodes())}")
    print(f"📊 目标候选数: {len(series_state.get_missing_episodes()) * config.stop_multiplier}")
    
    # 模拟筛选过程 (这里简化，直接返回文件)
    class MockSelector(DynamicFunnelSelector):
        async def _process_batch(self, batch):
            # 模拟返回一些文件
            return demo_files[:len(batch)]
    
    mock_selector = MockSelector(config)
    selected_sources, candidate_pool = await mock_selector.select_with_funnel(
        demo_sources, series_state
    )
    
    print(f"✅ 筛选结果:")
    print(f"   选中源数: {len(selected_sources)}")
    print(f"   候选文件数: {len(candidate_pool)}")
    
    return candidate_pool


def demo_consistency_checker(candidate_files: List[RawFileNode], video_metas: List[VideoMeta]):
    """演示一致性检查功能"""
    print("\n" + "="*60)
    print("🔍 演示2: 智能一致性洗码")
    print("="*60)
    
    # 创建配置
    config = ConsistencyConfig(
        enable=True,
        size_deviation=0.3,  # 允许30%偏差
        min_samples=3
    )
    
    # 创建检查器
    checker = ConsistencyChecker(config)
    
    print(f"📊 输入文件数: {len(candidate_files)}")
    print("📊 文件大小分布:")
    for i, file in enumerate(candidate_files):
        print(f"   {file.filename}: {file.size/1024/1024:.1f} MB")
    
    # 执行一致性检查
    consistent_files = checker.check_size_consistency(candidate_files, video_metas)
    
    print(f"✅ 一致性检查结果:")
    print(f"   保留文件数: {len(consistent_files)}")
    print(f"   剔除文件数: {len(candidate_files) - len(consistent_files)}")
    
    return consistent_files


def demo_naming_generator(consistent_files: List[RawFileNode], video_metas: List[VideoMeta], series_info: SeriesInfo):
    """演示标准化命名功能"""
    print("\n" + "="*60)
    print("🏷️ 演示3: 标准化重命名系统")
    print("="*60)
    
    # 创建配置
    config = NamingConfig(
        enable=True,
        format_template="{title} S{season:02d}E{episode:02d} [{quality}].{ext}",
        quality_tags={
            "2160p": "4K",
            "1080p": "1080p",
            "hdr": "HDR",
            "atmos": "Atmos"
        }
    )
    
    # 创建命名生成器
    generator = StandardizedNamingGenerator(config)
    
    print(f"📊 输入文件数: {len(consistent_files)}")
    print("📊 命名转换:")
    
    selected_files = []
    for i, (file, meta) in enumerate(zip(consistent_files, video_metas[:len(consistent_files)])):
        if meta.is_valid_video:  # 只处理有效视频
            # 生成标准化文件名
            target_filename = generator.generate_filename(series_info, file, meta)
            
            # 创建选中文件对象
            selected_file = SelectedFile(
                file_node=file,
                video_meta=meta,
                selection_reason="演示选择",
                target_filename=target_filename,
                rename_metadata={
                    "original_filename": file.filename,
                    "generated_by": "demo_v4.1"
                }
            )
            selected_files.append(selected_file)
            
            print(f"   原文件名: {file.filename}")
            print(f"   新文件名: {target_filename}")
            print()
    
    print(f"✅ 标准化命名结果:")
    print(f"   处理文件数: {len(selected_files)}")
    
    return selected_files


def demo_enhanced_save_config(selected_files: List[SelectedFile], series_info: SeriesInfo):
    """演示增强转存配置生成"""
    print("\n" + "="*60)
    print("⚙️ 演示4: 增强转存配置生成")
    print("="*60)
    
    # 创建适配器
    adapter = QuarkAutoSaveAdapter()
    
    print(f"📊 输入文件数: {len(selected_files)}")
    
    # 生成增强配置
    config_path = adapter.create_enhanced_save_config(selected_files, series_info.title)
    
    print(f"✅ 配置文件已生成: {config_path}")
    
    # 读取并显示配置内容
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    print("📋 配置文件内容预览:")
    print(f"   版本: {config['version']}")
    print(f"   剧集: {config['series_info']['title']}")
    print(f"   任务数: {config['series_info']['total_tasks']}")
    print(f"   增强功能: {list(config['enhanced_features'].keys())}")
    
    return config_path


async def main():
    """主演示函数"""
    print("🚀 智能媒体资源治理系统 v4.1 增强功能演示")
    print("🎯 本演示将展示三大核心优化功能的完整流程")
    
    # 获取演示数据
    demo_sources, demo_files, demo_metas, series_state, series_info = create_demo_data()
    
    try:
        # 演示1: 动态漏斗筛选
        candidate_pool = await demo_dynamic_funnel_selector()
        
        # 演示2: 一致性检查
        consistent_files = demo_consistency_checker(candidate_pool, demo_metas)
        
        # 演示3: 标准化命名
        selected_files = demo_naming_generator(consistent_files, demo_metas, series_info)
        
        # 演示4: 增强转存配置
        config_path = demo_enhanced_save_config(selected_files, series_info)
        
        # 总结
        print("\n" + "="*60)
        print("🎉 v4.1 增强功能演示完成")
        print("="*60)
        print("✅ 动态漏斗筛选: 智能选择最优源，避免漏选")
        print("✅ 智能一致性洗码: 基于统计学剔除异常文件")
        print("✅ 标准化重命名: 生成媒体库友好的文件名")
        print("✅ 增强转存配置: 支持重命名和元数据丰富")
        print(f"\n📁 生成的配置文件: {config_path}")
        print("\n🚀 v4.1架构优化成功解决了漏选、品控粗糙、命名混乱三大痛点！")
        
    except Exception as e:
        print(f"❌ 演示过程中出现错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())