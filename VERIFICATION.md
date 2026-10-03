# Verification record

Verified 2026-10-02 America/Chicago (2026-10-03 UTC), Linux, Python 3.12.14. Synthetic reference scope only. Independent adversarial findings and grades are recorded separately; this record is implementation verification.

| Command | Outcome |
|---|---|
| `python3 demo.py` | Exit 0; 19/19 expectations |
| `python3 -W error::ResourceWarning -m unittest discover -s tests -v` | Exit 0; 30 tests |
| `uv run --with mcp python interop/sdk_client_check.py` | Exit 0; mcp 2.3.0, protocol 2025-06-18, seven tools and cross-tenant NOT_FOUND |

Actual deferred-COMMIT rollback, strict non-JSON rejection, invalid response-ID sanitization and discovery/runtime bounds are covered. Module/server use one version. Docker, hosted CI and real-provider deployment remain unverified.

Python 3.10/3.11 runtime execution was not performed; source targets Python 3.10+.

## Source identity before this record

SHA-256 binds this record to the source. Changes require rechecking affected assertions.

| File | SHA-256 |
|---|---|
| `.github/workflows/verify.yml` | `c151f5872f0070a4239c18c418699277f23b02418e09dd6f425536d5aa7ef0a2` |
| `.gitignore` | `955c17438f8fb8a2c600c7d6e3904e5c602b90df550537fbc5a15d93e497ef28` |
| `DEPLOYMENT_RUNBOOK.md` | `3e113b56fc563bfcc74a28c1a92590bac22ef3e5a5b1b30e1d0175526ff5fa69` |
| `Dockerfile` | `ebfdcce17d178758cf2481e8cd4312c1cf4270a07292e3f313651fe9f6911d4c` |
| `LICENSE` | `037df8cb655d4ff33487e5052e79b617699db575004c68f7e122187b8de7d67f` |
| `README.md` | `9a2d8598e6a64f118840c729c5f75ff4d7f1bfed4847a93bd0fbd68a83cf48e1` |
| `client.py` | `b7757ff945d277558540a79e203a664406d9f6644e45c30cef385a76e5f7241c` |
| `demo.py` | `f2a39be90c7c9c7eba5c07f4d01a585304fbe1aadebd2c4b40af60d886361064` |
| `gateway/__init__.py` | `951279e6b69619efdc730e5f68623a5bd015c0011aa42465a17fd65a1be656f2` |
| `gateway/audit.py` | `ae33eb8eaac41cb7d80c19cd2e3509b7a3116325b7ac2939ac0aa789841eebde` |
| `gateway/data.py` | `e122c0f1a6cddfc14fd34bdbb388dd96ba371729f6e053cf65233c81ceaa946d` |
| `gateway/policy.py` | `7b39cec84c9474e53b63c13fd33fc80b2bf1462bfba12204dc37aa6919cb79a1` |
| `gateway/server.py` | `08e1969ef8f28b9cb809a26bc88b29d93cc38bbd5adbfc45fc16c3717a92efb3` |
| `gateway/store.py` | `c7c155d6e1f3ef90b54b7b45cdb5bbf00b806b8fbf16bba939b471d9f33c38b9` |
| `interop/sdk_client_check.py` | `e8c1942f3dcf6c9a0893d12a30347847024338d9acf802510ac8afb54c5a7ab6` |
| `tests/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `tests/test_gateway.py` | `00ef8c860b5861fc24b5b60354f759efa72115731b7c83f81f3b08745492f9be` |
