"""
增强组件工厂
负责创建正确配置的增强决策引擎，确保依赖注入的完整性
"""

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from core.contracts import (
    ComponentConfig, ValidationResult, ConsistencyConfig, 
    NamingConfig, RecoveryAction
)
from core.enhanced_decision_engine import EnhancedDecisionMaker
from core.consistency_checker import ConsistencyChecker
from core.naming_generator import StandardizedNamingGenerator

logger = logging.getLogger(__name__)


class ComponentValidationError(Exception):
    """组件验证错误"""
    pass


class DependencyInjectionError(Exception):
    """依赖注入错误"""
    pass


class EnhancedComponentFactory:
    """
    增强组件工厂
    
    核心功能：
    1. 依赖注入容器模式
    2. 组件配置验证
    3. 单例和懒加载模式
    4. 明确的错误信息处理
    """
    
    def __init__(self, config: ComponentConfig):
        """
        初始化增强组件工厂
        
        Args:
            config: 组件配置
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 单例实例缓存
        self._consistency_checker: Optional[ConsistencyChecker] = None
        self._naming_generator: Optional[StandardizedNamingGenerator] = None
        self._enhanced_decision_maker: Optional[EnhancedDecisionMaker] = None
        
        # 验证标志
        self._validated = False
        
        self.logger.info(f"🏭 增强组件工厂初始化:")
        self.logger.info(f"   增强功能启用: {config.enable_enhanced_features}")
        self.logger.info(f"   创建时验证: {config.validate_on_creation}")
        
        # 如果配置要求，立即验证
        if config.validate_on_creation:
            self._validate_configuration()
    
    def create_enhanced_decision_maker(self) -> EnhancedDecisionMaker:
        """
        创建增强决策引擎
        
        确保：
        1. 返回EnhancedDecisionMaker实例（非普通DecisionMaker）
        2. 自动注入ConsistencyChecker
        3. 自动注入NamingGenerator
        4. 验证所有依赖的配置正确性
        
        Returns:
            配置完整的增强决策引擎实例
            
        Raises:
            ComponentValidationError: 组件配置验证失败
            DependencyInjectionError: 依赖注入失败
        """
        self.logger.info("🔧 创建增强决策引擎...")
        
        # 验证配置
        if not self._validated:
            self._validate_configuration()
        
        # 使用单例模式
        if self._enhanced_decision_maker is not None:
            self.logger.debug("返回缓存的增强决策引擎实例")
            return self._enhanced_decision_maker
        
        try:
            # 创建基础决策引擎
            enhanced_decision_maker = EnhancedDecisionMaker()
            
            # 注入依赖组件
            if self.config.enable_enhanced_features:
                consistency_checker = self._get_consistency_checker()
                naming_generator = self._get_naming_generator()
                
                enhanced_decision_maker.set_enhanced_components(
                    consistency_checker, naming_generator
                )
                
                self.logger.info("✅ 增强组件依赖注入完成:")
                self.logger.info(f"   一致性检查器: {consistency_checker is not None}")
                self.logger.info(f"   命名生成器: {naming_generator is not None}")
            else:
                self.logger.warning("⚠️ 增强功能已禁用，跳过依赖注入")
            
            # 缓存实例
            self._enhanced_decision_maker = enhanced_decision_maker
            
            self.logger.info("🎉 增强决策引擎创建成功")
            return enhanced_decision_maker
            
        except Exception as e:
            error_msg = f"创建增强决策引擎失败: {str(e)}"
            self.logger.error(error_msg)
            raise DependencyInjectionError(error_msg) from e
    
    def _get_consistency_checker(self) -> ConsistencyChecker:
        """
        获取一致性检查器实例（懒加载 + 单例）
        
        Returns:
            一致性检查器实例
        """
        if self._consistency_checker is None:
            self.logger.debug("创建一致性检查器实例")
            self._consistency_checker = ConsistencyChecker(self.config.consistency_config)
        
        return self._consistency_checker
    
    def _get_naming_generator(self) -> StandardizedNamingGenerator:
        """
        获取命名生成器实例（懒加载 + 单例）
        
        Returns:
            命名生成器实例
        """
        if self._naming_generator is None:
            self.logger.debug("创建命名生成器实例")
            self._naming_generator = StandardizedNamingGenerator(self.config.naming_config)
        
        return self._naming_generator
    
    def validate_dependencies(self) -> ValidationResult:
        """
        验证依赖组件配置
        
        Returns:
            验证结果
        """
        self.logger.info("🔍 验证组件依赖...")
        
        missing_components = []
        configuration_errors = []
        
        try:
            # 验证一致性检查器配置
            if self.config.enable_enhanced_features:
                consistency_config = self.config.consistency_config
                if not isinstance(consistency_config, ConsistencyConfig):
                    missing_components.append("ConsistencyConfig")
                else:
                    if consistency_config.size_deviation <= 0:
                        configuration_errors.append("consistency_config.size_deviation 必须大于0")
                    if consistency_config.min_samples <= 0:
                        configuration_errors.append("consistency_config.min_samples 必须大于0")
                
                # 验证命名生成器配置
                naming_config = self.config.naming_config
                if not isinstance(naming_config, NamingConfig):
                    missing_components.append("NamingConfig")
                else:
                    if not naming_config.format_template:
                        configuration_errors.append("naming_config.format_template 不能为空")
                    if not naming_config.quality_tags:
                        configuration_errors.append("naming_config.quality_tags 不能为空")
            
            # 尝试创建组件实例进行验证
            if not missing_components and not configuration_errors:
                try:
                    if self.config.enable_enhanced_features:
                        # 测试创建一致性检查器
                        test_consistency = ConsistencyChecker(self.config.consistency_config)
                        
                        # 测试创建命名生成器
                        test_naming = StandardizedNamingGenerator(self.config.naming_config)
                        
                        self.logger.debug("组件实例创建测试通过")
                except Exception as e:
                    configuration_errors.append(f"组件实例创建失败: {str(e)}")
            
            is_valid = len(missing_components) == 0 and len(configuration_errors) == 0
            
            result = ValidationResult(
                is_valid=is_valid,
                missing_components=missing_components,
                configuration_errors=configuration_errors
            )
            
            if is_valid:
                self.logger.info("✅ 组件依赖验证通过")
            else:
                self.logger.error("❌ 组件依赖验证失败:")
                for component in missing_components:
                    self.logger.error(f"   缺失组件: {component}")
                for error in configuration_errors:
                    self.logger.error(f"   配置错误: {error}")
            
            return result
            
        except Exception as e:
            error_msg = f"验证过程异常: {str(e)}"
            self.logger.error(error_msg)
            return ValidationResult(
                is_valid=False,
                missing_components=[],
                configuration_errors=[error_msg]
            )
    
    def _validate_configuration(self) -> None:
        """
        验证配置并设置验证标志
        
        Raises:
            ComponentValidationError: 配置验证失败
        """
        validation_result = self.validate_dependencies()
        
        if not validation_result.is_valid:
            error_details = []
            
            if validation_result.missing_components:
                error_details.append(f"缺失组件: {', '.join(validation_result.missing_components)}")
            
            if validation_result.configuration_errors:
                error_details.append(f"配置错误: {'; '.join(validation_result.configuration_errors)}")
            
            error_msg = f"组件配置验证失败: {'; '.join(error_details)}"
            raise ComponentValidationError(error_msg)
        
        self._validated = True
    
    def reset_cache(self) -> None:
        """
        重置组件缓存
        用于配置更新后重新创建组件
        """
        self.logger.info("🔄 重置组件缓存")
        
        self._consistency_checker = None
        self._naming_generator = None
        self._enhanced_decision_maker = None
        self._validated = False
    
    def get_component_status(self) -> Dict[str, Any]:
        """
        获取组件状态信息
        
        Returns:
            组件状态字典
        """
        return {
            "factory_config": {
                "enable_enhanced_features": self.config.enable_enhanced_features,
                "validate_on_creation": self.config.validate_on_creation,
                "validated": self._validated
            },
            "cached_instances": {
                "consistency_checker": self._consistency_checker is not None,
                "naming_generator": self._naming_generator is not None,
                "enhanced_decision_maker": self._enhanced_decision_maker is not None
            },
            "component_configs": {
                "consistency_enabled": self.config.consistency_config.enable,
                "naming_enabled": self.config.naming_config.enable
            }
        }
    
    def get_statistics(self) -> dict:
        """获取工厂统计信息"""
        return {
            "config": {
                "enable_enhanced_features": self.config.enable_enhanced_features,
                "validate_on_creation": self.config.validate_on_creation
            },
            "status": {
                "validated": self._validated,
                "instances_created": {
                    "consistency_checker": self._consistency_checker is not None,
                    "naming_generator": self._naming_generator is not None,
                    "enhanced_decision_maker": self._enhanced_decision_maker is not None
                }
            }
        }


class ErrorRecoveryManager:
    """
    错误恢复管理器
    处理组件创建和使用过程中的错误
    """
    
    @staticmethod
    def handle_factory_error(error: Exception, component: str) -> RecoveryAction:
        """
        处理工厂错误
        
        Args:
            error: 异常对象
            component: 组件名称
            
        Returns:
            恢复动作
        """
        logger.error(f"组件工厂错误 ({component}): {str(error)}")
        
        if isinstance(error, ComponentValidationError):
            return RecoveryAction.FAIL_FAST
        elif isinstance(error, DependencyInjectionError):
            if component == "consistency_checker":
                return RecoveryAction.DISABLE_CONSISTENCY_CHECK
            elif component == "naming_generator":
                return RecoveryAction.USE_ORIGINAL_NAMES
            else:
                return RecoveryAction.FALLBACK_TO_BASIC_DECISION
        else:
            return RecoveryAction.FALLBACK_TO_STATIC
    
    @staticmethod
    def get_fallback_message(action: RecoveryAction) -> str:
        """
        获取降级消息
        
        Args:
            action: 恢复动作
            
        Returns:
            降级消息
        """
        messages = {
            RecoveryAction.FAIL_FAST: "配置错误，系统无法启动",
            RecoveryAction.DISABLE_CONSISTENCY_CHECK: "一致性检查器不可用，已禁用一致性检查",
            RecoveryAction.USE_ORIGINAL_NAMES: "命名生成器不可用，使用原始文件名",
            RecoveryAction.FALLBACK_TO_BASIC_DECISION: "增强决策引擎不可用，降级到基础决策",
            RecoveryAction.FALLBACK_TO_STATIC: "动态组件不可用，降级到静态模式"
        }
        
        return messages.get(action, "未知恢复动作")


def create_enhanced_component_factory() -> EnhancedComponentFactory:
    """
    创建增强组件工厂实例的工厂函数
    
    Returns:
        配置好的增强组件工厂实例
        
    Raises:
        ComponentValidationError: 配置验证失败
    """
    from config.config_loader import create_component_config
    
    try:
        component_config = create_component_config()
        return EnhancedComponentFactory(component_config)
    except Exception as e:
        logger.error(f"创建增强组件工厂失败: {str(e)}")
        raise ComponentValidationError(f"工厂创建失败: {str(e)}") from e