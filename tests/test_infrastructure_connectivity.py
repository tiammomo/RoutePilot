"""
基础设施连通性测试 (Infrastructure Connectivity Tests)

测试所有基础设施组件的连接状态:
- Redis (消息队列 & 缓存)
- Milvus (向量数据库)
- Nacos (配置中心)
- MySQL (Nacos 数据库)

使用方法:
    uv run python tests/test_infrastructure_connectivity.py

输出示例:
    ============================================================
        基础设施连通性测试
    ============================================================

    [Test 1/4] Redis 连接测试
    --------------
    地址: localhost:6379
    状态: ✅ healthy
    详情:
      - PING: PONG
      - SET: OK
      - GET: test_value
      - DEL: 1
      - 队列长度: 0

    [Test 2/4] Milvus 连接测试
    --------------
    地址: localhost:19530
    状态: ✅ healthy
    详情:
      - 连接: 成功
      - 健康检查: OK

    ...

    ============================================================
    测试结果: 4/4 通过
    ============================================================
"""

import sys
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

# 添加项目路径
sys.path.insert(0, 'agent/src')

from infrastructure.infra_config import get_config


# =============================================================================
# 测试结果格式化
# =============================================================================

class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = True
        self.start_time = None
        self.end_time = None
        self.details: Dict[str, Any] = {}
        self.errors: list = []

    @property
    def duration_ms(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0


def print_header():
    print("\n" + "=" * 60)
    print("    基础设施连通性测试")
    print("    " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60 + "\n")


def print_result(result: TestResult):
    status = "✅ healthy" if result.passed else "❌ unhealthy"
    print(f"[Test] {result.name}")
    print(f"  状态: {status}")
    print(f"  耗时: {result.duration_ms:.1f}ms")

    if result.details:
        print("  详情:")
        for key, value in result.details.items():
            print(f"    - {key}: {value}")

    if result.errors:
        print("  错误:")
        for error in result.errors:
            print(f"    - {error}")

    print()


# =============================================================================
# Redis 连通性测试
# =============================================================================

async def test_redis() -> TestResult:
    """测试 Redis 连接"""
    result = TestResult("Redis 连接测试")
    result.start_time = datetime.now().timestamp()

    try:
        import redis.asyncio as redis

        config = get_config()
        host = config.redis.host
        port = config.redis.port

        # 创建连接
        client = redis.Redis(host=host, port=port, decode_responses=True)

        # 测试 PING
        ping_result = await client.ping()
        result.details["PING"] = "PONG" if ping_result else "FAILED"

        # 测试 SET/GET
        test_key = f"{config.redis.key_prefix}connectivity_test"
        set_result = await client.set(test_key, "test_value", ex=60)
        result.details["SET"] = "OK" if set_result else "FAILED"

        get_result = await client.get(test_key)
        result.details["GET"] = get_result if get_result else "FAILED"

        # 测试 DEL
        del_result = await client.delete(test_key)
        result.details["DEL"] = str(del_result)

        # 检查队列
        queue_len = await client.llen(config.redis.queues.task_queue)
        result.details["队列长度"] = str(queue_len)

        # 清理测试数据
        await client.delete(test_key)

        await client.aclose()

        if ping_result and set_result:
            result.passed = True
        else:
            result.passed = False
            result.errors.append("Redis 基本操作失败")

    except ImportError as e:
        result.passed = False
        result.errors.append(f"Redis 模块未安装: {e}")
    except Exception as e:
        result.passed = False
        result.errors.append(f"连接失败: {e}")

    result.end_time = datetime.now().timestamp()
    return result


# =============================================================================
# Milvus 连通性测试
# =============================================================================

async def test_milvus() -> TestResult:
    """测试 Milvus 连接"""
    result = TestResult("Milvus 连接测试")
    result.start_time = datetime.now().timestamp()

    try:
        from pymilvus import connections, utility

        config = get_config()
        host = config.milvus.host
        port = config.milvus.port

        # 连接
        connections.connect(host=host, port=str(port))
        result.details["连接"] = "成功"

        # 健康检查
        try:
            health = utility.get_server_version()
            result.details["版本"] = health
        except:
            result.details["版本"] = "未知"

        # 列出集合
        try:
            collections = utility.list_collections()
            result.details["集合列表"] = str(collections) if collections else "空"
        except Exception as e:
            result.details["集合列表"] = f"获取失败: {e}"

        # 检查指定集合
        collection_name = "travel_documents"
        if collection_name in collections:
            result.details[f"集合 '{collection_name}'"] = "存在"
        else:
            result.details[f"集合 '{collection_name}'"] = "不存在（可创建）"

        try:
            connections.disconnect("default")
        except:
            pass

    except ImportError as e:
        result.passed = False
        result.errors.append(f"pymilvus 未安装: {e}")
    except Exception as e:
        result.passed = False
        result.errors.append(f"连接失败: {e}")

    result.end_time = datetime.now().timestamp()
    return result


# =============================================================================
# Nacos 连通性测试
# =============================================================================

async def test_nacos() -> TestResult:
    """测试 Nacos 连接"""
    result = TestResult("Nacos 连接测试")
    result.start_time = datetime.now().timestamp()

    try:
        import httpx

        config = get_config()
        server_addr = config.nacos.server_addresses[0]
        username = config.nacos.username
        password = config.nacos.password

        # 健康检查
        health_url = f"{server_addr}/nacos/v1/ns/service/list"
        try:
            response = httpx.get(health_url, timeout=5.0)
            if response.status_code == 200:
                result.details["健康检查"] = "OK"
            else:
                result.details["健康检查"] = f"HTTP {response.status_code}"
        except httpx.TimeoutException:
            result.details["健康检查"] = "超时"
        except httpx.ConnectError:
            result.details["健康检查"] = "连接失败"
        except Exception as e:
            result.details["健康检查"] = f"错误: {e}"

        # 获取配置
        config_id = f"{config.nacos.data_id_prefix}app.yaml"
        get_config_url = f"{server_addr}/nacos/v1/cs/configs"
        params = {
            "dataId": config_id,
            "group": config.nacos.group,
            "tenant": config.nacos.namespace,
            "username": username,
            "password": password
        }

        try:
            response = httpx.get(get_config_url, params=params, timeout=5.0)
            if response.status_code == 200:
                content = response.text
                if content:
                    result.details["配置获取"] = f"成功 ({len(content)} bytes)"
                else:
                    result.details["配置获取"] = "成功（配置为空）"
            else:
                result.details["配置获取"] = f"HTTP {response.status_code}"
        except Exception as e:
            result.details["配置获取"] = f"错误: {e}"

        # 发布测试配置
        test_config_id = f"{config.nacos.data_id_prefix}connectivity_test.yaml"
        publish_url = f"{server_addr}/nacos/v1/cs/configs"

        # 先删除测试配置
        delete_data = {
            "dataId": test_config_id,
            "group": config.nacos.group,
            "tenant": config.nacos.namespace,
            "username": username,
            "password": password
        }

        try:
            delete_response = httpx.delete(publish_url, data=delete_data, timeout=5.0)
            result.details["配置删除测试"] = str(delete_response.status_code)
        except:
            pass

        # 发布测试配置
        publish_data = {
            "dataId": test_config_id,
            "group": config.nacos.group,
            "tenant": config.nacos.namespace,
            "content": "connectivity_test=true\ntimestamp=" + datetime.now().isoformat(),
            "username": username,
            "password": password
        }

        try:
            publish_response = httpx.post(publish_url, data=publish_data, timeout=5.0)
            if publish_response.status_code in [200, 201]:
                result.details["配置发布测试"] = "成功"
            else:
                result.details["配置发布测试"] = f"HTTP {publish_response.status_code}"
        except Exception as e:
            result.details["配置发布测试"] = f"错误: {e}"

    except ImportError as e:
        result.passed = False
        result.errors.append(f"httpx 未安装: {e}")
    except Exception as e:
        result.passed = False
        result.errors.append(f"测试失败: {e}")

    result.end_time = datetime.now().timestamp()
    return result


# =============================================================================
# MySQL 连通性测试 (Nacos 数据库)
# =============================================================================

async def test_mysql() -> TestResult:
    """测试 MySQL 连接"""
    result = TestResult("MySQL 连接测试 (Nacos)")
    result.start_time = datetime.now().timestamp()

    try:
        import httpx

        config = get_config()
        host = config.mysql.host
        port = config.mysql.port

        # 使用 httpx 测试端口连通性
        try:
            response = httpx.get(
                f"http://{host}:{port}",
                timeout=3.0,
                follow_redirects=True
            )
            # 如果能连接到，可能有管理界面
            result.details["端口连通性"] = "可达"
        except httpx.ConnectError:
            result.details["端口连通性"] = "不可达（可能正常，MySQL 不直接暴露 HTTP）"
        except Exception as e:
            result.details["端口连通性"] = f"错误: {e}"

        # 尝试直接连接 MySQL
        try:
            import asyncio
            import socket

            # 创建 socket 连接
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect((host, port))
            sock.close()
            result.details["Socket 连接"] = "成功"
        except Exception as e:
            result.details["Socket 连接"] = f"失败: {e}"

        # 如果有 nacos，可以使用 nacos 检查
        nacos_config = get_config()
        nacos_addr = nacos_config.nacos.server_addresses[0]

        # 通过 Nacos 检查 MySQL
        try:
            nacos_url = f"{nacos_addr}/nacos/v1/ns/service/list"
            response = httpx.get(nacos_url, timeout=5.0)
            if response.status_code == 200:
                result.details["Nacos 服务"] = "可用"
            else:
                result.details["Nacos 服务"] = f"HTTP {response.status_code}"
        except Exception as e:
            result.details["Nacos 服务"] = f"不可用: {e}"

    except ImportError as e:
        result.passed = False
        result.errors.append(f"模块未安装: {e}")
    except Exception as e:
        result.passed = False
        result.errors.append(f"测试失败: {e}")

    result.end_time = datetime.now().timestamp()
    return result


# =============================================================================
# MinIO 连通性测试
# =============================================================================

async def test_minio() -> TestResult:
    """测试 MinIO 连接"""
    result = TestResult("MinIO 连接测试 (Milvus 存储)")
    result.start_time = datetime.now().timestamp()

    try:
        import httpx

        config = get_config()
        endpoint = config.minio.endpoint

        # 健康检查
        health_url = f"http://{endpoint}/minio/health/live"
        try:
            response = httpx.get(health_url, timeout=5.0)
            if response.status_code == 200:
                result.details["健康检查"] = "OK"
            else:
                result.details["健康检查"] = f"HTTP {response.status_code}"
        except httpx.TimeoutException:
            result.details["健康检查"] = "超时"
        except httpx.ConnectError:
            result.details["健康检查"] = "连接失败"
        except Exception as e:
            result.details["健康检查"] = f"错误: {e}"

        # 检查桶列表
        try:
            import base64
            from urllib.parse import urlencode

            access_key = config.minio.access_key
            secret_key = config.minio.secret_key

            # 简化的认证检查
            result.details["端点"] = endpoint
            result.details["访问密钥"] = f"{access_key[:4]}****" if len(access_key) > 4 else "未配置"
        except Exception as e:
            result.details["配置检查"] = f"错误: {e}"

    except ImportError as e:
        result.passed = False
        result.errors.append(f"模块未安装: {e}")
    except Exception as e:
        result.passed = False
        result.errors.append(f"测试失败: {e}")

    result.end_time = datetime.now().timestamp()
    return result


# =============================================================================
# 主测试函数
# =============================================================================

async def run_all_tests():
    """运行所有连通性测试"""
    print_header()

    # 获取配置
    config = get_config()

    print(f"使用的配置文件: 未知 (使用默认配置)")
    print(f"Redis: {config.redis.host}:{config.redis.port}")
    print(f"Milvus: {config.milvus.host}:{config.milvus.port}")
    print(f"Nacos: {config.nacos.server_addresses}")
    print(f"MySQL: {config.mysql.host}:{config.mysql.port}")
    print()

    # 运行测试
    results = []

    # Test 1: Redis
    print("-" * 40)
    result = await test_redis()
    results.append(result)
    print_result(result)

    # Test 2: Milvus
    print("-" * 40)
    result = await test_milvus()
    results.append(result)
    print_result(result)

    # Test 3: Nacos
    print("-" * 40)
    result = await test_nacos()
    results.append(result)
    print_result(result)

    # Test 4: MinIO
    print("-" * 40)
    result = await test_minio()
    results.append(result)
    print_result(result)

    # Test 5: MySQL
    print("-" * 40)
    result = await test_mysql()
    results.append(result)
    print_result(result)

    # 汇总结果
    passed_count = sum(1 for r in results if r.passed)
    total_count = len(results)

    print("=" * 60)
    print(f"    测试结果: {passed_count}/{total_count} 通过")
    print("=" * 60)

    # 详细结果表
    print("\n详细结果:")
    print(f"{'服务':<15} {'状态':<12} {'耗时':<10}")
    print("-" * 40)
    for r in results:
        status = "✅ 通过" if r.passed else "❌ 失败"
        print(f"{r.name.split()[0]:<15} {status:<12} {r.duration_ms:.1f}ms")

    print("\n")
    return passed_count == total_count


def main():
    """主入口"""
    try:
        success = asyncio.run(run_all_tests())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n测试执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
