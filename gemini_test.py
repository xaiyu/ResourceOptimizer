import asyncio
import logging
import sys
from typing import List

# 确保能导入项目模块
sys.path.append('.')

from core.contracts import (
    RawFileNode, VideoMeta, SeriesInfo, SeriesState,
    DynamicFunnelConfig, ConsistencyConfig, NamingConfig, SelectedFile
)
from core.consistency_checker import ConsistencyChecker
from core.naming_generator import StandardizedNamingGenerator
from io_layer.dynamic_funnel_selector import DynamicFunnelSelector

# 配置日志只显示关键信息
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("Test")

def run_test_case(name, passed):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} - {name}")

# ==========================================
# 测试 1: 智能洗码 (一致性检查)
# ==========================================
def test_consistency_checker():
    print(f"\n[测试 1] 智能洗码逻辑验证")
    print("-" * 40)
    
    # 构造数据：3个正常文件 (约2GB)，1个异常文件 (500MB)
    files = [
        RawFileNode("id1", "S02E01.mkv", 2100 * 1024**2, "/path/1", "token", "source"), # 2.1GB
        RawFileNode("id2", "S02E02.mkv", 2000 * 1024**2, "/path/2", "token", "source"), # 2.0GB
        RawFileNode("id3", "S02E03.mkv", 1900 * 1024**2, "/path/3", "token", "source"), # 1.9GB
        RawFileNode("id4", "S02E04_Trailer.mp4", 500 * 1024**2, "/path/4", "token", "source"), # 500MB (异常!)
    ]
    
    # 构造对应的元数据
    metas = [
        VideoMeta("庆余年", 2, 1, "4K", 90, True),
        VideoMeta("庆余年", 2, 2, "4K", 90, True),
        VideoMeta("庆余年", 2, 3, "4K", 90, True),
        VideoMeta("庆余年", 2, 4, "1080p", 20, True),
    ]
    
    config = ConsistencyConfig(enable=True, size_deviation=0.5) # 允许50%偏差
    checker = ConsistencyChecker(config)
    
    # 执行检查
    result = checker.check_size_consistency(files, metas)
    
    # 验证
    has_trailer = any(f.file_id == "id4" for f in result)
    count_correct = len(result) == 3
    
    run_test_case("剔除离群文件 (Trailer)", not has_trailer)
    run_test_case("保留正常文件数量 (3/4)", count_correct)

# ==========================================
# 测试 2: 标准化命名
# ==========================================
def test_naming_generator():
    print(f"\n[测试 2] 标准化命名逻辑验证")
    print("-" * 40)
    
    series_info = SeriesInfo(title="庆余年", season=2)
    config = NamingConfig(enable=True)
    generator = StandardizedNamingGenerator(config)
    
    test_cases = [
        # (原文件名, 期望包含的关键词)
        ("Joy.of.Life.S02E01.2160p.HDR.mkv", ["庆余年", "S02E01", "4K", "HDR"]),
        ("庆余年2.第5集.1080p.mp4", ["庆余年", "S02E05", "1080p"]),
        ("qyn_s2_ep08_remux_atmos.mkv", ["庆余年", "S02E08", "Atmos"]),
    ]
    
    for original, keywords in test_cases:
        # 简单模拟元数据，实际会由LLM解析
        import re
        ep_match = re.search(r'(?:E|ep|第)(\d+)', original, re.IGNORECASE)
        ep = int(ep_match.group(1)) if ep_match else 1
        meta = VideoMeta("庆余年", 2, ep, "4K", 90, True)
        node = RawFileNode("id", original, 100, "/path", "token", "src")
        
        # 生成新名字
        new_name = generator.generate_filename(series_info, node, meta)
        
        # 验证所有关键词都在新名字里
        all_present = all(k in new_name for k in keywords)
        print(f"   原名: {original}")
        print(f"   新名: {new_name}")
        run_test_case(f"转换 '{original[:15]}...'", all_present)

# ==========================================
# 测试 3: 动态漏斗筛选 (Mock)
# ==========================================
async def test_funnel_selector():
    print(f"\n[测试 3] 漏斗筛选扩容验证")
    print("-" * 40)
    
    # 模拟数据：前3个源是空的，第4个源才有货
    sources = [
        {"title": "源1(空)", "url": "url1", "score": 90},
        {"title": "源2(空)", "url": "url2", "score": 80},
        {"title": "源3(空)", "url": "url3", "score": 70},
        {"title": "源4(有货)", "url": "url4", "score": 60},
        {"title": "源5(空)", "url": "url5", "score": 50},
    ]
    
    # Mock Crawler，不真的去爬
    class MockSelector(DynamicFunnelSelector):
        async def _process_batch(self, batch):
            found = []
            for src in batch:
                if "有货" in src['title']:
                    print(f"   >>> 在 [{src['title']}] 中发现了文件！")
                    found.append(RawFileNode("id", "file.mkv", 100, "/", "t", "c"))
                else:
                    print(f"   ... [{src['title']}] 是空的")
            return found

    # 配置：每批查2个，目标是找到至少1个文件
    config = DynamicFunnelConfig(batch_size=2, max_sources=10, stop_multiplier=1.0)
    selector = MockSelector(config)
    state = SeriesState({1}, set()) # 缺1集
    
    print("开始筛选 (预期: 应该会执行到第2批)...")
    selected_sources, candidates = await selector.select_with_funnel(sources, state)
    
    run_test_case("自动扩容到下一批", len(selected_sources) >= 4)
    run_test_case("最终找到文件", len(candidates) > 0)

if __name__ == "__main__":
    print("🚀 开始 ResourceOptimizer v4.1 功能验证")
    test_consistency_checker()
    test_naming_generator()
    asyncio.run(test_funnel_selector())
    print("\n🏁 测试结束")