#!/usr/bin/env python3
"""
v4.1 优化功能演示脚本
展示动态漏斗筛选、智能一致性洗码和标准化重命名的效果
"""

import logging
import sys
import os
from typing import List

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.config_loader import get_config
from io_layer.source_manager import SourceManager
from core.decision_engine import DecisionMaker
from core.contracts import RawFileNode, VideoMeta, SelectedFile

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)


def demo_dynamic_funnel_selection():
    """演示动态漏斗筛选机制"""
    print("\n" + "=" * 60)
    print("🎯 v4.1 动态漏斗筛选机制演示")
    print("=" * 60)
    
    source_manager = SourceManager()
    
    # 创建测试源数据
    sources = {
        "庆余年第二季": [
            "普通源1,https://example.com/normal1",
            "普通源2,https://example.com/normal2", 
            "普通源3,https://example.com/normal3",
            "[4K Remux] 超高质量源,https://example.com/4k_remux",
            "[HDR] 高质量源,https://example.com/hdr",
            "[BluRay] 蓝光源,https://example.com/bluray",
            "低质量源720p,https://example.com/low",
            "[预告] 预告片源,https://example.com/trailer",
            "[Atmos] 全景声源,https://example.com/atmos",
            "测试源,https://example.com/test"
        ]
    }
    
    print(f"📊 总源数量: {len(sources['庆余年第二季'])}")
    
    # 传统模式 (不传递缺失集数)
    print("\n🔸 传统模式 (Top 3):")
    traditional_sources = source_manager.rank_sources(sources)
    print(f"   选择源数量: {len(traditional_sources)}")
    for i, source in enumerate(traditional_sources, 1):
        print(f"   {i}. {source.title} (评分: {source.score})")
    
    # 动态漏斗筛选模式 (缺失5集)
    print("\n🔸 动态漏斗筛选 (缺失5集):")
    dynamic_sources = source_manager.rank_sources(sources, missing_episodes=5)
    print(f"   选择源数量: {len(dynamic_sources)}")
    for i, source in enumerate(dynamic_sources, 1):
        print(f"   {i}. {source.title} (评分: {source.score})")
    
    # 动态漏斗筛选模式 (缺失10集)
    print("\n🔸 动态漏斗筛选 (缺失10集):")
    dynamic_sources_10 = source_manager.rank_sources(sources, missing_episodes=10)
    print(f"   选择源数量: {len(dynamic_sources_10)}")
    for i, source in enumerate(dynamic_sources_10, 1):
        print(f"   {i}. {source.title} (评分: {source.score})")
    
    print(f"\n✅ 动态漏斗筛选效果:")
    print(f"   - 传统模式: {len(traditional_sources)} 个源")
    print(f"   - 缺失5集: {len(dynamic_sources)} 个源 (+{len(dynamic_sources) - len(traditional_sources)})")
    print(f"   - 缺失10集: {len(dynamic_sources_10)} 个源 (+{len(dynamic_sources_10) - len(traditional_sources)})")
    print(f"   🎯 根据缺失集数动态调整源数量，提高资源覆盖率！")


def demo_size_consistency_check():
    """演示智能一致性洗码"""
    print("\n" + "=" * 60)
    print("🧠 v4.1 智能一致性洗码演示")
    print("=" * 60)
    
    decision_maker = DecisionMaker()
    
    # 创建测试文件 (包含离群值)
    test_files = [
        ("庆余年.S02E01.mkv", 2.1),  # 正常大小
        ("庆余年.S02E02.mkv", 2.0),  # 正常大小
        ("庆余年.S02E03.mkv", 2.2),  # 正常大小
        ("庆余年.S02E04.mkv", 1.9),  # 正常大小
        ("庆余年.S02E05.mkv", 0.5),  # 离群值 - 太小 (可能是预告片)
        ("庆余年.S02E06.mkv", 8.0),  # 离群值 - 太大 (可能是未压缩版)
    ]
    
    selected_files = []
    
    print("📊 原始文件列表:")
    for i, (filename, size_gb) in enumerate(test_files):
        size_bytes = int(size_gb * 1024 ** 3)
        
        file_node = RawFileNode(
            file_id=f"test_{i}",
            filename=filename,
            size=size_bytes,
            full_path=f"/test/{filename}",
            share_token="test_token",
            source_context="[4K HDR] 庆余年第二季"
        )
        
        video_meta = VideoMeta(
            title_cn="庆余年第二季",
            season=2,
            episode=i + 1,
            resolution="2160p",
            quality_score=85,
            is_valid_video=True
        )
        
        selected_file = SelectedFile(
            file_node=file_node,
            video_meta=video_meta,
            selection_reason="初步选择",
            priority=85
        )
        
        selected_files.append(selected_file)
        print(f"   {i+1}. {filename} - {size_gb:.1f}GB")
    
    # 计算统计信息
    sizes = [f.file_node.size for f in selected_files]
    median_size = sorted(sizes)[len(sizes)//2]
    median_gb = median_size / (1024**3)
    
    print(f"\n📈 统计分析:")
    print(f"   中位数大小: {median_gb:.1f}GB")
    print(f"   偏差阈值: 50%")
    
    # 执行一致性检查
    print(f"\n🔍 执行一致性洗码...")
    consistent_files = decision_maker._enforce_size_consistency(selected_files)
    
    print(f"\n✅ 一致性洗码结果:")
    print(f"   保留文件: {len(consistent_files)}/{len(selected_files)}")
    print(f"   剔除文件: {len(selected_files) - len(consistent_files)}")
    
    print(f"\n📋 保留的文件:")
    for i, file in enumerate(consistent_files, 1):
        size_gb = file.file_node.size / (1024**3)
        deviation = abs(file.file_node.size - median_size) / median_size
        print(f"   {i}. {file.file_node.filename} - {size_gb:.1f}GB (偏差: {deviation:.1%})")
    
    print(f"\n🎯 智能一致性洗码效果:")
    print(f"   - 自动剔除了 {len(selected_files) - len(consistent_files)} 个离群文件")
    print(f"   - 确保下载的剧集是同一版本、同一质量层级")
    print(f"   - 避免了'下了一整季，中间夹杂几个低清版'的情况")


def demo_standardized_naming():
    """演示标准化重命名"""
    print("\n" + "=" * 60)
    print("📝 v4.1 标准化重命名演示")
    print("=" * 60)
    
    decision_maker = DecisionMaker()
    
    # 创建测试文件 (混乱的原始文件名)
    test_files = [
        ("qyns2e01.4k.hdr.atmos.remux.mkv", 1, "2160p", 95),
        ("庆余年2_第02集_1080p_中字.mp4", 2, "1080p", 80),
        ("Joy.of.Life.S02E03.2160p.WEB-DL.H265.mkv", 3, "2160p", 88),
        ("【庆余年第二季】第4集 4K HDR 杜比全景声.mkv", 4, "2160p", 92),
        ("qyl_s2_ep05_uhd_bluray_remux.mkv", 5, "2160p", 90),
    ]
    
    selected_files = []
    
    print("📊 原始文件名 (混乱状态):")
    for i, (filename, episode, resolution, score) in enumerate(test_files):
        file_node = RawFileNode(
            file_id=f"test_{i}",
            filename=filename,
            size=2000000000,  # 2GB
            full_path=f"/test/{filename}",
            share_token="test_token",
            source_context="[4K HDR Atmos] 庆余年第二季"
        )
        
        video_meta = VideoMeta(
            title_cn="庆余年第二季",
            season=2,
            episode=episode,
            resolution=resolution,
            quality_score=score,
            is_valid_video=True
        )
        
        selected_file = SelectedFile(
            file_node=file_node,
            video_meta=video_meta,
            selection_reason="测试选择",
            priority=score
        )
        
        selected_files.append(selected_file)
        print(f"   {i+1}. {filename}")
    
    # 执行标准化重命名
    print(f"\n🔄 执行标准化重命名...")
    renamed_files = decision_maker._generate_standard_filenames(selected_files, "庆余年第二季")
    
    print(f"\n✅ 标准化重命名结果:")
    print(f"   格式: {'{title} S{season:02d}E{episode:02d} [{quality}].{ext}'}")
    
    print(f"\n📋 重命名对比:")
    for i, file in enumerate(renamed_files):
        original = file.file_node.filename
        target = file.target_filename
        print(f"   {i+1}. 原始: {original}")
        print(f"      标准: {target}")
        print()
    
    print(f"🎯 标准化重命名效果:")
    print(f"   - 统一命名格式，便于管理和识别")
    print(f"   - 自动提取质量标签 (4K, HDR, Atmos等)")
    print(f"   - 提高 Plex/Emby 的识别准确率")
    print(f"   - 实现'入库即规范'，无需后续整理")


def demo_integrated_pipeline():
    """演示完整的v4.1优化流程"""
    print("\n" + "=" * 60)
    print("🚀 v4.1 完整优化流程演示")
    print("=" * 60)
    
    print("📋 模拟场景:")
    print("   - 剧集: 庆余年第二季")
    print("   - 缺失: 5集")
    print("   - 源数量: 8个")
    print("   - 候选文件: 12个 (包含离群值)")
    
    # 1. 动态漏斗筛选
    print(f"\n🔸 步骤1: 动态漏斗筛选")
    source_manager = SourceManager()
    sources = {
        "庆余年第二季": [
            "[4K Remux HDR Atmos] 庆余年第二季,https://example.com/best",
            "[4K HDR] 庆余年第二季 完整版,https://example.com/4k",
            "[1080p] 庆余年第二季 高清版,https://example.com/1080p",
            "庆余年第二季 普通版,https://example.com/normal",
            "[720p] 庆余年第二季,https://example.com/720p",
            "[预告] 庆余年第二季 预告片,https://example.com/trailer",
            "庆余年第二季 测试版,https://example.com/test",
            "[BluRay] 庆余年第二季 蓝光版,https://example.com/bluray"
        ]
    }
    
    ranked_sources = source_manager.rank_sources(sources, missing_episodes=5)
    print(f"   ✅ 选择了 {len(ranked_sources)} 个优质源 (传统模式只会选3个)")
    
    # 2. 智能一致性洗码
    print(f"\n🔸 步骤2: 智能一致性洗码")
    decision_maker = DecisionMaker()
    
    # 模拟候选文件 (包含离群值)
    candidate_files = []
    file_sizes = [2.1, 2.0, 2.2, 1.9, 2.1, 0.3, 7.5, 2.0, 1.8, 2.3]  # 包含2个离群值
    
    for i, size_gb in enumerate(file_sizes):
        file_node = RawFileNode(
            file_id=f"candidate_{i}",
            filename=f"qyl_s2_e{i+1:02d}_messy_name.mkv",
            size=int(size_gb * 1024**3),
            full_path=f"/test/qyl_s2_e{i+1:02d}_messy_name.mkv",
            share_token="test_token",
            source_context="[4K HDR] 庆余年第二季"
        )
        
        video_meta = VideoMeta(
            title_cn="庆余年第二季",
            season=2,
            episode=i + 1,
            resolution="2160p",
            quality_score=85,
            is_valid_video=True
        )
        
        selected_file = SelectedFile(
            file_node=file_node,
            video_meta=video_meta,
            selection_reason="候选文件",
            priority=85
        )
        
        candidate_files.append(selected_file)
    
    consistent_files = decision_maker._enforce_size_consistency(candidate_files)
    print(f"   ✅ 剔除了 {len(candidate_files) - len(consistent_files)} 个离群文件")
    print(f"   📊 保留 {len(consistent_files)}/{len(candidate_files)} 个一致性文件")
    
    # 3. 标准化重命名
    print(f"\n🔸 步骤3: 标准化重命名")
    renamed_files = decision_maker._generate_standard_filenames(consistent_files[:3], "庆余年第二季")
    print(f"   ✅ 生成标准文件名")
    
    for file in renamed_files[:3]:  # 只显示前3个
        print(f"   📝 {file.file_node.filename} → {file.target_filename}")
    
    # 总结效果
    print(f"\n🎉 v4.1 优化效果总结:")
    print(f"   🎯 动态漏斗筛选: 根据缺失集数智能扩容，提高资源覆盖率")
    print(f"   🧠 智能一致性洗码: 自动剔除离群文件，确保版本一致性")
    print(f"   📝 标准化重命名: 生成规范文件名，提升管理效率")
    print(f"   ⚡ 整体提升: 解决'漏选'、'品控粗糙'、'命名混乱'三大痛点")


def main():
    """主函数"""
    print("🎬 智能媒体资源治理系统 v4.1 优化演示")
    print("=" * 60)
    print("本演示将展示v4.1版本的三大核心优化功能:")
    print("1. 🎯 动态漏斗筛选机制 - 解决资源漏选问题")
    print("2. 🧠 智能一致性洗码 - 解决品控粗糙问题") 
    print("3. 📝 标准化重命名 - 解决命名混乱问题")
    
    try:
        # 加载配置
        config = get_config()
        
        # 演示各个功能
        demo_dynamic_funnel_selection()
        demo_size_consistency_check()
        demo_standardized_naming()
        demo_integrated_pipeline()
        
        print(f"\n🎊 演示完成！")
        print(f"v4.1优化功能已成功实施，系统性能和用户体验得到显著提升！")
        
    except Exception as e:
        logger.error(f"演示过程中发生异常: {str(e)}", exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)