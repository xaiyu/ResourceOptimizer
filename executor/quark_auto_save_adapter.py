"""
quark-auto-save 适配器
负责将我们的决策结果转换为 quark-auto-save 兼容的任务配置
"""

import json
import re
import os
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import asdict

from core.contracts import SelectedFile, RawFileNode
from config.config_loader import get_config_value

import logging
logger = logging.getLogger(__name__)


class QuarkAutoSaveAdapter:
    """quark-auto-save 适配器"""
    
    def __init__(self, 
                 output_dir: str = "instance/output/quark_tasks",
                 quark_project_path: str = "1111/quark-auto-save-main"):
        """
        初始化适配器
        
        Args:
            output_dir: 任务文件输出目录
            quark_project_path: quark-auto-save项目路径
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.quark_project_path = Path(quark_project_path)
        self.config_path = self.quark_project_path / "quark_config.json"
        
        # 加载quark-auto-save的配置模板
        self._load_quark_config_template()
        
        logger.info(f"QuarkAutoSave适配器初始化完成")
        logger.info(f"输出目录: {self.output_dir}")
        logger.info(f"quark-auto-save路径: {self.quark_project_path}")
    
    def _load_quark_config_template(self):
        """加载quark-auto-save的配置模板"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.quark_config_template = json.load(f)
                logger.info("已加载quark-auto-save配置模板")
            else:
                # 使用默认模板
                self.quark_config_template = {
                    "cookie": [""],
                    "push_config": {"QUARK_SIGN_NOTIFY": True},
                    "plugins": {"emby": {"url": "", "token": ""}},
                    "magic_regex": {},
                    "tasklist": []
                }
                logger.warning("未找到quark-auto-save配置文件，使用默认模板")
        except Exception as e:
            logger.error(f"加载quark-auto-save配置失败: {e}")
            self.quark_config_template = {"tasklist": []}
    
    def generate_task(self, decision: DecisionResult) -> Dict[str, Any]:
        """
        生成单个任务配置
        
        Args:
            decision: 决策结果
            
        Returns:
            quark-auto-save兼容的任务配置
        """
        task = {
            "taskname": self._generate_task_name(decision),
            "shareurl": decision.source_url,
            "savepath": self._generate_save_path(decision),
        }
        
        # 根据决策类型设置匹配模式
        if decision.decision_type == "single_file":
            # 单文件模式：精确匹配文件名
            task["pattern"] = self._escape_regex(decision.selected_file.name)
            task["replace"] = ""
            
        elif decision.decision_type == "folder":
            # 文件夹模式：匹配整个文件夹
            task["update_subdir"] = decision.selected_folder.name
            task["pattern"] = ""
            task["replace"] = ""
            
        elif decision.decision_type == "episodes":
            # 剧集模式：使用智能匹配
            task["pattern"] = self._generate_episode_pattern(decision)
            task["replace"] = self._generate_rename_rule(decision)
            
        # 设置任务期限（默认1年后）
        end_date = datetime.now() + timedelta(days=365)
        task["enddate"] = end_date.strftime("%Y-%m-%d")
        
        # 添加我们的元数据（用于追溯）
        task["_metadata"] = {
            "generated_by": "smart-chase-system",
            "generated_at": datetime.now().isoformat(),
            "decision_score": getattr(decision, 'score', 0),
            "media_type": getattr(decision, 'media_type', 'unknown'),
            "quality_info": self._extract_quality_info(decision)
        }
        
        return task
    
    def generate_batch_config(self, decisions: List[DecisionResult]) -> str:
        """
        生成批量任务配置文件
        
        Args:
            decisions: 决策结果列表
            
        Returns:
            生成的配置文件路径
        """
        # 生成任务列表
        tasks = []
        for decision in decisions:
            try:
                task = self.generate_task(decision)
                tasks.append(task)
                logger.info(f"✅ 生成任务: {task['taskname']}")
            except Exception as e:
                logger.error(f"❌ 生成任务失败: {decision.series_title}, 错误: {e}")
        
        # 创建完整配置
        config = self.quark_config_template.copy()
        config["tasklist"] = tasks
        
        # 添加生成信息
        config["_generation_info"] = {
            "generated_by": "smart-chase-system",
            "generated_at": datetime.now().isoformat(),
            "total_tasks": len(tasks),
            "source_decisions": len(decisions)
        }
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"quark_config_{timestamp}.json"
        filepath = self.output_dir / filename
        
        # 写入文件
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        logger.info(f"🎯 批量任务配置已生成: {filepath}")
        logger.info(f"📊 包含 {len(tasks)} 个转存任务")
        
        return str(filepath)
    
    def _generate_task_name(self, decision: DecisionResult) -> str:
        """生成任务名称"""
        name = decision.series_title or "未命名任务"
        
        # 添加质量标识
        if hasattr(decision, 'selected_file') and decision.selected_file:
            filename = decision.selected_file.name.lower()
            quality_tags = []
            
            if '4k' in filename or '2160p' in filename:
                quality_tags.append('4K')
            elif '1080p' in filename:
                quality_tags.append('1080p')
            
            if 'hdr' in filename or '杜比视界' in filename:
                quality_tags.append('HDR')
            
            if 'atmos' in filename or '全景声' in filename:
                quality_tags.append('Atmos')
            
            if quality_tags:
                name += f" [{'/'.join(quality_tags)}]"
        
        return name
    
    def _generate_save_path(self, decision: DecisionResult) -> str:
        """生成保存路径"""
        base_path = get_config_value("output.base_dir", "/智能追剧")
        
        # 根据媒体类型分类
        media_type = getattr(decision, 'media_type', 'unknown')
        if media_type == "movie":
            category = "电影"
        elif media_type == "tv":
            category = "电视剧"
        elif media_type == "variety":
            category = "综艺"
        elif media_type == "anime":
            category = "动漫"
        else:
            category = "其他"
        
        # 构建完整路径
        title = decision.series_title or "未命名"
        return f"{base_path}/{category}/{title}"
    
    def _escape_regex(self, filename: str) -> str:
        """转义正则表达式特殊字符"""
        # 需要转义的特殊字符
        special_chars = r'\.[]{}()*+?^$|'
        escaped = filename
        
        for char in special_chars:
            escaped = escaped.replace(char, f'\\{char}')
        
        # 精确匹配整个文件名
        return f"^{escaped}$"
    
    def _generate_episode_pattern(self, decision: DecisionResult) -> str:
        """生成剧集匹配正则"""
        # 使用quark-auto-save的魔法正则
        # 匹配常见的剧集格式：S01E01, 第01集等
        return r".*?([Ss]\d{1,2})?(?:[第EePpXx\.\-\_\( ]{1,2}|^)(\d{1,3})(?!\d).*?\.(mp4|mkv)"
    
    def _generate_rename_rule(self, decision: DecisionResult) -> str:
        """生成重命名规则"""
        # 使用quark-auto-save的魔法变量
        # 格式：任务名.S01E01.扩展名
        return "{TASKNAME}.{SXX}E{E}.{EXT}"
    
    def _extract_quality_info(self, decision: DecisionResult) -> Dict[str, Any]:
        """提取质量信息"""
        quality_info = {}
        
        if hasattr(decision, 'selected_file') and decision.selected_file:
            filename = decision.selected_file.name.lower()
            
            # 分辨率
            if '4k' in filename or '2160p' in filename:
                quality_info['resolution'] = '4K'
            elif '1080p' in filename:
                quality_info['resolution'] = '1080p'
            elif '720p' in filename:
                quality_info['resolution'] = '720p'
            
            # 编码
            if 'hevc' in filename or 'h265' in filename:
                quality_info['codec'] = 'HEVC'
            elif 'h264' in filename:
                quality_info['codec'] = 'H264'
            
            # 音频
            if 'atmos' in filename:
                quality_info['audio'] = 'Atmos'
            elif 'truehd' in filename:
                quality_info['audio'] = 'TrueHD'
            elif 'dts' in filename:
                quality_info['audio'] = 'DTS'
            
            # 来源
            if 'remux' in filename:
                quality_info['source'] = 'Remux'
            elif 'bluray' in filename:
                quality_info['source'] = 'BluRay'
            elif 'web-dl' in filename:
                quality_info['source'] = 'WEB-DL'
        
        return quality_info
    
    def execute_quark_auto_save(self, config_file: str) -> Dict[str, Any]:
        """
        执行quark-auto-save任务
        
        Args:
            config_file: 配置文件路径
            
        Returns:
            执行结果
        """
        try:
            import subprocess
            
            # 构建命令
            cmd = [
                "python",
                "quark_auto_save.py"
            ]
            
            # 设置环境变量
            env = os.environ.copy()
            env["CONFIG_PATH"] = config_file
            
            # 执行命令
            result = subprocess.run(
                cmd,
                cwd=str(self.quark_project_path),
                env=env,
                capture_output=True,
                text=True,
                timeout=1800  # 30分钟超时
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "执行超时（30分钟）",
                "stdout": "",
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "stdout": "",
                "stderr": ""
            }
    
    def get_execution_command(self, config_file: str) -> str:
        """
        获取执行命令
        
        Args:
            config_file: 配置文件路径
            
        Returns:
            执行命令字符串
        """
        abs_config_path = os.path.abspath(config_file)
        abs_quark_path = os.path.abspath(self.quark_project_path)
        
        return f"""
# 执行转存任务的命令：
cd "{abs_quark_path}"
set CONFIG_PATH={abs_config_path}
python quark_auto_save.py

# 或者使用Docker（如果已配置）：
docker run -v "{abs_config_path}:/app/config/quark_config.json" cp0204/quark-auto-save:latest
"""
    
    def create_enhanced_save_config(self, selected_files: List, series_title: str) -> str:
        """
        创建增强的转存配置 (v4.1)
        支持标准化文件名和重命名元数据
        
        Args:
            selected_files: 选中的文件列表 (SelectedFile对象)
            series_title: 剧集标题
            
        Returns:
            配置文件路径
        """
        try:
            # 构建增强的任务配置
            tasks = []
            
            for selected_file in selected_files:
                file_node = selected_file.file_node
                video_meta = selected_file.video_meta
                
                # 使用标准化文件名 (v4.1新功能)
                target_name = getattr(selected_file, 'target_filename', None) or file_node.filename
                
                task = {
                    "taskname": self._generate_enhanced_task_name(series_title, video_meta),
                    "shareurl": file_node.share_token,
                    "savepath": self._generate_enhanced_save_path(series_title, video_meta.season),
                    "pattern": self._escape_regex(file_node.filename),
                    "replace": target_name,  # v4.1: 使用标准化文件名进行重命名
                    "enddate": (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d"),
                    
                    # v4.1: 增强元数据
                    "_enhanced_metadata": {
                        "version": "v4.1",
                        "original_filename": file_node.filename,
                        "target_filename": target_name,
                        "file_size": file_node.size,
                        "episode": video_meta.episode,
                        "quality_score": video_meta.quality_score,
                        "selection_reason": selected_file.selection_reason,
                        "consistency_score": getattr(selected_file, 'consistency_score', None),
                        "rename_metadata": getattr(selected_file, 'rename_metadata', None),
                        "generated_by": "enhanced_system_v4.1",
                        "generated_at": datetime.now().isoformat()
                    }
                }
                tasks.append(task)
            
            # 生成增强配置文件
            config = {
                "version": "v4.1_enhanced",
                "generated_at": datetime.now().isoformat(),
                "series_info": {
                    "title": series_title,
                    "total_tasks": len(tasks),
                    "total_files": len(selected_files)
                },
                "enhanced_features": {
                    "standardized_naming": True,
                    "consistency_checked": True,
                    "metadata_enriched": True
                },
                "tasklist": tasks
            }
            
            # 保存配置文件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            config_filename = f"enhanced_quark_config_{series_title}_{timestamp}.json"
            # 清理文件名中的非法字符
            config_filename = re.sub(r'[<>:"/\\|?*]', '_', config_filename)
            config_path = self.output_dir / config_filename
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ 增强转存配置已生成: {config_path}")
            logger.info(f"   任务数: {len(tasks)}")
            logger.info(f"   文件数: {len(selected_files)}")
            
            return str(config_path)
            
        except Exception as e:
            logger.error(f"❌ 生成增强转存配置失败: {e}")
            raise
    
    def _generate_enhanced_task_name(self, series_title: str, video_meta) -> str:
        """生成增强的任务名称"""
        name = series_title
        
        # 添加季集信息
        if hasattr(video_meta, 'season') and video_meta.season:
            name += f" S{video_meta.season:02d}"
        
        if hasattr(video_meta, 'episode') and video_meta.episode:
            name += f"E{video_meta.episode:02d}"
        
        # 添加质量标识
        if hasattr(video_meta, 'resolution') and video_meta.resolution:
            name += f" [{video_meta.resolution}]"
        
        return name
    
    def _generate_enhanced_save_path(self, series_title: str, season: int = 1) -> str:
        """生成增强的保存路径"""
        base_path = get_config_value("output.base_dir", "/智能追剧")
        
        # 构建层级路径：基础路径/电视剧/剧名/季度
        clean_title = re.sub(r'[<>:"/\\|?*]', '_', series_title)
        season_folder = f"Season {season:02d}" if season > 1 else ""
        
        if season_folder:
            return f"{base_path}/电视剧/{clean_title}/{season_folder}"
        else:
            return f"{base_path}/电视剧/{clean_title}"