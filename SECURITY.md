# Security

Report vulnerabilities to stephen@szlholdings.com.

## Serialization

`model.joblib` / pickle / dill are not approved load paths. The kernel source under `torch-ext/` is. If a Hub revision still lists `model.joblib`, treat it as QUARANTINED residue pending a Hub PR with exact `parent_commit`.
