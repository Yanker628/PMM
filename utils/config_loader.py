import os
import yaml
from dotenv import load_dotenv
from typing import Any, Dict

class ConfigLoaderError(Exception):
    """自定义异常：配置加载相关错误"""
    pass

class Config:
    """配置对象，封装所有参数，支持属性访问"""
    def __init__(self, yaml_config: Dict[str, Any], env_config: Dict[str, str]):
        self.yaml = yaml_config
        self.env = env_config

    def get(self, key: str, default=None):
        """优先查找yaml配置，其次查找env，最后返回默认值"""
        return self.yaml.get(key, self.env.get(key, default))

    def __getitem__(self, key):
        return self.get(key)

    def __repr__(self):
        return f"<Config yaml={self.yaml} env={self.env}>"

def load_env(env_path: str = ".env") -> Dict[str, str]:
    """加载.env文件，返回环境变量字典，None值替换为''"""
    if not os.path.exists(env_path):
        raise ConfigLoaderError(f".env 文件未找到: {env_path}")
    load_dotenv(env_path)
    keys = ["BINANCE_API_KEY", "BINANCE_SECRET_KEY", "EXCHANGE_ENV", "LISTEN_KEY_REFRESH_INTERVAL"]
    return {k: os.getenv(k) or '' for k in keys}

def load_yaml(yaml_path: str = "config.yaml") -> Dict[str, Any]:
    """加载yaml配置文件，返回字典"""
    if not os.path.exists(yaml_path):
        raise ConfigLoaderError(f"config.yaml 文件未找到: {yaml_path}")
    with open(yaml_path, "r", encoding="utf-8") as f:
        try:
            return yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigLoaderError(f"YAML 解析错误: {e}")

def get_config(env_path: str = ".env", yaml_path: str = "config.yaml") -> Config:
    """统一加载配置，返回Config对象"""
    env_config = load_env(env_path)
    yaml_config = load_yaml(yaml_path)
    return Config(yaml_config, env_config)
