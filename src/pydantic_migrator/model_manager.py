"""ModelManager class."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Generic, Self, cast, get_args

from pydantic import BaseModel
from pydantic.json_schema import GenerateJsonSchema

from ._migration_manager import MigrationManager
from ._registry import Registry
from ._schema_manager import SchemaManager
from ._type_inspector import TypeInspector
from .exceptions import MigrationError, ModelNotFoundError
from .migration_hooks import MigrationHook
from .migration_testing import (
    MigrationTestCase,
    MigrationTestCases,
    MigrationTestResult,
    MigrationTestResults,
)
from .model_diff import ModelDiff
from .model_version import ModelVersion
from .schema_config import SchemaConfig
from .types import (
    DecoratedBaseModel,
    JsonSchema,
    JsonSchemaGenerator,
    MigrationFunc,
    ModelData,
    NestedModelInfo,
    SchemaTransformer,
    T,
    V,
)
from .versioned_model import VersionedModel


class RegisterProxy(Generic[T]):
    """Subscriptable proxy for typed model registration.

    Enables ``@manager.register[UserV2]("User", "2.0.0")`` syntax so type checkers
    can infer the versioned model type ``V`` at registration time.
    """

    def __init__(self, manager: ModelManager[T]) -> None:
        self._manager = manager

    def __getitem__(
        self, model_type: type[V]
    ) -> Callable[
        [str, str | ModelVersion],
        Callable[[type[V]], type[V]],
    ]:
        _ = model_type

        def with_name_and_version(
            name: str,
            version: str | ModelVersion,
            enable_ref: bool = False,
            backward_compatible: bool = False,
        ) -> Callable[[type[V]], type[V]]:
            def decorator(cls: type[V]) -> type[V]:
                self._manager._registry.register(
                    name, version, enable_ref, backward_compatible
                )(cls)
                self._manager._store_versioned_model(name, version, cls)
                return cls

            return decorator

        return with_name_and_version


class ModelManager(Generic[T]):
    """High-level interface for versioned model management and schema generation.

    ModelManager provides a unified API for managing schema evolution across different
    versions of Pydantic models. It handles model registration, automatic migration
    between versions, customizable schema generation, and batch processing operations.

    Example:
        **Basic Usage**:

        ```python
        from pydantic_migrator import ModelManager, ModelData

        manager = ModelManager()

        # Register model versions
        @manager.model("User", "1.0.0")
        class UserV1(BaseModel):
            name: str

        @manager.model("User", "2.0.0")
        class UserV2(BaseModel):
            name: str
            email: str

        # Define migration between versions
        @manager.migration("User", "1.0.0", "2.0.0")
        def migrate(data: ModelData) -> ModelData:
            return {**data, "email": "unknown@example.com"}

        # Migrate legacy data
        old_data = {"name": "Alice"}
        user = manager.migrate(old_data, "User", "1.0.0", "2.0.0")
        # Result: UserV2(name="Alice", email="unknown@example.com")
        ```

        **Custom Schema Generation**:

        ```python
        from pydantic.json_schema import GenerateJsonSchema

        class CustomSchemaGenerator(GenerateJsonSchema):
            '''Add custom metadata to all schemas.'''
            def generate(
                self,
                schema: Mapping[str, Any],
                mode: JsonSchemaMode = "validation"
            ) -> JsonSchema:
                json_schema = super().generate(schema, mode=mode)
                json_schema["x-company"] = "Acme"
                json_schema["$schema"] = self.schema_dialect
                return json_schema

        # Set at manager level (applies to all schemas)
        manager = ModelManager(
            default_schema_config=SchemaConfig(
                schema_generator=CustomSchemaGenerator,
                mode="validation",
                by_alias=True
            )
        )

        @manager.model("User", "1.0.0")
        class User(BaseModel):
            name: str = Field(title="Full Name")
            email: str

        # Get schema with default config
        schema = manager.get_schema("User", "1.0.0")
        # Will include x-company: "Acme"
        ```

        **Advanced Features**:

        ```python
        # Batch migration with parallel processing
        users = manager.migrate_batch(
            legacy_users, "User", "1.0.0", "2.0.0",
            parallel=True, max_workers=4
        )

        # Stream large datasets efficiently
        for user in manager.migrate_batch_streaming(
            large_dataset, "User", "1.0.0", "2.0.0"
         ):
            save_to_database(user)

        # Compare versions and export schemas
        diff = manager.diff("User", "1.0.0", "2.0.0")
        print(diff.to_markdown())
        manager.dump_schemas("schemas/", separate_definitions=True)

        # Test migrations with validation
        results = manager.test_migration(
            "User", "1.0.0", "2.0.0",
            test_cases=[
                (
                     {"name": "Alice"},
                     {"name": "Alice", "email": "unknown@example.com"}
                )
            ]
        )
        results.assert_all_passed()
        ```

        **Typed registration** (static type inference):

        ``get()`` and ``get_latest()`` return a :class:`VersionedModel` container.
        Use ``.cls`` for the model class or ``.load(data)`` for a validated instance.

        ```python
        from typing import Annotated
        from pydantic import BaseModel, Field
        from pydantic_migrator import ModelManager, VersionedModel

        manager: ModelManager["UserModel"] = ModelManager()

        @manager.register[UserV1]("User", "1.0.0")
        class UserV1(BaseModel):
            schema_version: str = "1.0.0"
            name: str

        @manager.register[UserV2]("User", "2.0.0")
        class UserV2(BaseModel):
            schema_version: str = "2.0.0"
            name: str
            email: str

        UserModel = Annotated[
            UserV1 | UserV2,
            Field(discriminator="schema_version"),
        ]

        user_v2: VersionedModel[UserModel, UserV2] = manager.get("User", "2.0.0")
        user: UserV2 = user_v2.load(
            {"schema_version": "2.0.0", "name": "Alice", "email": "a@b.com"}
        )
        ```

        **Schema Transformers**:

        ```python
        manager = ModelManager()

        @manager.model("Product", "1.0.0")
        class Product(BaseModel):
            name: str
            price: float

        # Add transformer for specific model
        @manager.schema_transformer("Product", "1.0.0")
        def add_examples(schema: JsonSchema) -> JsonSchema:
            schema["examples"] = [{"name": "Widget", "price": 9.99}]
            return schema

        schema = manager.get_schema("Product", "1.0.0")
        # Will include examples
        ```
    """

    def __init__(self: Self, default_schema_config: SchemaConfig | None = None) -> None:
        """Initialize the versioned model manager.

        Args:
            default_schema_config: Default configuration for schema generation
                applied to all schema operations unless overridden.
        """
        self._registry = Registry()
        self._migration_manager = MigrationManager(self._registry)
        self._schema_manager = SchemaManager(
            self._registry, default_config=default_schema_config
        )
        self._version_map: dict[tuple[str, ModelVersion], VersionedModel] = {}

    @property
    def container_type(self) -> type[T] | None:
        orig = getattr(self, "__orig_class__", None)
        return get_args(orig)[0] if orig else None

    @property
    def register(self) -> RegisterProxy[T]:
        return RegisterProxy(self)

    def _store_versioned_model(
        self: Self,
        name: str,
        version: str | ModelVersion,
        cls: type[BaseModel],
    ) -> VersionedModel[T, BaseModel]:
        ver = ModelVersion.parse(version) if isinstance(version, str) else version
        versioned = VersionedModel(self, name, ver, cls)
        self._version_map[(name, ver)] = versioned
        return versioned

    def _get_versioned_model(
        self: Self,
        name: str,
        version: str | ModelVersion,
    ) -> VersionedModel[T, BaseModel]:
        ver = ModelVersion.parse(version) if isinstance(version, str) else version
        key = (name, ver)
        if key not in self._version_map:
            cls = self._registry.get_model(name, version)
            self._store_versioned_model(name, ver, cls)
        return self._version_map[key]

    def model(
        self: Self,
        name: str,
        version: str | ModelVersion,
        enable_ref: bool = False,
        backward_compatible: bool = False,
    ) -> Callable[[type[DecoratedBaseModel]], type[DecoratedBaseModel]]:
        """Register a versioned model.

        Args:
            name: Name of the model.
            version: Semantic version.
            enable_ref: If True, this model can be referenced via $ref in separate
                schema files. If False, it will always be inlined.
            backward_compatible: If True, this model does not need a migration function
                to migrate to the next version. If a migration function is defined it
                will use it.

        Returns:
            Decorator function for model class.

        Example:
            ```python
            # Model that will be inlined (default)
            @manager.model("Address", "1.0.0")
            class AddressV1(BaseModel):
                street: str

            # Model that can be a separate schema with $ref
            @manager.model("City", "1.0.0", enable_ref=True)
            class CityV1(BaseModel):
                city: City
            ```
        """
        registry_decorator = self._registry.register(
            name, version, enable_ref, backward_compatible
        )

        def decorator(cls: type[DecoratedBaseModel]) -> type[DecoratedBaseModel]:
            registry_decorator(cls)
            self._store_versioned_model(name, version, cls)
            return cls

        return decorator

    def get(self: Self, name: str, version: str | ModelVersion) -> VersionedModel[T, V]:
        """Get a versioned model container by name and version.

        Args:
            name: Name of the model.
            version: Semantic version.

        Returns:
            VersionedModel container for the specified version.
        """
        return self._get_versioned_model(name, version)  # type: ignore[return-value]  # ty: ignore[invalid-return-type]

    def get_latest(self: Self, name: str) -> VersionedModel[T, V]:
        """Get the latest versioned model container by name.

        Args:
            name: Name of the model.

        Returns:
            VersionedModel container for the latest version.
        """
        latest_version = max(self._registry.get_versions(name))
        return self._get_versioned_model(name, latest_version)  # type: ignore[return-value]  # ty: ignore[invalid-return-type]

    def get_nested_models(
        self: Self,
        name: str,
        version: str | ModelVersion,
    ) -> list[NestedModelInfo]:
        """Get all nested models used by a model.

        Args:
            name: Name of the model.
            version: Semantic version.

        Returns:
            List of NestedModelInfo.
        """
        return self._schema_manager.get_nested_models(name, version)

    def list_models(self: Self) -> list[str]:
        """Get list of all registered models.

        Returns:
            List of model names.
        """
        return self._registry.list_models()

    def list_versions(self: Self, name: str) -> list[ModelVersion]:
        """Get all versions for a model.

        Args:
            name: Name of the model.

        Returns:
            Sorted list of versions.
        """
        return self._registry.get_versions(name)

    def migration(
        self: Self,
        name: str,
        from_version: str | ModelVersion,
        to_version: str | ModelVersion,
    ) -> Callable[[MigrationFunc], MigrationFunc]:
        """Register a migration function.

        Args:
            name: Name of the model.
            from_version: Source version.
            to_version: Target version.

        Returns:
            Decorator function for migration function.
        """
        return self._migration_manager.register_migration(
            name, from_version, to_version
        )

    def add_hook(self: Self, hook: MigrationHook) -> None:
        """Register a migration hook for observability/logging.

        Args:
            hook: Migration hook instance to register.

        Example:
            ```python
            from pydantic_migrator import MetricsHook, MigrationHook
            import logging

            # Use built-in metrics hook
            metrics = MetricsHook()
            manager.add_hook(metrics)

            # Add custom logging hook
            class LoggingHook(MigrationHook):
                def before_migrate(
                    self,
                    name: str,
                    from_version: ModelVersion,
                    to_version: ModelVersion,
                    data: Mapping[str, Any],
                ) -> None:
                    logging.info(f"Starting migration: {name}")
                    return data

            manager.add_hook(LoggingHook())
            ```
        """
        self._migration_manager.add_hook(hook)

    def remove_hook(self: Self, hook: MigrationHook) -> None:
        """Remove a previously registered hook.

        Args:
            hook: Migration hook instance to remove.
        """
        self._migration_manager.remove_hook(hook)

    def clear_hooks(self: Self) -> None:
        """Remove all registered hooks."""
        self._migration_manager.clear_hooks()

    def has_migration_path(
        self: Self,
        name: str,
        from_version: str | ModelVersion,
        to_version: str | ModelVersion,
    ) -> bool:
        """Check if a migration path exists between two versions.

        Args:
            name: Name of the model.
            from_version: Source version.
            to_version: Target version.

        Returns:
            True if a migration path exists, False otherwise.

        Example:
            ```python
            if manager.has_migration_path("User", "1.0.0", "3.0.0"):
                users = manager.migrate_batch(old_users, "User", "1.0.0", "3.0.0")
            else:
                logger.error("Cannot migrate users to v3.0.0")
            ```
        """
        from_ver = (
            ModelVersion.parse(from_version)
            if isinstance(from_version, str)
            else from_version
        )
        to_ver = (
            ModelVersion.parse(to_version)
            if isinstance(to_version, str)
            else to_version
        )
        try:
            self._migration_manager.validate_migration_path(name, from_ver, to_ver)
            return True
        except (KeyError, ModelNotFoundError, MigrationError):
            return False

    def _prepare_data_for_validation(
        self: Self,
        migrated_data: ModelData,
        target_model: type[BaseModel],
    ) -> Any:
        """Prepare migrated data for Pydantic validation.

        For RootModels, unwrap the 'root' key since Pydantic expects the raw value.
        For regular BaseModels, use the data as-is.

        Args:
            migrated_data: The migrated data dictionary.
            target_model: The target model class.

        Returns:
            Data prepared for validation (dict for BaseModel, unwrapped for RootModel).
        """
        if TypeInspector.is_root_model(target_model):
            return migrated_data.get("root")
        return migrated_data

    def validate_data(
        self: Self,
        data: ModelData,
        name: str,
        version: str | ModelVersion,
    ) -> bool:
        """Check if data is valid for a specific model version.

        Validates whether the provided data conforms to the schema of the specified
        model version without raising an exception.

        Args:
            data: Data dictionary to validate.
            name: Name of the model.
            version: Semantic version to validate against.

        Returns:
            True if data is valid for the model version, False otherwise.

        Example:
            ```python
            data = {"name": "Alice"}
            is_valid = manager.validate_data(data, "User", "1.0.0")
            # Returns: True

            is_valid = manager.validate_data(data, "User", "2.0.0")
            # Returns: False, missing required field 'email'
            ```
        """
        try:
            versioned: VersionedModel[T, BaseModel] = self.get(name, version)
            versioned.cls.model_validate(data)
            return True
        except Exception:
            return False

    def migrate(
        self: Self,
        data: ModelData,
        name: str,
        from_version: str | ModelVersion,
        to_version: str | ModelVersion,
    ) -> BaseModel:
        """Migrate data between versions.

        Args:
            data: Data dictionary to migrate.
            name: Name of the model.
            from_version: Source version.
            to_version: Target version.

        Returns:
            Migrated BaseModel.
        """
        migrated_data = self.migrate_data(data, name, from_version, to_version)
        versioned: VersionedModel[T, BaseModel] = self.get(name, to_version)
        validation_data = self._prepare_data_for_validation(
            migrated_data, versioned.cls
        )
        return versioned.cls.model_validate(validation_data)

    def migrate_as(
        self: Self,
        data: ModelData,
        name: str,
        from_version: str | ModelVersion,
        to_version: str | ModelVersion,
        target_type: type[DecoratedBaseModel],
    ) -> DecoratedBaseModel:
        """Migrate data between versions with type safety.

        This is a type-safe variant of migrate() that returns a specific model type when
        you provide the target type explicitly.

        Args:
            data: Data dictionary to migrate.
            name: Name of the model.
            from_version: Source version.
            to_version: Target version.
            target_type: The expected model class type.

        Returns:
            Migrated model instance of the specified type.

        Example:
            ```python
            old_data = {"name": "Alice"}
            user: UserV2 = manager.migrate_as(
                old_data, "User", "1.0.0", "2.0.0", UserV2
            )
            # Type checker knows user is UserV2, not just BaseModel
            ```
        """
        migrated_data = self.migrate_data(data, name, from_version, to_version)
        validation_data = self._prepare_data_for_validation(migrated_data, target_type)
        return target_type.model_validate(validation_data)

    def migrate_data(
        self: Self,
        data: ModelData,
        name: str,
        from_version: str | ModelVersion,
        to_version: str | ModelVersion,
    ) -> ModelData:
        """Migrate data between versions.

        Args:
            data: Data dictionary to migrate.
            name: Name of the model.
            from_version: Source version.
            to_version: Target version.

        Returns:
            Raw migrated dictionary.
        """
        return self._migration_manager.migrate(data, name, from_version, to_version)

    def migrate_batch(  # noqa: PLR0913
        self: Self,
        data_list: Iterable[ModelData],
        name: str,
        from_version: str | ModelVersion,
        to_version: str | ModelVersion,
        parallel: bool = False,
        max_workers: int | None = None,
        use_processes: bool = False,
    ) -> list[BaseModel]:
        """Migrate multiple data items between versions.

        Args:
            data_list: Iterable of data dictionaries to migrate.
            name: Name of the model.
            from_version: Source version.
            to_version: Target version.
            parallel: If True, use parallel processing.
            max_workers: Maximum number of workers for parallel processing.
            use_processes: If True, use ProcessPoolExecutor instead of
                ThreadPoolExecutor.

        Returns:
            List of migrated BaseModel instances.
        """
        data_list = list(data_list)

        if not data_list:
            return []

        if not parallel:
            return [
                self.migrate(item, name, from_version, to_version) for item in data_list
            ]

        executor_class = ProcessPoolExecutor if use_processes else ThreadPoolExecutor
        with executor_class(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self.migrate, item, name, from_version, to_version)
                for item in data_list
            ]
            return [future.result() for future in futures]

    def migrate_batch_as(  # noqa: PLR0913
        self: Self,
        data_list: Iterable[ModelData],
        name: str,
        from_version: str | ModelVersion,
        to_version: str | ModelVersion,
        target_type: type[DecoratedBaseModel],
        parallel: bool = False,
        max_workers: int | None = None,
        use_processes: bool = False,
    ) -> list[DecoratedBaseModel]:
        """Migrate multiple data items between versions with type safety.

        This is a type-safe variant of migrate_batch() that returns a specific model
        type when you provide the target type explicitly.

        Args:
            data_list: Iterable of data dictionaries to migrate.
            name: Name of the model.
            from_version: Source version.
            to_version: Target version.
            target_type: The expected model class type.
            parallel: If True, use parallel processing.
            max_workers: Maximum number of workers for parallel processing.
            use_processes: If True, use ProcessPoolExecutor instead of
                ThreadPoolExecutor.

        Returns:
            List of migrated model instances of the specified type.

        Example:
            ```python
            old_users = [{"name": "Alice"}, {"name": "Bob"}]
            users: list[UserV2] = manager.migrate_batch_as(
                old_users, "User", "1.0.0", "2.0.0", UserV2,
                parallel=True, max_workers=4
            )
            ```
        """
        data_list = list(data_list)

        if not data_list:
            return []

        if not parallel:
            return [
                self.migrate_as(item, name, from_version, to_version, target_type)
                for item in data_list
            ]

        executor_class = ProcessPoolExecutor if use_processes else ThreadPoolExecutor
        with executor_class(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    self.migrate_as, item, name, from_version, to_version, target_type
                )
                for item in data_list
            ]
            return [future.result() for future in futures]  # ty:ignore[invalid-return-type]

    def migrate_batch_data(  # noqa: PLR0913
        self: Self,
        data_list: Iterable[ModelData],
        name: str,
        from_version: str | ModelVersion,
        to_version: str | ModelVersion,
        parallel: bool = False,
        max_workers: int | None = None,
        use_processes: bool = False,
    ) -> list[ModelData]:
        """Migrate multiple data items between versions, returning raw dictionaries.

        Args:
            data_list: Iterable of data dictionaries to migrate.
            name: Name of the model.
            from_version: Source version.
            to_version: Target version.
            parallel: If True, use parallel processing.
            max_workers: Maximum number of workers for parallel processing.
            use_processes: If True, use ProcessPoolExecutor.

        Returns:
            List of raw migrated dictionaries.
        """
        data_list = list(data_list)

        if not data_list:
            return []

        if not parallel:
            return [
                self.migrate_data(item, name, from_version, to_version)
                for item in data_list
            ]

        executor_class = ProcessPoolExecutor if use_processes else ThreadPoolExecutor
        with executor_class(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self.migrate_data, item, name, from_version, to_version)
                for item in data_list
            ]
            return [future.result() for future in futures]

    def migrate_batch_streaming(
        self: Self,
        data_list: Iterable[ModelData],
        name: str,
        from_version: str | ModelVersion,
        to_version: str | ModelVersion,
        chunk_size: int = 100,
    ) -> Iterable[BaseModel]:
        """Migrate data in chunks, yielding results as they complete.

        Args:
            data_list: Iterable of data dictionaries to migrate.
            name: Name of the model.
            from_version: Source version.
            to_version: Target version.
            chunk_size: Number of items to process in each chunk.

        Yields:
            Migrated BaseModel instances.
        """
        chunk = []

        for item in data_list:
            chunk.append(item)

            if len(chunk) >= chunk_size:
                yield from self.migrate_batch(chunk, name, from_version, to_version)
                chunk = []

        if chunk:
            yield from self.migrate_batch(chunk, name, from_version, to_version)

    def migrate_batch_streaming_as(  # noqa: PLR0913
        self: Self,
        data_list: Iterable[ModelData],
        name: str,
        from_version: str | ModelVersion,
        to_version: str | ModelVersion,
        target_type: type[DecoratedBaseModel],
        chunk_size: int = 100,
    ) -> Iterable[DecoratedBaseModel]:
        """Migrate data in chunks with type safety, yielding results as they complete.

        This is a type-safe variant of migrate_batch_streaming() that returns a specific
        model type when you provide the target type explicitly.

        Args:
            data_list: Iterable of data dictionaries to migrate.
            name: Name of the model.
            from_version: Source version.
            to_version: Target version.
            target_type: The expected model class type.
            chunk_size: Number of items to process in each chunk.

        Yields:
            Migrated model instances of the specified type.

        Example:
            ```python
            for user in manager.migrate_batch_streaming_as(
                large_dataset, "User", "1.0.0", "2.0.0", UserV2
            ):
                save_to_database(user)  # user is typed as UserV2
            ```
        """
        chunk = []

        for item in data_list:
            chunk.append(item)

            if len(chunk) >= chunk_size:
                yield from self.migrate_batch_as(
                    chunk, name, from_version, to_version, target_type
                )
                chunk = []

        if chunk:
            yield from self.migrate_batch_as(
                chunk, name, from_version, to_version, target_type
            )

    def migrate_batch_data_streaming(
        self: Self,
        data_list: Iterable[ModelData],
        name: str,
        from_version: str | ModelVersion,
        to_version: str | ModelVersion,
        chunk_size: int = 100,
    ) -> Iterable[ModelData]:
        """Migrate data in chunks, yielding raw dictionaries as they complete.

        Args:
            data_list: Iterable of data dictionaries to migrate.
            name: Name of the model.
            from_version: Source version.
            to_version: Target version.
            chunk_size: Number of items to process in each chunk.

        Yields:
            Raw migrated dictionaries.
        """
        chunk = []

        for item in data_list:
            chunk.append(item)

            if len(chunk) >= chunk_size:
                yield from self.migrate_batch_data(
                    chunk, name, from_version, to_version
                )
                chunk = []

        if chunk:
            yield from self.migrate_batch_data(chunk, name, from_version, to_version)

    def test_migration(
        self: Self,
        name: str,
        from_version: str | ModelVersion,
        to_version: str | ModelVersion,
        test_cases: MigrationTestCases,
    ) -> MigrationTestResults:
        """Test a migration with multiple test cases.

        Args:
            name: Name of the model.
            from_version: Source version to migrate from.
            to_version: Target version to migrate to.
            test_cases: List of test cases.

        Returns:
            MigrationTestResults containing individual results for each test case.
        """
        results = []

        for test_case_input in test_cases:
            if isinstance(test_case_input, tuple):
                test_case = MigrationTestCase(
                    source=cast(ModelData, test_case_input[0]),
                    target=test_case_input[1],  # ty:ignore[invalid-argument-type]
                )
            else:
                test_case = test_case_input

            try:
                actual = self.migrate_data(
                    test_case.source, name, from_version, to_version
                )

                if test_case.target is not None:
                    passed = actual == test_case.target
                    error = None if passed else "Output mismatch"
                else:
                    # Just verify it doesn't crash
                    passed = True
                    error = None

                results.append(
                    MigrationTestResult(
                        test_case=test_case, actual=actual, passed=passed, error=error
                    )
                )
            except Exception as e:
                results.append(
                    MigrationTestResult(
                        test_case=test_case, actual={}, passed=False, error=str(e)
                    )
                )

        return MigrationTestResults(results)

    def diff(
        self: Self,
        name: str,
        from_version: str | ModelVersion,
        to_version: str | ModelVersion,
    ) -> ModelDiff:
        """Get a detailed diff between two model versions.

        Args:
            name: Name of the model.
            from_version: Source version.
            to_version: Target version.

        Returns:
            ModelDiff with detailed change information.
        """
        from_ver_str = str(
            ModelVersion.parse(from_version)
            if isinstance(from_version, str)
            else from_version
        )
        to_ver_str = str(
            ModelVersion.parse(to_version)
            if isinstance(to_version, str)
            else to_version
        )

        from_versioned: VersionedModel[T, BaseModel] = self.get(name, from_version)
        to_versioned: VersionedModel[T, BaseModel] = self.get(name, to_version)

        return ModelDiff.from_models(
            name=name,
            from_model=from_versioned.cls,
            to_model=to_versioned.cls,
            from_version=from_ver_str,
            to_version=to_ver_str,
        )

    def set_default_schema_generator(
        self: Self, generator: JsonSchemaGenerator | type[GenerateJsonSchema]
    ) -> None:
        """Set the default schema generator for all schemas.

        This is a convenience method that updates the default schema configuration.

        Args:
            generator: Custom schema generator - either a callable or GenerateJsonSchema
                class.

        Example:
            **Class**:

            ```python
            from pydantic.json_schema import GenerateJsonSchema


            class MyGenerator(GenerateJsonSchema):
                def generate(
                    self,
                    schema: Mapping[str, Any],
                    mode: JsonSchemaMode = "validation"
                ) -> JsonSchema:
                    json_schema = super().generate(schema, mode=mode)
                    json_schema["x-custom"] = True
                    json_schema["$schema"] = self.schema_dialect
                    return json_schema

            manager = ModelManager()
            manager.set_default_schema_generator(MyGenerator)

            # All subsequent schema calls will use MyGenerator
            schema = manager.get_schema("User", "1.0.0")
            ```

            **Callable**:

            ```python
            def my_generator(model: type[BaseModel]) -> JsonSchema:
                schema = model.model_json_schema()
                schema["x-custom"] = True
                return schema

            manager = ModelManager()
            manager.set_default_schema_generator(my_generator)
            ```
        """
        self._schema_manager.set_default_schema_generator(generator)

    def schema_transformer(
        self: Self,
        name: str,
        version: str | ModelVersion,
    ) -> Callable[[SchemaTransformer], SchemaTransformer]:
        """Decorator to register a schema transformer for a model version.

        Transformers are simple functions that modify a schema after generation.
        They're useful for model-specific customizations that don't require deep
        integration with Pydantic's generation process.

        Args:
            name: Name of the model.
            version: Model version.

        Returns:
            Decorator function.

        Example:
            ```python
            @manager.schema_transformer("User", "1.0.0")
            def add_auth_metadata(schema: JsonSchema) -> JsonSchema:
                schema["x-requires-auth"] = True
                schema["x-auth-level"] = 'admin'
                return schema

            @manager.schema_transformer("Product", "2.0.0")
            def add_product_examples(schema: JsonSchema) -> JsonSchema:
                schema["examples"] = [
                    {"name": "Widget", "price": 9.99},
                    {"name": "Gadget", "price": 19.99}
                ]
                return schema
            ```
        """

        def decorator(func: SchemaTransformer) -> SchemaTransformer:
            self._schema_manager.register_transformer(name, version, func)
            return func

        return decorator

    def get_schema_transformers(
        self: Self,
        name: str,
        version: str | ModelVersion,
    ) -> list[SchemaTransformer]:
        """Get all transformers for a model version.

        Args:
            name: Name of the model.
            version: Model version.

        Returns:
            List of transformer functions.

        Example:
            ```python
            transformers = manager.get_schema_transformers("User", "1.0.0")
            print(f"Found {len(transformers)} transformers")
            ```
        """
        return self._schema_manager.get_transformers(name, version)

    def clear_schema_transformers(
        self: Self,
        name: str | None = None,
        version: str | ModelVersion | None = None,
    ) -> None:
        """Clear schema transformers.

        Args:
            name: Optional model name. If None, clears all.
            version: Optional version. If None, clears all versions of model.

        Example:
            ```python
            # Clear all transformers
            manager.clear_schema_transformers()

            # Clear User transformers
            manager.clear_schema_transformers("User")

            # Clear specific version
            manager.clear_schema_transformers("User", "1.0.0")
            ```
        """
        self._schema_manager.clear_transformers(name, version)

    def get_schema(
        self: Self,
        name: str,
        version: str | ModelVersion,
        config: SchemaConfig | None = None,
        **kwargs: Any,
    ) -> JsonSchema:
        """Get JSON schema for a specific version.

        Args:
            name: Name of the model.
            version: Semantic version.
            config: Optional schema configuration (overrides default).
            **kwargs: Additional schema generation arguments (e.g.,
                mode="serialization").

        Returns:
            JSON schema dictionary.

        Example:
            ```python
            # Use default config
            schema = manager.get_schema("User", "1.0.0")

            # Override with custom config
            config = SchemaConfig(mode="serialization")
            schema = manager.get_schema("User", "1.0.0", config=config)

            # Quick override with kwargs
            schema = manager.get_schema("User", "1.0.0", mode="serialization")
            ```
        """
        return self._schema_manager.get_schema(name, version, config=config, **kwargs)

    def dump_schemas(
        self: Self,
        output_dir: str | Path,
        indent: int = 2,
        separate_definitions: bool = False,
        ref_template: str | None = None,
        config: SchemaConfig | None = None,
    ) -> None:
        """Export all schemas to JSON files.

        Args:
            output_dir: Directory path for output.
            indent: JSON indentation level.
            separate_definitions: If True, create separate schema files for nested
                models and use $ref to reference them.
            ref_template: Template for $ref URLs when separate_definitions=True.
            config: Optional schema configuration for all exported schemas.

        Example:
            ```python
            # Export with custom generator
            config = SchemaConfig(
                schema_generator=CustomGenerator,
                mode="validation"
            )
            manager.dump_schemas("schemas/", config=config)

            # Export validation and serialization schemas separately
            manager.dump_schemas(
                "schemas/validation/",
                config=SchemaConfig(mode="validation")
            )
            manager.dump_schemas(
                "schemas/serialization/",
                config=SchemaConfig(mode="serialization")
            )
            ```
        """
        self._schema_manager.dump_schemas(
            output_dir, indent, separate_definitions, ref_template, config=config
        )
