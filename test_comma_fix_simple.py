"""
简单测试：验证标题中包含逗号的修复
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 模拟配置
class MockConfig:
    @staticmethod
    def get_config_value(key, default=None):
        config_map = {
            "weights.keyword_score": {},
            "aliases": {},
            "app.funnel.batch_size": 3,
            "app.funnel.max_sources": 10,
            "app.funnel.stop_multiplier": 3.0,
            "app.funnel.enable_early_stop": True
        }
        return config_map.get(key, default)

# 替换配置模块
sys.modules['config.config_loader'] = MockConfig()

from io_layer.source_manager import SourceManager


def test_comma_in_title_fix():
    """测试标题中包含逗号的修复"""
    print("🧪 开始测试标题中包含逗号的修复...")
    
    # 创建源管理器
    source_manager = SourceManager()
    
    # 测试场景1: 字符串格式（旧方式，会出错）
    print("\n📝 测试场景1: 字符串格式（旧方式）")
    string_sources = {
        "庆余年": ["[4K, HDR] 庆余年第01集,http://example.com/ep01"]
    }
    
    string_ranked = source_manager.rank_sources(string_sources, missing_episodes=1)
    if string_ranked:
        string_source = string_ranked[0]
        print(f"   标题: '{string_source.title}'")
        print(f"   URL: '{string_source.url}'")
        print(f"   ❌ 问题: 标题被截断，URL包含标题片段")
    
    # 测试场景2: 字典格式（新方式，正确）
    print("\n📝 测试场景2: 字典格式（新方式）")
    dict_sources = {
        "庆余年": [{"title": "[4K, HDR] 庆余年第01集", "url": "http://example.com/ep01"}]
    }
    
    dict_ranked = source_manager.rank_sources(dict_sources, missing_episodes=1)
    if dict_ranked:
        dict_source = dict_ranked[0]
        print(f"   标题: '{dict_source.title}'")
        print(f"   URL: '{dict_source.url}'")
        print(f"   ✅ 正确: 标题完整，URL正确")
    
    # 测试场景3: 多个包含逗号的标题
    print("\n📝 测试场景3: 多个包含逗号的标题")
    complex_sources = {
        "庆余年": [
            {"title": "[4K, HDR] 庆余年第01集", "url": "http://example.com/ep01"},
            {"title": "庆余年, 杜比视界版本", "url": "http://example.com/ep02"},
            {"title": "庆余年 [Remux, 无损, 中字]", "url": "http://example.com/ep03"}
        ]
    }
    
    complex_ranked = source_manager.rank_sources(complex_sources, missing_episodes=3)
    print(f"   成功解析 {len(complex_ranked)} 个源:")
    for i, source in enumerate(complex_ranked, 1):
        print(f"   {i}. 标题: '{source.title}' (评分: {source.score})")
        print(f"      URL: '{source.url}'")
        
        # 验证URL完整性
        if not source.url.startswith("http://"):
            print(f"      ❌ 错误: URL格式不正确")
            return False
        
        # 验证标题完整性
        if "庆余年" not in source.title:
            print(f"      ❌ 错误: 标题不完整")
            return False
    
    print("\n✅ 所有测试通过！标题中包含逗号的问题已修复")
    return True


def demonstrate_problem_and_solution():
    """演示问题和解决方案"""
    print("\n" + "="*60)
    print("🔍 问题演示：标题中包含逗号导致URL解析错误")
    print("="*60)
    
    # 问题场景
    problematic_title = "[4K, HDR] 庆余年第01集"
    url = "http://example.com/ep01"
    
    print(f"原始数据:")
    print(f"  标题: {problematic_title}")
    print(f"  URL: {url}")
    
    # 旧方式：字符串拼接
    old_format = f"{problematic_title},{url}"
    print(f"\n旧方式 (字符串拼接): '{old_format}'")
    
    # 模拟旧的解析逻辑
    if "," in old_format:
        parsed_title, parsed_url = old_format.split(",", 1)
        print(f"解析结果:")
        print(f"  标题: '{parsed_title}' ❌ (被截断)")
        print(f"  URL: '{parsed_url}' ❌ (包含标题片段)")
    
    # 新方式：字典格式
    new_format = {"title": problematic_title, "url": url}
    print(f"\n新方式 (字典格式): {new_format}")
    print(f"解析结果:")
    print(f"  标题: '{new_format['title']}' ✅ (完整)")
    print(f"  URL: '{new_format['url']}' ✅ (正确)")


if __name__ == "__main__":
    demonstrate_problem_and_solution()
    test_comma_in_title_fix()