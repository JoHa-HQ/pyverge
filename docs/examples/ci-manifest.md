# CI manifest comparison

Generate and compare a graph snapshot in CI:

<!--pytest.mark.skip-->

```bash
pyverge manifest --manager demo_manager:UserManager \
  --output target/manifest.json

pyverge manifest --manager demo_manager:UserManager \
  --baseline target/manifest.json
```

The manifest command exits `1` when the graph diverges.
