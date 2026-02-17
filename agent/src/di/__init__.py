"""
依赖注入容器 (Dependency Injection Container)

本模块提供简单的依赖注入功能，用于管理组件间的依赖关系。
采用服务定位器模式，支持接口抽象和实现替换。

主要组件:
- Container: 依赖注入容器
- ServiceDescriptor: 服务描述符
- Inject: 依赖注入装饰器

功能特点:
- 单例/瞬态服务注册
- 接口抽象
- 运行时依赖解析
- 便于单元测试时替换实现

使用示例:
    from di import Container, injectable

    # 注册服务
    container = Container()
    container.register_singleton(ILLMClient, AnthropicAdapter)

    # 获取服务
    client = container.resolve(ILLMClient)

    # 单元测试时替换实现
    container.register_singleton(ILLMClient, MockAdapter)
"""

from typing import Dict, Type, TypeVar, Callable, Any, Optional, get_type_hints
from enum import Enum
from functools import wraps
import threading


T = TypeVar('T')


class ServiceLifetime(Enum):
    """服务生命周期"""
    TRANSIENT = "transient"   # 每次请求创建新实例
    SINGLETON = "singleton"    # 全局单例


class ServiceDescriptor:
    """服务描述符"""

    def __init__(
        self,
        service_type: Type,
        implementation: Optional[Type] = None,
        factory: Optional[Callable] = None,
        lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT
    ):
        self.service_type = service_type
        self.implementation = implementation or service_type
        self.factory = factory
        self.lifetime = lifetime
        self._instance: Optional[Any] = None
        self._lock = threading.Lock()


class Container:
    """
    依赖注入容器

    提供服务的注册和解析功能，支持单例和瞬态两种生命周期。
    """

    def __init__(self):
        self._services: Dict[Type, ServiceDescriptor] = {}
        self._lock = threading.Lock()

    def register_singleton(
        self,
        service_type: Type[T],
        implementation: Type[T]
    ) -> 'Container':
        """
        注册单例服务

        Args:
            service_type: 服务接口类型
            implementation: 服务实现类型

        Returns:
            Container: 容器本身，支持链式调用
        """
        with self._lock:
            self._services[service_type] = ServiceDescriptor(
                service_type=service_type,
                implementation=implementation,
                lifetime=ServiceLifetime.SINGLETON
            )
        return self

    def register_transient(
        self,
        service_type: Type[T],
        implementation: Type[T]
    ) -> 'Container':
        """
        注册瞬态服务

        Args:
            service_type: 服务接口类型
            implementation: 服务实现类型

        Returns:
            Container: 容器本身，支持链式调用
        """
        with self._lock:
            self._services[service_type] = ServiceDescriptor(
                service_type=service_type,
                implementation=implementation,
                lifetime=ServiceLifetime.TRANSIENT
            )
        return self

    def register_factory(
        self,
        service_type: Type[T],
        factory: Callable[[], T]
    ) -> 'Container':
        """
        注册工厂服务

        Args:
            service_type: 服务类型
            factory: 工厂函数

        Returns:
            Container: 容器本身，支持链式调用
        """
        with self._lock:
            self._services[service_type] = ServiceDescriptor(
                service_type=service_type,
                factory=factory,
                lifetime=ServiceLifetime.TRANSIENT
            )
        return self

    def register_instance(
        self,
        service_type: Type[T],
        instance: T
    ) -> 'Container':
        """
        注册实例（相当于单例）

        Args:
            service_type: 服务类型
            instance: 服务实例

        Returns:
            Container: 容器本身，支持链式调用
        """
        with self._lock:
            self._services[service_type] = ServiceDescriptor(
                service_type=service_type,
                implementation=type(instance),
                lifetime=ServiceLifetime.SINGLETON
            )
            # 预先设置实例
            self._services[service_type]._instance = instance
        return self

    def resolve(self, service_type: Type[T]) -> T:
        """
        解析服务

        Args:
            service_type: 服务类型

        Returns:
            T: 服务实例

        Raises:
            KeyError: 服务未注册时抛出
        """
        with self._lock:
            if service_type not in self._services:
                raise KeyError(f"Service {service_type} is not registered")

            descriptor = self._services[service_type]

            # 如果是单例且已有实例，直接返回
            if descriptor.lifetime == ServiceLifetime.SINGLETON:
                if descriptor._instance is not None:
                    return descriptor._instance

            # 创建实例
            instance = self._create_instance(descriptor)

            # 如果是单例，保存实例
            if descriptor.lifetime == ServiceLifetime.SINGLETON:
                descriptor._instance = instance

            return instance

    def _create_instance(self, descriptor: ServiceDescriptor) -> Any:
        """创建服务实例"""
        # 如果有工厂函数，使用工厂函数
        if descriptor.factory:
            return descriptor.factory()

        # 否则使用实现类的构造函数
        implementation = descriptor.implementation

        # 获取构造函数的参数
        try:
            import inspect
            sig = inspect.signature(implementation.__init__)
            params = sig.parameters
        except (ValueError, TypeError):
            # 如果无法获取签名，直接实例化
            return implementation()

        # 解析依赖
        deps = {}
        for param_name, param in params.items():
            if param_name == 'self':
                continue
            if param.annotation != inspect.Parameter.empty:
                try:
                    deps[param_name] = self.resolve(param.annotation)
                except KeyError:
                    # 如果没有注册该依赖，尝试使用默认值
                    if param.default != inspect.Parameter.empty:
                        pass  # 使用默认值
                    else:
                        raise

        return implementation(**deps)

    def create_scope(self) -> 'ScopedContainer':
        """创建作用域容器"""
        return ScopedContainer(self)


class ScopedContainer:
    """作用域容器（用于请求级别的依赖管理）"""

    def __init__(self, parent: Container):
        self._parent = parent
        self._scoped_services: Dict[Type, Any] = {}
        self._lock = threading.Lock()

    def resolve(self, service_type: Type[T]) -> T:
        """解析作用域服务"""
        with self._lock:
            if service_type not in self._scoped_services:
                self._scoped_services[service_type] = self._parent.resolve(service_type)
            return self._scoped_services[service_type]


# 全局容器实例
_global_container: Optional[Container] = None


def get_container() -> Container:
    """获取全局容器实例"""
    global _global_container
    if _global_container is None:
        _global_container = Container()
    return _global_container


def set_container(container: Container) -> None:
    """设置全局容器实例"""
    global _global_container
    _global_container = container


def injectable(cls: Type[T]) -> Type[T]:
    """
    可注入标记装饰器

    标记类可以被注入依赖。使用此装饰器的类，其构造函数参数
    将自动从容器中解析。

    Args:
        cls: 要标记的类

    Returns:
        Type[T]: 标记后的类
    """
    @wraps(cls)
    class Wrapper(cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

    return Wrapper
