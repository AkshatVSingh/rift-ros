# Output schema

JSON output is a list of diagnostic results. Each result contains:

```json
{
  "severity": "failure",
  "component": "tf",
  "message": "transform unavailable: map -> odom",
  "evidence": "no transform received before timeout"
}
```

Valid severity values are `pass`, `warning`, `failure`, and `info`.
