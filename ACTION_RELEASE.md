# GitHub Action release checklist

The floating `v1` tag currently predates the Action outputs and fail-closed checks on `main`.
Publish the next immutable release only after the `main` CI run is green:

```bash
git fetch origin
git switch main
git pull --ff-only
git tag -a v1.1.0 -m "Blast Radius Action v1.1.0"
git push origin v1.1.0
git tag -fa v1 -m "Blast Radius Action v1" v1.1.0
git push origin v1 --force
```

Then create the GitHub release from `v1.1.0` and publish/update the Marketplace listing with
`action.yml`. Verify a consumer repository with a full-history checkout:

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0
    persist-credentials: false
- id: blast-radius
  uses: Lockelamoree/Blast_Radius@v1
  with:
    diff-base: ${{ github.event.pull_request.base.sha }}
    fail-on: never
```

Confirm that the run summary contains the verdict and findings and that the `verdict`,
`critical`, and `caution` outputs are available. Moving `v1` and accepting Marketplace terms are
release-owner actions; they are intentionally separate from production deployment.
