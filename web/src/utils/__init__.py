"""
================================================================================
工具函数模块
================================================================================

提供项目常用的工具函数。

功能分类:
    - datetime: 日期时间工具
    - security: 安全工具
    - string: 字符串工具
    - validation: 验证工具
    - async: 异步工具

使用示例:
    from utils import generate_session_id, validate_uuid, format_timestamp

================================================================================
"""

import hashlib
import hmac
import json
import os
import random
import re
import secrets
import string
import time
import uuid
from datetime import datetime, timezone, timedelta
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

import logging

logger = logging.getLogger(__name__)

# =============================================================================
# 时间日期工具
# =============================================================================

def get_current_timestamp() -> float:
    """获取当前时间戳（秒）"""
    return time.time()


def get_current_datetime() -> datetime:
    """获取当前日期时间（UTC）"""
    return datetime.now(timezone.utc)


def get_current_datetime_str(format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """获取当前日期时间字符串

    Args:
        format_str: 日期时间格式，默认 "%Y-%m-%d %H:%M:%S"

    Returns:
        格式化后的日期时间字符串
    """
    return datetime.now(timezone.utc).strftime(format_str)


def format_timestamp(timestamp: float, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """格式化时间戳

    Args:
        timestamp: Unix 时间戳（秒）
        format_str: 日期时间格式

    Returns:
        格式化后的日期时间字符串
    """
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return dt.strftime(format_str)


def parse_datetime(datetime_str: str, format_str: str = "%Y-%m-%d %H:%M:%S") -> datetime:
    """解析日期时间字符串

    Args:
        datetime_str: 日期时间字符串
        format_str: 日期时间格式

    Returns:
        datetime 对象
    """
    return datetime.strptime(datetime_str, format_str).replace(tzinfo=timezone.utc)


def get_date_days_ago(days: int) -> datetime:
    """获取 N 天前的日期

    Args:
        days: 天数

    Returns:
        N 天前的 datetime 对象
    """
    return datetime.now(timezone.utc) - timedelta(days=days)


def format_duration(seconds: float) -> str:
    """格式化时长

    Args:
        seconds: 秒数

    Returns:
        格式化后的时长字符串，如 "1h 30m 15s"
    """
    if seconds < 60:
        return f"{seconds:.1f}s"

    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)

    if minutes < 60:
        return f"{minutes}m {remaining_seconds}s"

    hours = minutes // 60
    remaining_minutes = minutes % 60
    return f"{hours}h {remaining_minutes}m"


# =============================================================================
# ID 生成工具
# =============================================================================

def generate_session_id() -> str:
    """生成会话 ID

    Returns:
        会话 ID（UUID 格式）
    """
    return str(uuid.uuid4())


def generate_short_id(length: int = 8) -> str:
    """生成短 ID

    Args:
        length: ID 长度，默认 8

    Returns:
        短 ID 字符串
    """
    alphabet = string.ascii_letters + string.digits
    return ''.join(random.choices(alphabet, k=length))


def generate_api_key(prefix: str = "sta") -> str:
    """生成 API 密钥

    Args:
        prefix: 前缀，默认 "sta"

    Returns:
        API 密钥，如 "sta_abc123..."
    """
    random_part = secrets.token_urlsafe(32)
    return f"{prefix}_{random_part}"


# =============================================================================
# 字符串工具
# =============================================================================

def truncate(text: str, max_length: int, suffix: str = "...") -> str:
    """截断字符串

    Args:
        text: 原始文本
        max_length: 最大长度
        suffix: 截断后缀

    Returns:
        截断后的字符串
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def slugify(text: str) -> str:
    """将文本转换为 URL 友好的 slug

    Args:
        text: 原始文本

    Returns:
        slug 字符串
    """
    # 转小写
    text = text.lower()
    # 替换空格和特殊字符
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip('-')


def mask_sensitive(text: str, visible_chars: int = 4) -> str:
    """脱敏处理

    Args:
        text: 原始文本
        visible_chars: 保留的可显示字符数

    Returns:
        脱敏后的字符串
    """
    if len(text) <= visible_chars:
        return '*' * len(text)

    masked_length = len(text) - visible_chars
    return '*' * masked_length + text[-visible_chars:]


def strip_html(html: str) -> str:
    """去除 HTML 标签

    Args:
        html: HTML 文本

    Returns:
        纯文本
    """
    return re.sub(r'<[^>]+>', '', html)


def extract_mentions(text: str) -> List[str]:
    """提取 @ 提及的用户

    Args:
        text: 文本

    Returns:
        提及的用户列表
    """
    return re.findall(r'@(\w+)', text)


def extract_hashtags(text: str) -> List[str]:
    """提取 # 标签

    Args:
        text: 文本

    Returns:
        标签列表
    """
    return re.findall(r'#(\w+)', text)


# =============================================================================
# 验证工具
# =============================================================================

def is_valid_uuid(text: str) -> bool:
    """验证 UUID 格式

    Args:
        text: 待验证文本

    Returns:
        是否为有效的 UUID
    """
    try:
        uuid.UUID(text)
        return True
    except (ValueError, AttributeError):
        return False


def validate_email(email: str) -> bool:
    """验证邮箱格式

    Args:
        email: 邮箱地址

    Returns:
        是否为有效的邮箱格式
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_url(url: str) -> bool:
    """验证 URL 格式

    Args:
        url: URL 地址

    Returns:
        是否为有效的 URL 格式
    """
    pattern = r'^https?://[^\s/$.?#].[^\s]*$'
    return bool(re.match(pattern, url))


# =============================================================================
# 安全工具
# =============================================================================

def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """密码哈希

    Args:
        password: 密码
        salt: 盐值（可选）

    Returns:
        (哈希值, 盐值) 元组
    """
    if salt is None:
        salt = secrets.token_hex(16)

    hashed = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return hashed.hex(), salt


def verify_password(password: str, hashed: str, salt: str) -> bool:
    """验证密码

    Args:
        password: 密码
        hashed: 哈希值
        salt: 盐值

    Returns:
        是否匹配
    """
    computed_hash, _ = hash_password(password, salt)
    return hmac.compare_digest(computed_hash, hashed)


def generate_token(length: int = 32) -> str:
    """生成随机令牌

    Args:
        length: 令牌长度

    Returns:
        随机令牌
    """
    return secrets.token_urlsafe(length)


# =============================================================================
# 异步工具
# =============================================================================

T = TypeVar('T')


async def run_in_thread_pool(
    func: Callable[..., T],
    *args: Any,
    **kwargs: Any
) -> T:
    """在线程池中运行阻塞函数

    Args:
        func: 要运行的函数
        *args: 位置参数
        **kwargs: 关键字参数

    Returns:
        函数返回值
    """
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


def async_retry(max_attempts: int = 3, delay: float = 1.0):
    """异步重试装饰器

    Args:
        max_attempts: 最大尝试次数
        delay: 重试延迟（秒）

    示例:
        @async_retry(max_attempts=3, delay=2.0)
        async def fetch_data():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_attempts} failed: {e}. "
                            f"Retrying in {delay}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"All {max_attempts} attempts failed")
            raise last_exception

        return wrapper
    return decorator


def retry(max_attempts: int = 3, delay: float = 1.0):
    """同步重试装饰器

    Args:
        max_attempts: 最大尝试次数
        delay: 重试延迟（秒）

    示例:
        @retry(max_attempts=3, delay=2.0)
        def fetch_data():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_attempts} failed: {e}. "
                            f"Retrying in {delay}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(f"All {max_attempts} attempts failed")
            raise last_exception

        return wrapper
    return decorator


# =============================================================================
# 数据转换工具
# =============================================================================

def dict_to_json(data: Dict) -> str:
    """字典转 JSON 字符串

    Args:
        data: 字典数据

    Returns:
        JSON 字符串
    """
    return json.dumps(data, ensure_ascii=False, indent=2)


def json_to_dict(json_str: str) -> Dict:
    """JSON 字符串转字典

    Args:
        json_str: JSON 字符串

    Returns:
        字典数据
    """
    return json.loads(json_str)


def flatten_dict(data: Dict, parent_key: str = '', sep: str = '.') -> Dict:
    """扁平化字典

    Args:
        data: 嵌套字典
        sep: 分隔符

    示例:
        flatten_dict({'a': {'b': 1}}) -> {'a.b': 1}

    Returns:
        扁平化后的字典
    """
    items: List[tuple] = []
    for k, v in data.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def safe_get(data: Dict, key_path: str, default: Any = None) -> Any:
    """安全获取嵌套字典值

    Args:
        data: 字典数据
        key_path: 键路径，如 "a.b.c"
        default: 默认值

    示例:
        safe_get({'a': {'b': 1}}, 'a.b') -> 1
        safe_get({'a': {'b': 1}}, 'a.c', 'default') -> 'default'

    Returns:
        获取到的值或默认值
    """
    keys = key_path.split('.')
    current = data

    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default

    return current


# =============================================================================
# 文件工具
# =============================================================================

def ensure_dir(path: str) -> None:
    """确保目录存在

    Args:
        path: 目录路径
    """
    os.makedirs(path, exist_ok=True)


def get_file_size(path: str) -> int:
    """获取文件大小（字节）

    Args:
        path: 文件路径

    Returns:
        文件大小
    """
    return os.path.getsize(path)


def get_file_extension(path: str) -> str:
    """获取文件扩展名

    Args:
        path: 文件路径

    Returns:
        扩展名（不含点）
    """
    return os.path.splitext(path)[1][1:]


def read_file_lines(path: str, encoding: str = 'utf-8') -> List[str]:
    """读取文件所有行

    Args:
        path: 文件路径
        encoding: 编码格式

    Returns:
        行列表
    """
    with open(path, 'r', encoding=encoding) as f:
        return f.readlines()


def write_file_lines(path: str, lines: List[str], encoding: str = 'utf-8') -> None:
    """写入文件多行

    Args:
        path: 文件路径
        lines: 行列表
        encoding: 编码格式
    """
    ensure_dir(os.path.dirname(path))
    with open(path, 'w', encoding=encoding) as f:
        f.writelines(lines)


# =============================================================================
# 杂项工具
# =============================================================================

def get_env(key: str, default: Any = None, required: bool = False) -> Any:
    """获取环境变量

    Args:
        key: 环境变量名
        default: 默认值
        required: 是否必需

    Returns:
        环境变量值

    Raises:
        ValueError: 当 required=True 且环境变量未设置时
    """
    value = os.getenv(key, default)
    if required and value is None:
        raise ValueError(f"Required environment variable '{key}' is not set")
    return value


def deep_merge(base: Dict, update: Dict) -> Dict:
    """深度合并字典

    Args:
        base: 基础字典
        update: 更新字典

    示例:
        deep_merge({'a': 1, 'b': {'c': 2}}, {'b': {'d': 3}})
        -> {'a': 1, 'b': {'c': 2, 'd': 3}}

    Returns:
        合并后的字典
    """
    result = base.copy()
    for key, value in update.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def calculate_checksum(data: Union[str, bytes], algorithm: str = 'md5') -> str:
    """计算数据校验和

    Args:
        data: 数据
        algorithm: 算法（md5, sha1, sha256）

    Returns:
        校验和十六进制字符串
    """
    if isinstance(data, str):
        data = data.encode('utf-8')

    if algorithm == 'md5':
        return hashlib.md5(data).hexdigest()
    elif algorithm == 'sha1':
        return hashlib.sha1(data).hexdigest()
    elif algorithm == 'sha256':
        return hashlib.sha256(data).hexdigest()
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")


# =============================================================================
# 导入 asyncio 以支持异步装饰器
# =============================================================================

import asyncio


__all__ = [
    # Time
    "get_current_timestamp",
    "get_current_datetime",
    "get_current_datetime_str",
    "format_timestamp",
    "parse_datetime",
    "get_date_days_ago",
    "format_duration",
    # ID Generation
    "generate_session_id",
    "generate_short_id",
    "generate_api_key",
    # String
    "truncate",
    "slugify",
    "mask_sensitive",
    "strip_html",
    "extract_mentions",
    "extract_hashtags",
    # Validation
    "is_valid_uuid",
    "validate_email",
    "validate_url",
    # Security
    "hash_password",
    "verify_password",
    "generate_token",
    # Async
    "run_in_thread_pool",
    "async_retry",
    "retry",
    # Data
    "dict_to_json",
    "json_to_dict",
    "flatten_dict",
    "safe_get",
    # File
    "ensure_dir",
    "get_file_size",
    "get_file_extension",
    "read_file_lines",
    "write_file_lines",
    # Misc
    "get_env",
    "deep_merge",
    "calculate_checksum",
]
