#!/usr/bin/env python3
"""配置加载器"""
import os
import yaml
from typing import Any, Dict

class ConfigLoader:
    """统一配置管理"""
    
    def __init__(self, config_dir: str = None):
        self.config_dir = config_dir or os.path.join(
            os.path.dirname(__file__), '..', 'config'
        )
        self._config = None
        self._env = os.environ.get('STOCK_SKILLS_ENV', 'development')
    
    def load(self) -> Dict[str, Any]:
        """加载配置"""
        if self._config is not None:
            return self._config
        
        # 加载基础配置
        base_config = self._load_yaml('base.yaml')
        
        # 加载环境配置
        env_config = self._load_yaml(f'{self._env}.yaml')
        
        # 合并配置
        self._config = self._deep_merge(base_config, env_config)
        
        # 环境变量覆盖
        self._apply_env_overrides()
        
        return self._config
    
    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        """加载 YAML 文件"""
        filepath = os.path.join(self.config_dir, filename)
        if not os.path.exists(filepath):
            return {}
        
        with open(filepath, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    
    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """深度合并配置"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def _apply_env_overrides(self):
        """应用环境变量覆盖"""
        env_mappings = {
            'FEISHU_USER_OPEN_ID': 'feishu.user_open_id',
            'STOCK_SKILLS_LOG_LEVEL': 'logging.level',
        }
        
        for env_key, config_path in env_mappings.items():
            if os.environ.get(env_key):
                self._set_nested(config_path, os.environ[env_key])
    
    def _set_nested(self, path: str, value: Any):
        """设置嵌套配置值"""
        keys = path.split('.')
        config = self._config
        for key in keys[:-1]:
            config = config.setdefault(key, {})
        config[keys[-1]] = value
    
    def get(self, path: str, default: Any = None) -> Any:
        """获取配置值"""
        if self._config is None:
            self.load()
        
        keys = path.split('.')
        value = self._config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default
        
        return value if value is not None else default


# 全局配置实例
_config = None

def get_config() -> ConfigLoader:
    """获取全局配置实例"""
    global _config
    if _config is None:
        _config = ConfigLoader()
        _config.load()
    return _config
