"""
配置管理模块 (Configuration Manager)

本模块提供统一的配置管理功能，支持JSON和YAML两种配置文件格式。
实现配置热加载、环境变量替换、多模型配置管理等核心功能。

主要组件:
- ConfigManager: 配置管理器核心类

功能特点:
- 支持JSON和YAML格式的配置文件
- 支持多配置文件分层加载（llm_config.yaml, agent_config.yaml, infrastructure_config.yaml）
- 环境变量替换，如 ${API_KEY}
- 多模型配置管理
- 旅游知识数据内置
- 嵌套配置项访问

配置文件分层:
    - config/llm_config.yaml          : LLM 模型配置（必选）
    - config/agent_config.yaml       : Agent 行为配置（可选）
    - config/infrastructure_config.yaml : 基础设施配置（可选）

使用示例:
    from config.config_manager import ConfigManager

    # 创建配置管理器（自动加载所有配置文件）
    config = ConfigManager("config/llm_config.yaml")

    # 获取模型配置
    model_config = config.get_model_config("gpt-4o-mini")

    # 获取 Agent 配置
    agent_config = config.get_agent_config()

    # 获取基础设施配置
    infra_config = config.get_infrastructure_config()

    # 获取配置值
    api_key = config.get_config("models.gpt-4o-mini.api_key")

    # 获取城市信息
    city_info = config.get_city_info("北京")

    # 按标签搜索城市
    cities = config.search_cities_by_tag("美食")
"""

import json
import os
import re
import yaml
from typing import Dict, Any, List, Optional


class ConfigManager:
    """
    配置管理器核心类

    负责加载、解析和管理应用配置，支持多模型配置和旅游知识数据。

    配置管理流程:
    1. 初始化时检查配置文件是否存在
    2. 加载配置文件（JSON或YAML格式）
    3. 替换环境变量占位符
    4. 初始化旅游知识数据
    5. 提供配置访问接口

    属性:
        config_path: str 配置文件路径
        config: Dict[str, Any] 原始配置数据
        models_config: Dict[str, Dict] 模型配置字典
        default_model_id: str 默认模型ID
        travel_knowledge: Dict[str, Any] 内置旅游知识数据

    内置旅游知识:
        - 支持城市: 北京、上海、杭州、成都、西安、厦门、呼和浩特、呼伦贝尔、包头
        - 每个城市包含: 地区、标签、最佳游玩季节、每日预算、推荐天数、景点列表
        - 兴趣标签关联城市列表
    """

    def __init__(self, config_path: str = "config/llm_config.yaml", load_additional: bool = True):
        """
        初始化配置管理器

        Args:
            config_path: str 配置文件路径，支持.yaml和.json格式
            load_additional: bool 是否加载额外的配置文件（agent_config.yaml, infrastructure_config.yaml）
        """
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.models_config: Dict[str, Dict[str, Any]] = {}
        self.default_model_id: str = "gpt-4o-mini"
        self.travel_knowledge: Dict[str, Any] = {}

        self._check_config_files()
        self._load_config()

        # 加载额外配置文件
        if load_additional:
            self._load_additional_configs()

        self._init_travel_knowledge()

    def _check_config_files(self) -> None:
        """
        检查配置文件是否存在

        优先查找YAML文件，如果YAML不存在且指定的是YAML文件，
        则尝试查找同名的JSON文件。
        Raises:
            FileNotFoundError: 配置文件不存在时抛出
        """
        # 优先查找 YAML 文件
        yaml_path = self.config_path
        json_path = self.config_path.replace('.yaml', '.json').replace('.yml', '.json')

        # 如果指定的是 yaml 文件但不存在，尝试 json
        if self.config_path.endswith(('.yaml', '.yml')) and not os.path.exists(yaml_path):
            if os.path.exists(json_path):
                self.config_path = json_path
                return

        if not os.path.exists(self.config_path):
            error_msg = (
                f"Configuration file missing: {self.config_path}\n\n"
                f"Please create configuration file before starting the application:\n"
                f"  1. Copy config/llm_config.yaml.example to config/llm_config.yaml\n"
                f"  2. Update the API keys in the configuration\n\n"
                f"Refer to README.md for detailed instructions."
            )
            raise FileNotFoundError(error_msg)

    def _load_config(self) -> None:
        """
        加载配置文件，支持 YAML 和 JSON 格式

        读取配置文件内容，替换环境变量占位符，然后解析为Python字典。
        格式由文件扩展名自动判断。
        """
        with open(self.config_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 替换环境变量占位符 ${VAR_NAME}
        content = self._replace_env_vars(content)

        if self.config_path.endswith(('.yaml', '.yml')):
            self.config = yaml.safe_load(content)
        else:
            self.config = json.loads(content)

        # 加载模型配置
        self.models_config = self.config.get('models', {})
        self.default_model_id = self.config.get('default_model', 'gpt-4o-mini')

        # 检查是否有模型配置
        if not self.models_config:
            raise ValueError(
                f"No models configured in {self.config_path}\n"
                f"Please add at least one model configuration."
            )

    def _replace_env_vars(self, content: str) -> str:
        """
        替换环境变量占位符 ${VAR_NAME}

        扫描配置文件中的 ${VAR_NAME} 格式的占位符，
        替换为对应的环境变量值。如果环境变量未设置，
        则保留原始占位符。

        Args:
            content: str 配置文件原始内容

        Returns:
            str: 替换环境变量后的内容
        """
        pattern = r'\$\{([^}]+)\}'

        def replace(match):
            var_name = match.group(1)
            env_value = os.environ.get(var_name, '')
            return env_value if env_value else match.group(0)

        return re.sub(pattern, replace, content)

    def _load_additional_configs(self) -> None:
        """
        加载额外的配置文件（agent_config.yaml, infrastructure_config.yaml）

        根据相对于主配置文件的路径，尝试加载额外的配置文件。
        如果文件不存在则跳过，不会抛出错误。
        额外的配置会合并到主配置中，相同键值会被覆盖。
        """
        # 获取配置目录
        config_dir = os.path.dirname(os.path.abspath(self.config_path))

        # 需要加载的额外配置文件
        additional_configs = [
            ("agent_config.yaml", "agent"),
            ("infrastructure_config.yaml", "infrastructure"),
        ]

        for filename, config_key in additional_configs:
            config_file = os.path.join(config_dir, filename)
            if os.path.exists(config_file):
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    content = self._replace_env_vars(content)

                    if config_file.endswith(('.yaml', '.yml')):
                        additional_data = yaml.safe_load(content)
                    else:
                        additional_data = json.loads(content)

                    # 合并配置
                    if config_key not in self.config:
                        self.config[config_key] = {}
                    self.config[config_key].update(additional_data)

                except Exception as e:
                    # 加载失败时记录警告但继续运行
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Failed to load {filename}: {e}")

    def _init_travel_knowledge(self) -> None:
        """
        初始化旅游知识数据

        加载内置的城市信息、景点、兴趣标签等旅游知识数据。
        这些数据用于辅助旅游推荐和路线规划。

        数据结构:
            travel_knowledge
            ├── cities: {城市名: 城市信息}
            │   ├── region: 地区
            │   ├── tags: 标签列表
            │   ├── best_season: 最佳游玩季节
            │   ├── avg_budget_per_day: 日均预算
            │   ├── recommended_days: 推荐天数
            │   └── attractions: 景点列表
            └── interest_tags: {兴趣标签: 城市列表}
        """
        self.travel_knowledge = {
            "cities": {
                "北京": {
                    "region": "华北",
                    "tags": ["历史文化", "首都", "古建筑"],
                    "best_season": ["春季", "秋季"],
                    "avg_budget_per_day": 500,
                    "recommended_days": 4,
                    "attractions": [
                        {"name": "故宫", "type": "历史遗迹", "duration": 4, "ticket": 60},
                        {"name": "长城", "type": "历史遗迹", "duration": 6, "ticket": 40},
                        {"name": "天坛", "type": "历史遗迹", "duration": 3, "ticket": 15},
                        {"name": "颐和园", "type": "园林", "duration": 4, "ticket": 30}
                    ]
                },
                "上海": {
                    "region": "华东",
                    "tags": ["现代都市", "购物", "美食"],
                    "best_season": ["春季", "秋季"],
                    "avg_budget_per_day": 600,
                    "recommended_days": 3,
                    "attractions": [
                        {"name": "外滩", "type": "城市景观", "duration": 3, "ticket": 0},
                        {"name": "东方明珠", "type": "地标建筑", "duration": 2, "ticket": 180},
                        {"name": "迪士尼乐园", "type": "主题乐园", "duration": 8, "ticket": 399},
                        {"name": "豫园", "type": "园林", "duration": 2, "ticket": 40}
                    ]
                },
                "杭州": {
                    "region": "华东",
                    "tags": ["自然风光", "人文历史", "休闲"],
                    "best_season": ["春季", "秋季"],
                    "avg_budget_per_day": 400,
                    "recommended_days": 3,
                    "attractions": [
                        {"name": "西湖", "type": "自然风光", "duration": 4, "ticket": 0},
                        {"name": "灵隐寺", "type": "宗教文化", "duration": 3, "ticket": 45},
                        {"name": "千岛湖", "type": "自然风光", "duration": 6, "ticket": 150},
                        {"name": "宋城", "type": "主题乐园", "duration": 4, "ticket": 310}
                    ]
                },
                "成都": {
                    "region": "西南",
                    "tags": ["美食", "休闲", "熊猫"],
                    "best_season": ["春季", "秋季"],
                    "avg_budget_per_day": 350,
                    "recommended_days": 4,
                    "attractions": [
                        {"name": "大熊猫繁育研究基地", "type": "动物园", "duration": 4, "ticket": 55},
                        {"name": "宽窄巷子", "type": "历史街区", "duration": 3, "ticket": 0},
                        {"name": "武侯祠", "type": "历史遗迹", "duration": 2, "ticket": 50},
                        {"name": "都江堰", "type": "历史遗迹", "duration": 5, "ticket": 80}
                    ]
                },
                "西安": {
                    "region": "西北",
                    "tags": ["历史文化", "古都", "美食"],
                    "best_season": ["春季", "秋季"],
                    "avg_budget_per_day": 400,
                    "recommended_days": 4,
                    "attractions": [
                        {"name": "兵马俑", "type": "历史遗迹", "duration": 4, "ticket": 120},
                        {"name": "大雁塔", "type": "历史遗迹", "duration": 2, "ticket": 50},
                        {"name": "古城墙", "type": "历史遗迹", "duration": 3, "ticket": 54},
                        {"name": "华清宫", "type": "历史遗迹", "duration": 3, "ticket": 120}
                    ]
                },
                "厦门": {
                    "region": "华南",
                    "tags": ["海滨", "休闲", "文艺"],
                    "best_season": ["春季", "秋季", "冬季"],
                    "avg_budget_per_day": 450,
                    "recommended_days": 3,
                    "attractions": [
                        {"name": "鼓浪屿", "type": "海岛", "duration": 6, "ticket": 0},
                        {"name": "南普陀寺", "type": "宗教文化", "duration": 2, "ticket": 0},
                        {"name": "曾厝垵", "type": "历史街区", "duration": 3, "ticket": 0},
                        {"name": "环岛路", "type": "城市景观", "duration": 3, "ticket": 0}
                    ]
                },
                "呼和浩特": {
                    "region": "内蒙古",
                    "tags": ["草原", "历史文化", "美食", "民族风情"],
                    "best_season": ["夏季", "秋季"],
                    "avg_budget_per_day": 350,
                    "recommended_days": 3,
                    "attractions": [
                        {"name": "大召寺", "type": "宗教文化", "duration": 2, "ticket": 35},
                        {"name": "内蒙古博物馆", "type": "博物馆", "duration": 2, "ticket": 0},
                        {"name": "昭君墓", "type": "历史遗迹", "duration": 2, "ticket": 65},
                        {"name": "敕勒川草原", "type": "自然风光", "duration": 4, "ticket": 0}
                    ]
                },
                "呼伦贝尔": {
                    "region": "内蒙古",
                    "tags": ["草原", "自然风光", "民族风情", "美食"],
                    "best_season": ["夏季", "秋季"],
                    "avg_budget_per_day": 450,
                    "recommended_days": 4,
                    "attractions": [
                        {"name": "呼伦贝尔大草原", "type": "自然风光", "duration": 6, "ticket": 0},
                        {"name": "额尔古纳湿地", "type": "自然风光", "duration": 4, "ticket": 65},
                        {"name": "满洲里国门", "type": "历史遗迹", "duration": 2, "ticket": 80},
                        {"name": "套娃广场", "type": "主题广场", "duration": 2, "ticket": 0}
                    ]
                },
                "包头": {
                    "region": "内蒙古",
                    "tags": ["草原", "工业", "美食"],
                    "best_season": ["夏季", "秋季"],
                    "avg_budget_per_day": 300,
                    "recommended_days": 2,
                    "attractions": [
                        {"name": "赛罕塔拉公园", "type": "自然风光", "duration": 3, "ticket": 0},
                        {"name": "北方兵器城", "type": "工业旅游", "duration": 2, "ticket": 50},
                        {"name": "五当召", "type": "宗教文化", "duration": 3, "ticket": 60}
                    ]
                }
            },

            "interest_tags": {
                "历史文化": ["北京", "西安", "洛阳", "南京"],
                "自然风光": ["杭州", "桂林", "张家界", "九寨沟", "呼伦贝尔"],
                "现代都市": ["上海", "深圳", "广州", "香港"],
                "美食": ["成都", "重庆", "广州", "西安", "呼和浩特", "呼伦贝尔"],
                "海滨度假": ["三亚", "厦门", "青岛", "大连"],
                "休闲养生": ["杭州", "成都", "丽江", "大理"],
                "草原风光": ["呼伦贝尔", "呼和浩特", "包头"],
                "民族风情": ["呼和浩特", "呼伦贝尔", "大理", "丽江"]
            }
        }

    def get_config(self, key: str, default: Any = None) -> Any:
        """
        获取配置值，支持嵌套键如 'web.port'

        Args:
            key: str 配置键，支持点分隔的嵌套访问，如 'models.gpt-4o-mini.api_key'
            default: Any 如果键不存在返回的默认值

        Returns:
            Any: 配置值，不存在时返回默认值
        """
        keys = key.split('.')
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def get_city_info(self, city_name: str) -> Optional[Dict[str, Any]]:
        """
        获取城市信息

        Args:
            city_name: str 城市名称

        Returns:
            Optional[Dict]: 城市信息字典，不存在返回None
        """
        return self.travel_knowledge['cities'].get(city_name)

    def search_cities_by_tag(self, tag: str) -> List[str]:
        """
        根据标签搜索城市

        Args:
            tag: str 兴趣标签，如"美食"、"历史文化"等

        Returns:
            List[str]: 匹配该标签的城市列表
        """
        return self.travel_knowledge['interest_tags'].get(tag, [])

    def get_all_cities(self) -> List[str]:
        """
        获取所有城市列表

        Returns:
            List[str]: 支持的城市名称列表
        """
        return list(self.travel_knowledge['cities'].keys())

    def _is_model_active(self, config: Dict[str, Any]) -> bool:
        """
        检查模型配置是否已激活（拥有有效的API密钥）

        只有拥有有效API密钥的模型才会被返回给前端。
        以下情况视为无效/占位符配置：
        - api_key 为空
        - api_key 包含 "YOUR_" 前缀（占位符）
        - api_key 是环境变量占位符 ${...} 但未设置

        Args:
            config: 模型配置字典

        Returns:
            bool: True 表示模型已激活可用
        """
        api_key = config.get('api_key', '')

        # 空密钥无效
        if not api_key:
            return False

        # 检查是否是环境变量占位符
        if api_key.startswith('${') and api_key.endswith('}'):
            # 占位符格式，检查环境变量是否已设置
            var_name = api_key[2:-1]
            return bool(os.environ.get(var_name))

        # 检查是否是占位符文本
        if 'YOUR_' in api_key.upper():
            return False

        return True

    def get_available_models(self) -> List[Dict[str, Any]]:
        """
        获取已激活的模型列表

        仅返回已配置有效API密钥的模型，过滤掉占位符配置。
        用于前端模型选择器，确保只显示可用的模型选项。

        Returns:
            List[Dict]: 模型信息列表，每个包含model_id、name、provider、model
        """
        models = []
        for model_id, config in self.models_config.items():
            # 只返回已激活的模型（拥有有效API密钥）
            if not self._is_model_active(config):
                continue

            provider_type = config.get('provider', 'openai')
            model_name = config.get('model', model_id)
            display_name = config.get('name', model_id)
            models.append({
                'model_id': model_id,
                'name': display_name,
                'provider': provider_type,
                'model': model_name
            })
        return models

    def get_model_config(self, model_id: Optional[str] = None) -> Dict[str, Any]:
        """
        获取模型配置

        Args:
            model_id: str 模型ID，默认为默认模型

        Returns:
            Dict[str, Any]: 模型配置字典

        Raises:
            ValueError: 模型ID不存在时抛出
        """
        if model_id is None:
            model_id = self.default_model_id

        if model_id not in self.models_config:
            raise ValueError(f"模型不存在: {model_id}")

        return self.models_config[model_id]

    def get_default_model_id(self) -> str:
        """
        获取默认模型ID

        Returns:
            str: 默认模型ID
        """
        return self.default_model_id

    def get_default_model_config(self) -> Dict[str, Any]:
        """
        获取默认模型配置

        Returns:
            Dict[str, Any]: 默认模型配置字典
        """
        return self.get_model_config(self.default_model_id)

    @property
    def agent_config(self) -> Dict[str, Any]:
        """
        获取 Agent 配置

        Returns:
            Dict[str, Any]: Agent配置字典
        """
        return self.config.get('agent', {})

    @property
    def web_config(self) -> Dict[str, Any]:
        """
        获取 Web 服务配置

        Returns:
            Dict[str, Any]: Web服务配置字典
        """
        return self.config.get('web', {})

    @property
    def grpc_config(self) -> Dict[str, Any]:
        """
        获取 gRPC 服务配置

        Returns:
            Dict[str, Any]: gRPC服务配置字典
        """
        return self.config.get('grpc', {})

    def get_agent_config(self) -> Dict[str, Any]:
        """
        获取 Agent 详细配置（包括 react、memory、tools 等子配置）

        Returns:
            Dict[str, Any]: Agent 配置字典
        """
        return self.config.get('agent', {})

    def get_infrastructure_config(self) -> Dict[str, Any]:
        """
        获取基础设施配置（包括 redis、milvus、nacos 等）

        Returns:
            Dict[str, Any]: 基础设施配置字典
        """
        return self.config.get('infrastructure', {})
