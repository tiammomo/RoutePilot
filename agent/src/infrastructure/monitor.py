"""
================================================================================
基础设施监控模块 (Infrastructure Monitor)

提供统一的基础设施健康监控和指标收集，支持：
- Redis/Milvus/Nacos/MinIO/MySQL 健康检查
- 连接数和内存使用统计
- QPS 和延迟监控
- 告警通知

使用示例:
```python
from infrastructure.monitor import (
    InfrastructureMonitor, HealthStatus, ServiceType,
    create_monitor, check_all_services
)

# 创建监控器
monitor = await create_monitor()

# 检查所有服务
results = await monitor.check_all()

# 获取指标
metrics = await monitor.get_metrics()

# 启动监控循环
await monitor.start_monitoring(interval=30)
```

================================================================================
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ServiceType(Enum):
    """服务类型"""
    REDIS = "redis"
    MILVUS = "milvus"
    NACOS = "nacos"
    MINIO = "minio"
    MYSQL = "mysql"


class ComponentStatus(Enum):
    """组件状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ServiceHealth:
    """服务健康状态"""
    service: ServiceType
    status: ComponentStatus
    response_time_ms: float
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    last_check: float = field(default_factory=time.time)
    consecutive_failures: int = 0

    @property
    def is_healthy(self) -> bool:
        return self.status == ComponentStatus.HEALTHY


@dataclass
class ServiceMetrics:
    """服务指标"""
    service: ServiceType
    # 连接指标
    connections: int = 0
    connections_max: int = 0
    # 性能指标
    qps: float = 0.0
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    # 资源指标
    memory_used_mb: float = 0.0
    memory_limit_mb: float = 0.0
    # 存储指标
    storage_used_gb: float = 0.0
    storage_limit_gb: float = 0.0
    # 业务指标
    queue_size: int = 0
    cache_hit_rate: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class AlertConfig:
    """告警配置"""
    enabled: bool = True
    # 连续失败阈值
    consecutive_failure_threshold: int = 3
    # 响应时间阈值
    response_time_threshold_ms: float = 5000
    # 内存使用阈值
    memory_usage_threshold_percent: float = 85.0
    # QPS 阈值
    qps_threshold: float = 10000
    # 通知回调
    on_alert: Optional[Callable[[ServiceHealth], None]] = None


class HealthChecker:
    """健康检查器"""

    @staticmethod
    async def check_redis(host: str, port: int) -> ServiceHealth:
        """检查 Redis 健康状态"""
        import redis.asyncio as redis

        start_time = time.time()
        try:
            client = redis.Redis(host=host, port=port, socket_timeout=5.0)
            await client.ping()

            # 获取更多信息
            info = await client.info("stats")
            memory = await client.info("memory")

            response_time = (time.time() - start_time) * 1000

            return ServiceHealth(
                service=ServiceType.REDIS,
                status=ComponentStatus.HEALTHY,
                response_time_ms=response_time,
                message="Redis 连接正常",
                details={
                    "version": info.get("redis_version", "unknown"),
                    "connected_clients": info.get("connected_clients", 0),
                    "used_memory_human": memory.get("used_memory_human", "unknown"),
                    "ops_per_sec": info.get("instantaneous_ops_per_sec", 0)
                }
            )
        except Exception as e:
            return ServiceHealth(
                service=ServiceType.REDIS,
                status=ComponentStatus.UNHEALTHY,
                response_time_ms=(time.time() - start_time) * 1000,
                message=f"Redis 连接失败: {str(e)}",
                consecutive_failures=1
            )

    @staticmethod
    async def check_milvus(host: str, port: int) -> ServiceHealth:
        """检查 Milvus 健康状态"""
        import pymilvus

        start_time = time.time()
        try:
            from pymilvus import connections, utility

            connections.connect(host=host, port=port, db_name="default", timeout=5.0)

            # 获取集合信息
            collections = utility.list_collections()

            response_time = (time.time() - start_time) * 1000

            return ServiceHealth(
                service=ServiceType.MILVUS,
                status=ComponentStatus.HEALTHY,
                response_time_ms=response_time,
                message="Milvus 连接正常",
                details={
                    "collections_count": len(collections),
                    "collections": collections[:10]  # 只返回前10个
                }
            )
        except ImportError:
            return ServiceHealth(
                service=ServiceType.MILVUS,
                status=ComponentStatus.DEGRADED,
                response_time_ms=(time.time() - start_time) * 1000,
                message="pymilvus 未安装"
            )
        except Exception as e:
            return ServiceHealth(
                service=ServiceType.MILVUS,
                status=ComponentStatus.UNHEALTHY,
                response_time_ms=(time.time() - start_time) * 1000,
                message=f"Milvus 连接失败: {str(e)}",
                consecutive_failures=1
            )

    @staticmethod
    async def check_nacos(server_addresses: List[str], timeout: float = 5.0) -> ServiceHealth:
        """检查 Nacos 健康状态"""
        import httpx
        from urllib.parse import urlparse

        start_time = time.time()

        # 尝试每个节点
        errors = []
        for addr in server_addresses:
            try:
                parsed = urlparse(addr)
                health_url = f"{parsed.scheme}://{parsed.netloc}/nacos/v1/ns/service/list"

                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.get(health_url)
                    if response.status_code == 200:
                        response_time = (time.time() - start_time) * 1000
                        return ServiceHealth(
                            service=ServiceType.NACOS,
                            status=ComponentStatus.HEALTHY,
                            response_time_ms=response_time,
                            message="Nacos 连接正常",
                            details={
                                "server": addr,
                                "response": response.text[:200]
                            }
                        )
            except Exception as e:
                errors.append(f"{addr}: {str(e)}")

        return ServiceHealth(
            service=ServiceType.NACOS,
            status=ComponentStatus.UNHEALTHY,
            response_time_ms=(time.time() - start_time) * 1000,
            message=f"Nacos 所有节点不可用: {'; '.join(errors)}",
            consecutive_failures=1
        )

    @staticmethod
    async def check_minio(endpoint: str, timeout: float = 5.0) -> ServiceHealth:
        """检查 MinIO 健康状态"""
        import httpx

        start_time = time.time()

        try:
            # 健康检查 URL
            health_url = f"http://{endpoint}/minio/health/live"

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(health_url)

                if response.status_code == 200:
                    response_time = (time.time() - start_time) * 1000
                    return ServiceHealth(
                        service=ServiceType.MINIO,
                        status=ComponentStatus.HEALTHY,
                        response_time_ms=response_time,
                        message="MinIO 连接正常",
                        details={}
                    )
                else:
                    return ServiceHealth(
                        service=ServiceType.MINIO,
                        status=ComponentStatus.DEGRADED,
                        response_time_ms=(time.time() - start_time) * 1000,
                        message=f"MinIO 返回异常状态码: {response.status_code}"
                    )

        except Exception as e:
            return ServiceHealth(
                service=ServiceType.MINIO,
                status=ComponentStatus.UNHEALTHY,
                response_time_ms=(time.time() - start_time) * 1000,
                message=f"MinIO 连接失败: {str(e)}",
                consecutive_failures=1
            )

    @staticmethod
    async def check_mysql(
        host: str,
        port: int,
        username: str,
        password: str,
        database: str,
        timeout: float = 5.0
    ) -> ServiceHealth:
        """检查 MySQL 健康状态"""
        import aiomysql

        start_time = time.time()

        try:
            conn = await aiomysql.connect(
                host=host,
                port=port,
                user=username,
                password=password,
                db=database,
                connect_timeout=timeout
            )

            async with conn.cursor() as cursor:
                await cursor.execute("SELECT 1")
                await cursor.fetchone()

                # 获取状态信息
                await cursor.execute("SHOW STATUS LIKE 'Threads_connected'")
                threads = await cursor.fetchone()

                await cursor.execute("SHOW STATUS LIKE 'Uptime'")
                uptime = await cursor.fetchone()

            await conn.aclose()

            response_time = (time.time() - start_time) * 1000

            return ServiceHealth(
                service=ServiceType.MYSQL,
                status=ComponentStatus.HEALTHY,
                response_time_ms=response_time,
                message="MySQL 连接正常",
                details={
                    "threads_connected": threads[1] if threads else 0,
                    "uptime_seconds": uptime[1] if uptime else 0
                }
            )

        except ImportError:
            return ServiceHealth(
                service=ServiceType.MYSQL,
                status=ComponentStatus.DEGRADED,
                response_time_ms=(time.time() - start_time) * 1000,
                message="aiomysql 未安装"
            )
        except Exception as e:
            return ServiceHealth(
                service=ServiceType.MYSQL,
                status=ComponentStatus.UNHEALTHY,
                response_time_ms=(time.time() - start_time) * 1000,
                message=f"MySQL 连接失败: {str(e)}",
                consecutive_failures=1
            )


class MetricsCollector:
    """指标收集器"""

    def __init__(self):
        self._metrics: Dict[ServiceType, ServiceMetrics] = {}
        self._latency_history: Dict[ServiceType, List[float]] = {}

    async def collect_redis_metrics(
        self,
        host: str,
        port: int
    ) -> ServiceMetrics:
        """收集 Redis 指标"""
        import redis.asyncio as redis

        metrics = ServiceMetrics(service=ServiceType.REDIS)

        try:
            client = redis.Redis(host=host, port=port)

            # 连接数
            info = await client.info("clients")
            metrics.connections = info.get("connected_clients", 0)

            # 内存使用
            mem_info = await client.info("memory")
            metrics.memory_used_mb = mem_info.get("used_memory", 0) / (1024 * 1024)

            # QPS
            stats = await client.info("stats")
            metrics.qps = stats.get("instantaneous_ops_per_sec", 0)

            # 延迟历史
            latency = await client.ping()
            latency_ms = time.time() * 1000 if latency else 0

            if ServiceType.REDIS not in self._latency_history:
                self._latency_history[ServiceType.REDIS] = []
            self._latency_history[ServiceType.REDIS].append(latency_ms)

            # 保持最近100个延迟数据点
            history = self._latency_history[ServiceType.REDIS][-100:]
            if history:
                metrics.avg_latency_ms = sum(history) / len(history)

            await client.aclose()

        except Exception as e:
            logger.error(f"[MetricsCollector] Redis 指标收集失败: {e}")

        return metrics

    async def collect_milvus_metrics(
        self,
        host: str,
        port: int
    ) -> ServiceMetrics:
        """收集 Milvus 指标"""
        from pymilvus import connections, utility

        metrics = ServiceMetrics(service=ServiceType.MILVUS)

        try:
            connections.connect(host=host, port=port, db_name="default")

            # 集合数量
            collections = utility.list_collections()
            metrics.memory_used_mb = len(collections) * 10  # 估算

        except Exception as e:
            logger.error(f"[MetricsCollector] Milvus 指标收集失败: {e}")

        return metrics

    def collect_system_metrics(self) -> Dict[str, Any]:
        """收集系统级指标"""
        import psutil

        return {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_usage_percent": psutil.disk_usage('/').percent,
            "boot_time": datetime.fromtimestamp(psutil.boot_time()).isoformat()
        }


class InfrastructureMonitor:
    """
    基础设施监控器

    统一监控所有基础设施服务的健康状态和指标。
    """

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        milvus_host: str = "localhost",
        milvus_port: int = 19530,
        nacos_addresses: Optional[List[str]] = None,
        minio_endpoint: str = "localhost:9000",
        mysql_config: Optional[Dict[str, Any]] = None,
        alert_config: Optional[AlertConfig] = None
    ):
        """
        初始化监控器

        Args:
            redis_host: Redis 主机
            redis_port: Redis 端口
            milvus_host: Milvus 主机
            milvus_port: Milvus 端口
            nacos_addresses: Nacos 服务器地址列表
            minio_endpoint: MinIO 端点
            mysql_config: MySQL 配置
            alert_config: 告警配置
        """
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.milvus_host = milvus_host
        self.milvus_port = milvus_port
        self.nacos_addresses = nacos_addresses or ["http://localhost:38848"]
        self.minio_endpoint = minio_endpoint
        self.mysql_config = mysql_config

        self.alert_config = alert_config or AlertConfig()

        self._health_checker = HealthChecker()
        self._metrics_collector = MetricsCollector()

        self._health_status: Dict[ServiceType, ServiceHealth] = {}
        self._metrics: Dict[ServiceType, ServiceMetrics] = {}

        self._monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None

    async def check_all(self) -> Dict[ServiceType, ServiceHealth]:
        """
        检查所有服务健康状态

        Returns:
            Dict: 服务健康状态
        """
        results = {}

        # 并发检查所有服务
        tasks = []

        tasks.append(self._check_redis())
        tasks.append(self._check_milvus())
        tasks.append(self._check_nacos())
        tasks.append(self._check_minio())

        if self.mysql_config:
            tasks.append(self._check_mysql())

        health_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in health_results:
            if isinstance(result, ServiceHealth):
                self._health_status[result.service] = result
                results[result.service] = result

        return results

    async def _check_redis(self) -> ServiceHealth:
        """检查 Redis"""
        result = await self._health_checker.check_redis(
            self.redis_host,
            self.redis_port
        )

        if self._should_alert(result):
            self._send_alert(result)

        return result

    async def _check_milvus(self) -> ServiceHealth:
        """检查 Milvus"""
        result = await self._health_checker.check_milvus(
            self.milvus_host,
            self.milvus_port
        )

        if self._should_alert(result):
            self._send_alert(result)

        return result

    async def _check_nacos(self) -> ServiceHealth:
        """检查 Nacos"""
        result = await self._health_checker.check_nacos(
            self.nacos_addresses
        )

        if self._should_alert(result):
            self._send_alert(result)

        return result

    async def _check_minio(self) -> ServiceHealth:
        """检查 MinIO"""
        result = await self._health_checker.check_minio(
            self.minio_endpoint
        )

        if self._should_alert(result):
            self._send_alert(result)

        return result

    async def _check_mysql(self) -> ServiceHealth:
        """检查 MySQL"""
        config = self.mysql_config
        result = await self._health_checker.check_mysql(
            host=config["host"],
            port=config.get("port", 3306),
            username=config["username"],
            password=config["password"],
            database=config["database"]
        )

        if self._should_alert(result):
            self._send_alert(result)

        return result

    def _should_alert(self, health: ServiceHealth) -> bool:
        """判断是否应该发送告警"""
        if not self.alert_config.enabled:
            return False

        # 连续失败
        if health.consecutive_failures >= self.alert_config.consecutive_failure_threshold:
            return True

        # 响应时间过长
        if health.response_time_ms > self.alert_config.response_time_threshold_ms:
            return True

        return False

    def _send_alert(self, health: ServiceHealth) -> None:
        """发送告警"""
        if self.alert_config.on_alert:
            self.alert_config.on_alert(health)

        logger.warning(
            f"[InfrastructureMonitor] 告警: {health.service.value} - "
            f"状态: {health.status.value}, "
            f"响应时间: {health.response_time_ms:.2f}ms, "
            f"消息: {health.message}"
        )

    async def get_metrics(self) -> Dict[ServiceType, ServiceMetrics]:
        """
        获取所有服务指标

        Returns:
            Dict: 服务指标
        """
        metrics = {}

        # Redis
        metrics[ServiceType.REDIS] = await self._metrics_collector.collect_redis_metrics(
            self.redis_host,
            self.redis_port
        )

        # Milvus
        metrics[ServiceType.MILVUS] = await self._metrics_collector.collect_milvus_metrics(
            self.milvus_host,
            self.milvus_port
        )

        self._metrics = metrics
        return metrics

    async def get_full_status(self) -> Dict[str, Any]:
        """
        获取完整状态

        Returns:
            Dict: 完整状态信息
        """
        health = await self.check_all()
        metrics = await self.get_metrics()
        system = self._metrics_collector.collect_system_metrics()

        # 计算总体状态
        all_healthy = all(h.is_healthy for h in health.values())

        return {
            "status": "healthy" if all_healthy else "degraded",
            "timestamp": datetime.now().isoformat(),
            "services": {
                service.value: {
                    "status": h.status.value,
                    "response_time_ms": round(h.response_time_ms, 2),
                    "message": h.message,
                    "details": h.details
                }
                for service, h in health.items()
            },
            "metrics": {
                service.value: {
                    "qps": m.qps,
                    "avg_latency_ms": round(m.avg_latency_ms, 2),
                    "memory_used_mb": round(m.memory_used_mb, 2),
                    "connections": m.connections
                }
                for service, m in metrics.items()
            },
            "system": system
        }

    async def start_monitoring(self, interval: int = 30) -> None:
        """
        启动监控循环

        Args:
            interval: 检查间隔（秒）
        """
        if self._monitoring:
            return

        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop(interval))

    async def _monitor_loop(self, interval: int) -> None:
        """监控循环"""
        logger.info(f"[InfrastructureMonitor] 启动监控，间隔: {interval}秒")

        while self._monitoring:
            try:
                await self.check_all()
                logger.debug("[InfrastructureMonitor] 周期检查完成")
            except Exception as e:
                logger.error(f"[InfrastructureMonitor] 监控错误: {e}")

            await asyncio.sleep(interval)

    async def stop_monitoring(self) -> None:
        """停止监控"""
        self._monitoring = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        logger.info("[InfrastructureMonitor] 监控已停止")

    def get_service_status(self, service: ServiceType) -> Optional[ServiceHealth]:
        """获取单个服务状态"""
        return self._health_status.get(service)


# =============================================================================
# 便捷函数
# =============================================================================

async def create_monitor(
    config_path: Optional[str] = None,
    **kwargs
) -> InfrastructureMonitor:
    """
    创建监控器

    Args:
        config_path: 配置文件路径
        **kwargs: 其他配置

    Returns:
        InfrastructureMonitor: 监控器实例
    """
    from .infra_config import get_config

    if config_path:
        infra_config = get_config(config_path)

        redis_host = infra_config.redis.host
        redis_port = infra_config.redis.port

        milvus_host = infra_config.milvus.host
        milvus_port = infra_config.milvus.port

        nacos_addresses = infra_config.nacos.server_addresses

        minio_endpoint = infra_config.minio.endpoint

        mysql_config = {
            "host": infra_config.mysql.host,
            "port": infra_config.mysql.port,
            "username": infra_config.mysql.username,
            "password": infra_config.mysql.password,
            "database": infra_config.mysql.database
        }

        return InfrastructureMonitor(
            redis_host=redis_host,
            redis_port=redis_port,
            milvus_host=milvus_host,
            milvus_port=milvus_port,
            nacos_addresses=nacos_addresses,
            minio_endpoint=minio_endpoint,
            mysql_config=mysql_config,
            **kwargs
        )

    return InfrastructureMonitor(**kwargs)


async def check_all_services(
    redis_host: str = "localhost",
    redis_port: int = 6379,
    milvus_host: str = "localhost",
    milvus_port: int = 19530,
    nacos_addresses: Optional[List[str]] = None,
    minio_endpoint: str = "localhost:9000"
) -> Dict[str, Any]:
    """
    快速检查所有服务

    Returns:
        Dict: 检查结果
    """
    monitor = InfrastructureMonitor(
        redis_host=redis_host,
        redis_port=redis_port,
        milvus_host=milvus_host,
        milvus_port=milvus_port,
        nacos_addresses=nacos_addresses,
        minio_endpoint=minio_endpoint
    )

    status = await monitor.get_full_status()
    await monitor.stop_monitoring()

    return status
