# CLI

Run `pyverge` after installing the CLI extra:

<!--pytest.mark.skip-->

```bash
pyverge info demo_manager:UserManager
pyverge doctor --manager demo_manager:UserManager
pyverge manifest --manager demo_manager:UserManager --output manifest.json
pyverge benchmark --manager demo_manager:UserManager --payload data.json --format json
```
