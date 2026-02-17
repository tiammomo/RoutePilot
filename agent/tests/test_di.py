#!/usr/bin/env python3
"""
================================================================================
依赖注入容器单元测试

测试 DI 容器的核心功能：
- 服务注册（单例/瞬态/工厂）
- 服务解析
- 作用域容器

运行方式:
    PYTHONPATH=agent/src python -m pytest agent/tests/test_di.py -v

================================================================================
"""

import sys
import pytest
from pathlib import Path

# 确保 agent/src 在路径中
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "agent" / "src"))

from di import Container, ServiceLifetime, get_container, ServiceDescriptor


# =============================================================================
# 测试夹具
# =============================================================================

@pytest.fixture
def container():
    """创建新的容器实例"""
    return Container()


# =============================================================================
# 测试用例
# =============================================================================

class TestContainer:
    """Container 测试类"""

    def test_register_singleton(self, container):
        """测试注册单例服务"""

        class TestService:
            def __init__(self):
                self.value = "test"

        container.register_singleton(TestService, TestService)
        instance1 = container.resolve(TestService)
        instance2 = container.resolve(TestService)

        # 单例应该返回同一实例
        assert instance1 is instance2
        assert instance1.value == "test"

    def test_register_transient(self, container):
        """测试注册瞬态服务"""

        class TestService:
            instance_id = 0

            def __init__(self):
                TestService.instance_id += 1
                self.id = TestService.instance_id

        container.register_transient(TestService, TestService)
        instance1 = container.resolve(TestService)
        instance2 = container.resolve(TestService)

        # 瞬态应该返回不同实例
        assert instance1 is not instance2
        assert instance1.id != instance2.id

    def test_register_factory(self, container):
        """测试注册工厂服务"""

        class TestService:
            def __init__(self, value: str = "default"):
                self.value = value

        container.register_factory(TestService, lambda: TestService("factory"))
        instance = container.resolve(TestService)

        assert instance.value == "factory"

    def test_register_instance(self, container):
        """测试注册实例"""

        class TestService:
            def __init__(self):
                self.value = "instance"

        instance = TestService()
        container.register_instance(TestService, instance)
        resolved = container.resolve(TestService)

        assert resolved is instance

    def test_resolve_unregistered_service(self, container):
        """测试解析未注册服务"""

        class UnknownService:
            pass

        with pytest.raises(KeyError):
            container.resolve(UnknownService)


class TestServiceLifetime:
    """ServiceLifetime 测试类"""

    def test_singleton_lifetime(self):
        """测试单例生命周期"""
        desc = ServiceDescriptor(
            service_type=object,
            implementation=object,
            lifetime=ServiceLifetime.SINGLETON
        )
        assert desc.lifetime == ServiceLifetime.SINGLETON

    def test_transient_lifetime(self):
        """测试瞬态生命周期"""
        desc = ServiceDescriptor(
            service_type=object,
            implementation=object,
            lifetime=ServiceLifetime.TRANSIENT
        )
        assert desc.lifetime == ServiceLifetime.TRANSIENT


class TestScopedContainer:
    """ScopedContainer 测试类"""

    def test_create_scope(self, container):
        """测试创建作用域"""
        scope = container.create_scope()
        assert scope is not None

    def test_scope_resolve(self, container):
        """测试作用域解析"""

        class TestService:
            def __init__(self):
                self.value = "scoped"

        container.register_singleton(TestService, TestService)
        scope = container.create_scope()

        instance = scope.resolve(TestService)
        assert instance.value == "scoped"


# =============================================================================
# 主程序入口
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
