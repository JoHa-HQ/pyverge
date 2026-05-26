# Schema Export

Generate external schema definitions from your versioned Pydantic models.

## JSON Schema

```python
schemas = manager.get_all_schemas()
# {"User": {"1.0.0": {...}, "2.0.0": {...}}, ...}

# Dump to files
manager.dump_schemas(Path("./schemas"))
```

## Avro

```python
manager.dump_avro_schemas(Path("./avro"))
```

Supports nested records, enums, unions, arrays, and maps.

## Protocol Buffers

```python
manager.dump_proto_schemas(Path("./proto"))
```

Generates `.proto` files with proper `message`, `enum`, and `oneof` definitions.

## TypeScript

```python
# TypeScript interfaces (default)
manager.dump_typescript_schemas(Path("./types"), style="interface")

# Type aliases
manager.dump_typescript_schemas(Path("./types"), style="type")

# Zod runtime validation schemas
manager.dump_typescript_schemas(Path("./schemas"), style="zod")
```

### Organization

```python
# Flat directory (default)
manager.dump_typescript_schemas(Path("./types"))

# Organized by major version
manager.dump_typescript_schemas(Path("./types"), organization="major_version")

# Organized by model
manager.dump_typescript_schemas(Path("./types"), organization="model")
```
