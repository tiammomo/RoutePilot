"""
================================================================================
基础设施层 - Snowflake ID 生成器 (Snowflake ID Generator)

提供分布式唯一 ID 生成功能，支持时间序列排序和数据中心/工作节点配置。

功能特点:
- 分布式唯一 ID 生成
- 时间序列排序支持
- 可配置的数据中心和工作节点
- 高性能异步生成
- ID 解析和验证

使用示例:
```python
from infrastructure.snowflake import SnowflakeGenerator, get_worker_id

# 创建生成器
generator = SnowflakeGenerator(data_center_id=1, worker_id=1)

# 生成 ID
id = generator.generate()

# 解析 ID
info = generator.parse(id)
print(f"时间戳: {info.timestamp}, 数据中心: {info.data_center_id}, 序列号: {info.sequence}")
```

================================================================================
"""

import time
import threading
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class SnowflakeConfig:
    """Snowflake 配置"""

    # 各个部分的位数
    TIMESTAMP_BITS = 41
    DATA_CENTER_BITS = 5
    WORKER_BITS = 5
    SEQUENCE_BITS = 12

    # 最大值
    MAX_DATA_CENTER_ID = (1 << DATA_CENTER_BITS) - 1  # 31
    MAX_WORKER_ID = (1 << WORKER_BITS) - 1  # 31
    MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1  # 4095

    # 起始时间戳（2024-01-01 00:00:00 UTC）
    EPOCH = 1704067200000  # 毫秒时间戳

    def __init__(
        self,
        data_center_id: int = 0,
        worker_id: int = 0,
        timestamp_bits: int = TIMESTAMP_BITS,
        data_center_bits: int = DATA_CENTER_BITS,
        worker_bits: int = WORKER_BITS,
        sequence_bits: int = SEQUENCE_BITS,
        epoch: int = EPOCH
    ):
        """
        初始化配置

        Args:
            data_center_id: 数据中心 ID (0-31)
            worker_id: 工作节点 ID (0-31)
            timestamp_bits: 时间戳位数
            data_center_bits: 数据中心 ID 位数
            worker_bits: 工作节点 ID 位数
            sequence_bits: 序列号位数
            epoch: 起始时间戳（毫秒）
        """
        self.data_center_id = data_center_id
        self.worker_id = worker_id
        self.timestamp_bits = timestamp_bits
        self.data_center_bits = data_center_bits
        self.worker_bits = worker_bits
        self.sequence_bits = sequence_bits
        self.epoch = epoch

        # 验证配置
        if data_center_id < 0 or data_center_id > self.MAX_DATA_CENTER_ID:
            raise ValueError(f"data_center_id 必须介于 0 和 {self.MAX_DATA_CENTER_ID} 之间")
        if worker_id < 0 or worker_id > self.MAX_WORKER_ID:
            raise ValueError(f"worker_id 必须介于 0 和 {self.MAX_WORKER_ID} 之间")

        # 计算移位
        self._timestamp_shift = data_center_bits + worker_bits + sequence_bits
        self._data_center_shift = worker_bits + sequence_bits
        self._worker_shift = sequence_bits


class SnowflakeID:
    """Snowflake ID 信息"""

    def __init__(
        self,
        id: int,
        timestamp: int,
        data_center_id: int,
        worker_id: int,
        sequence: int,
        generated_at: datetime
    ):
        self.id = id
        self.timestamp = timestamp
        self.data_center_id = data_center_id
        self.worker_id = worker_id
        self.sequence = sequence
        self.generated_at = generated_at

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "data_center_id": self.data_center_id,
            "worker_id": self.worker_id,
            "sequence": self.sequence,
            "generated_at": self.generated_at.isoformat()
        }

    def __str__(self) -> str:
        return f"SnowflakeID({self.id})"

    def __repr__(self) -> str:
        return (
            f"SnowflakeID(id={self.id}, "
            f"dc={self.data_center_id}, "
            f"w={self.worker_id}, "
            f"seq={self.sequence})"
        )


class SnowflakeGenerator:
    """
    Snowflake ID 生成器

    基于 Twitter Snowflake 算法，支持分布式唯一 ID 生成。
    ID 结构（从高位到低位）:
    - 时间戳 (41 位)
    - 数据中心 ID (5 位)
    - 工作节点 ID (5 位)
    - 序列号 (12 位)
    """

    def __init__(
        self,
        data_center_id: int = 0,
        worker_id: int = 0,
        config: Optional[SnowflakeConfig] = None
    ):
        """
        初始化生成器

        Args:
            data_center_id: 数据中心 ID (0-31)
            worker_id: 工作节点 ID (0-31)
            config: Snowflake 配置
        """
        self.config = config or SnowflakeConfig(data_center_id=data_center_id, worker_id=worker_id)

        self._last_timestamp = -1
        self._sequence = 0
        self._lock = threading.Lock()
        self._worker_id = self.config.worker_id
        self._data_center_id = self.config.data_center_id

        logger.info(
            f"[SnowflakeGenerator] 初始化完成: "
            f"data_center={self._data_center_id}, worker={self._worker_id}"
        )

    @property
    def data_center_id(self) -> int:
        """获取数据中心 ID"""
        return self._data_center_id

    @property
    def worker_id(self) -> int:
        """获取工作节点 ID"""
        return self._worker_id

    def _get_timestamp(self) -> int:
        """获取当前时间戳（毫秒）"""
        return int(time.time() * 1000)

    def _wait_for_next_timestamp(self, last_timestamp: int) -> int:
        """
        等待下一个时间戳

        Args:
            last_timestamp: 最后时间戳

        Returns:
            int: 下一个时间戳
        """
        timestamp = self._get_timestamp()
        while timestamp <= last_timestamp:
            timestamp = self._get_timestamp()
        return timestamp

    def generate(self) -> int:
        """
        生成唯一 ID

        Returns:
            int: 生成的 ID

        Raises:
            RuntimeError: 系统时钟回退
        """
        with self._lock:
            timestamp = self._get_timestamp()

            # 检查时钟回退
            if timestamp < self._last_timestamp:
                raise RuntimeError(
                    f"时钟回退检测: {timestamp} < {self._last_timestamp}. "
                    "请检查系统时间。"
                )

            # 如果是同一毫秒，递增序列号
            if timestamp == self._last_timestamp:
                self._sequence = (self._sequence + 1) & self.config.MAX_SEQUENCE
                if self._sequence == 0:
                    # 序列号用尽，等待下一毫秒
                    timestamp = self._wait_for_next_timestamp(timestamp)
            else:
                # 新毫秒，重置序列号
                self._sequence = 0

            self._last_timestamp = timestamp

            # 构建 ID
            id = (
                (timestamp - self.config.epoch) << self.config._timestamp_shift |
                self._data_center_id << self.config._data_center_shift |
                self._worker_id << self.config._worker_shift |
                self._sequence
            )

            return id

    def parse(self, id: int) -> SnowflakeID:
        """
        解析 ID

        Args:
            id: Snowflake ID

        Returns:
            SnowflakeID: 解析结果
        """
        # 提取各个部分
        sequence = id & self.config.MAX_SEQUENCE
        worker_id = (id >> self.config._worker_shift) & self.config.MAX_WORKER_ID
        data_center_id = (id >> self.config._data_center_shift) & self.config.MAX_DATA_CENTER_ID
        timestamp = (id >> self.config._timestamp_shift) + self.config.epoch

        # 转换时间戳为 datetime
        generated_at = datetime.fromtimestamp(timestamp / 1000)

        return SnowflakeID(
            id=id,
            timestamp=timestamp,
            data_center_id=data_center_id,
            worker_id=worker_id,
            sequence=sequence,
            generated_at=generated_at
        )

    def get_info(self) -> dict:
        """获取生成器信息"""
        return {
            "data_center_id": self._data_center_id,
            "worker_id": self._worker_id,
            "config": {
                "timestamp_bits": self.config.timestamp_bits,
                "data_center_bits": self.config.data_center_bits,
                "worker_bits": self.config.worker_bits,
                "sequence_bits": self.config.sequence_bits,
                "epoch": self.config.epoch,
                "max_data_center_id": self.config.MAX_DATA_CENTER_ID,
                "max_worker_id": self.config.MAX_WORKER_ID,
                "max_sequence": self.config.MAX_SEQUENCE
            }
        }


class AsyncSnowflakeGenerator:
    """
    异步 Snowflake ID 生成器

    支持异步环境下的高性能 ID 生成。
    """

    def __init__(
        self,
        data_center_id: int = 0,
        worker_id: int = 0,
        config: Optional[SnowflakeConfig] = None
    ):
        """
        初始化生成器

        Args:
            data_center_id: 数据中心 ID
            worker_id: 工作节点 ID
            config: Snowflake 配置
        """
        self._generator = SnowflakeGenerator(data_center_id, worker_id, config)
        self._lock = asyncio.Lock()

    @property
    def data_center_id(self) -> int:
        return self._generator.data_center_id

    @property
    def worker_id(self) -> int:
        return self._generator.worker_id

    async def generate(self) -> int:
        """
        异步生成唯一 ID

        Returns:
            int: 生成的 ID
        """
        async with self._lock:
            return self._generator.generate()

    def parse(self, id: int) -> SnowflakeID:
        """解析 ID"""
        return self._generator.parse(id)


# 全局生成器实例
_default_generator: Optional[SnowflakeGenerator] = None
_default_async_generator: Optional[AsyncSnowflakeGenerator] = None


def get_generator(
    data_center_id: int = 0,
    worker_id: int = 0
) -> SnowflakeGenerator:
    """
    获取全局 Snowflake 生成器

    Args:
        data_center_id: 数据中心 ID
        worker_id: 工作节点 ID

    Returns:
        SnowflakeGenerator: 生成器实例
    """
    global _default_generator

    if _default_generator is None:
        _default_generator = SnowflakeGenerator(
            data_center_id=data_center_id,
            worker_id=worker_id
        )

    return _default_generator


def get_async_generator(
    data_center_id: int = 0,
    worker_id: int = 0
) -> AsyncSnowflakeGenerator:
    """
    获取全局异步 Snowflake 生成器

    Args:
        data_center_id: 数据中心 ID
        worker_id: 工作节点 ID

    Returns:
        AsyncSnowflakeGenerator: 异步生成器实例
    """
    global _default_async_generator

    if _default_async_generator is None:
        _default_async_generator = AsyncSnowflakeGenerator(
            data_center_id=data_center_id,
            worker_id=worker_id
        )

    return _default_async_generator


def generate_id(data_center_id: int = 0, worker_id: int = 0) -> int:
    """
    便捷函数：生成唯一 ID

    Args:
        data_center_id: 数据中心 ID
        worker_id: 工作节点 ID

    Returns:
        int: 生成的 ID
    """
    generator = get_generator(data_center_id, worker_id)
    return generator.generate()


def parse_id(id: int) -> SnowflakeID:
    """
    便捷函数：解析 ID

    Args:
        id: Snowflake ID

    Returns:
        SnowflakeID: 解析结果
    """
    generator = get_generator()
    return generator.parse(id)
