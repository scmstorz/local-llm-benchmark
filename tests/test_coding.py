import hashlib
import json
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from local_llm_benchmark.coding import (
    CodingRunConfig,
    DEFAULT_CODING_CASE_PATH,
    DEFAULT_WHOLE_FILE_CODING_CASE_PATH,
    audit_coding_case,
    diagnose_fenced_file_transport,
    finalize_deferred_track_a_run,
    load_coding_case,
    parse_candidate_files,
    parse_candidate_patch,
    run_track_a_once,
    verify_candidate_artifact,
    verify_candidate_patch,
)


REFERENCE_PATCH = "\n".join(
    line[4:] if line.startswith("    ") else line
    for line in """\
    diff --git a/src/paged_sync/sync.py b/src/paged_sync/sync.py
    --- a/src/paged_sync/sync.py
    +++ b/src/paged_sync/sync.py
    @@ -2,7 +2,7 @@
    <CONTEXT_BLANK>
     from __future__ import annotations
    <CONTEXT_BLANK>
    -from .errors import PageLimitExceeded
    +from .errors import PageLimitExceeded, PaginationCycleError
     from .models import PageSource, Record
    <CONTEXT_BLANK>
    <CONTEXT_BLANK>
    @@ -21,16 +21,22 @@
             raise ValueError("max_pages must be at least one")
    <CONTEXT_BLANK>
         records: list[Record] = []
    +    seen_identifiers: set[str] = set()
    +    fetched_cursors: set[str | None] = set()
         cursor = start_cursor
-    for _ in range(max_pages):
+    for page_number in range(1, max_pages + 1):
+        fetched_cursors.add(cursor)
             page = source.fetch_page(cursor)
-        if not page.records:
-            break
-        records.extend(page.records)
-        cursor = page.next_cursor
-        if cursor is None:
+        for record in page.records:
+            if record.identifier not in seen_identifiers:
+                seen_identifiers.add(record.identifier)
+                records.append(record)
+
+        next_cursor = page.next_cursor
+        if next_cursor is None:
                 return records
-    else:
-        raise PageLimitExceeded(max_pages)
-
-    return records
+        if next_cursor in fetched_cursors:
+            raise PaginationCycleError(next_cursor)
+        if page_number == max_pages:
+            raise PageLimitExceeded(max_pages)
+        cursor = next_cursor
    """.splitlines()
).replace("<CONTEXT_BLANK>", " ") + "\n"

REFERENCE_SYNC_FILE = textwrap.dedent(
    '''\
    """Collect records from a cursor-paginated source."""

    from __future__ import annotations

    from .errors import PageLimitExceeded, PaginationCycleError
    from .models import PageSource, Record


    def collect_records(
        source: PageSource,
        *,
        start_cursor: str | None = None,
        max_pages: int = 100,
    ) -> list[Record]:
        """Return records from consecutive pages."""
        if max_pages < 1:
            raise ValueError("max_pages must be at least one")

        records: list[Record] = []
        seen_identifiers: set[str] = set()
        fetched_cursors: set[str | None] = set()
        cursor = start_cursor
        for page_number in range(1, max_pages + 1):
            fetched_cursors.add(cursor)
            page = source.fetch_page(cursor)
            for record in page.records:
                if record.identifier not in seen_identifiers:
                    seen_identifiers.add(record.identifier)
                    records.append(record)

            next_cursor = page.next_cursor
            if next_cursor is None:
                return records
            if next_cursor in fetched_cursors:
                raise PaginationCycleError(next_cursor)
            if page_number == max_pages:
                raise PageLimitExceeded(max_pages)
            cursor = next_cursor
    '''
)
REFERENCE_FILE_RESPONSE = (
    '<<<FILE path="src/paged_sync/sync.py">>>\n'
    + REFERENCE_SYNC_FILE.rstrip("\n")
    + "\n<<<END FILE>>>"
)

ASYNC_CACHE_CASE_PATH = Path(
    "tasks/coding/dev/async-cache-coalescing/case.json"
)
REFERENCE_ASYNC_CACHE_FILE = textwrap.dedent(
    '''\
    /** Create an asynchronous TTL cache with per-key request coalescing. */
    export function createAsyncCache(loader, { ttlMs, now = Date.now } = {}) {
      if (typeof loader !== "function") {
        throw new TypeError("loader must be a function");
      }
      if (!Number.isFinite(ttlMs) || ttlMs <= 0) {
        throw new RangeError("ttlMs must be a positive finite number");
      }
      if (typeof now !== "function") {
        throw new TypeError("now must be a function");
      }

      const values = new Map();
      const inFlight = new Map();
      const keyGenerations = new Map();
      let clearGeneration = 0;

      const keyGeneration = (key) => keyGenerations.get(key) ?? 0;

      function get(key) {
        const cached = values.get(key);
        if (cached !== undefined) {
          if (now() < cached.expiresAt) {
            return Promise.resolve(cached.value);
          }
          values.delete(key);
        }

        const active = inFlight.get(key);
        if (active !== undefined) {
          return active.promise;
        }

        const startedAfterClear = clearGeneration;
        const startedAtKeyGeneration = keyGeneration(key);
        const token = Symbol("load");
        const promise = Promise.resolve()
          .then(() => loader(key))
          .then((value) => {
            if (
              clearGeneration === startedAfterClear
              && keyGeneration(key) === startedAtKeyGeneration
            ) {
              values.set(key, { value, expiresAt: now() + ttlMs });
            }
            return value;
          })
          .finally(() => {
            if (inFlight.get(key)?.token === token) {
              inFlight.delete(key);
            }
          });

        inFlight.set(key, { token, promise });
        return promise;
      }

      function invalidate(key) {
        values.delete(key);
        inFlight.delete(key);
        keyGenerations.set(key, keyGeneration(key) + 1);
      }

      function clear() {
        values.clear();
        inFlight.clear();
        keyGenerations.clear();
        clearGeneration += 1;
      }

      return { get, invalidate, clear };
    }
    '''
)
REFERENCE_ASYNC_CACHE_RESPONSE = (
    '<<<FILE path="src/async-cache.mjs">>>\n'
    + REFERENCE_ASYNC_CACHE_FILE.rstrip("\n")
    + "\n<<<END FILE>>>"
)

PHP_PAYMENT_CASE_PATH = Path(
    "tasks/coding/dev/php-payment-result-migration/case.json"
)
PHP_PAYMENT_SMOKE_DIAGNOSTIC_PATH = Path(
    "reports/coding/php-payment-result-migration-ornith-smoke-diagnostic.json"
)
PHP_PAYMENT_TRANSPORT_PROTOCOL_PATH = Path(
    "tasks/coding/dev/php-payment-result-migration/transport-diagnostic-v1.json"
)
PHP_PAYMENT_COMPARISON_REPORT_PATH = Path(
    "reports/coding/php-payment-result-migration-track-a-v1.json"
)
REFERENCE_PHP_CHECKOUT_FILE = textwrap.dedent(
    '''\
    <?php

    declare(strict_types=1);

    namespace Benchmark\\Payment;

    final readonly class CheckoutService
    {
        public function __construct(
            private PaymentGateway $gateway,
            private PaymentRepository $repository,
            private RetryPolicy $retryPolicy,
        ) {
        }

        public function checkout(Order $order): CheckoutOutcome
        {
            $existingState = $this->repository->stateFor($order->id);
            if ($existingState !== PaymentState::Unpaid) {
                return match ($existingState) {
                    PaymentState::Paid => CheckoutOutcome::Paid,
                    PaymentState::Declined => CheckoutOutcome::Declined,
                    PaymentState::Pending => CheckoutOutcome::Pending,
                    PaymentState::Unpaid => throw new \\LogicException('unreachable'),
                };
            }

            $request = new PaymentRequest(
                $order->id,
                $order->amountCents,
                'checkout:' . $order->id,
            );
            $attemptNumber = 1;

            while (true) {
                $result = $this->gateway->charge($request);

                if ($result->status === PaymentStatus::Succeeded) {
                    $this->repository->markPaid(
                        $order->id,
                        $result->providerReference,
                    );
                    return CheckoutOutcome::Paid;
                }

                if ($result->status === PaymentStatus::Declined) {
                    $this->repository->markDeclined($order->id, $result->reason);
                    return CheckoutOutcome::Declined;
                }

                if ($result->status === PaymentStatus::Unknown) {
                    $this->repository->markPending($order->id, $result->reason);
                    return CheckoutOutcome::Pending;
                }

                if ($this->retryPolicy->shouldRetry($result, $attemptNumber)) {
                    $attemptNumber++;
                    continue;
                }

                $this->repository->markPending($order->id, $result->reason);
                return CheckoutOutcome::Pending;
            }
        }
    }
    '''
)
REFERENCE_PHP_RETRY_POLICY_FILE = textwrap.dedent(
    '''\
    <?php

    declare(strict_types=1);

    namespace Benchmark\\Payment;

    use InvalidArgumentException;

    final readonly class RetryPolicy
    {
        public function __construct(private int $maxAttempts = 3)
        {
            if ($maxAttempts < 1) {
                throw new InvalidArgumentException('maxAttempts must be at least one');
            }
        }

        public function shouldRetry(PaymentResult $result, int $attemptNumber): bool
        {
            if ($attemptNumber < 1) {
                throw new InvalidArgumentException('attemptNumber must be at least one');
            }

            return $result->status === PaymentStatus::RetryableFailure
                && $attemptNumber < $this->maxAttempts;
        }
    }
    '''
)
REFERENCE_PHP_PAYMENT_RESPONSE = (
    '<<<FILE path="src/CheckoutService.php">>>\n'
    + REFERENCE_PHP_CHECKOUT_FILE.rstrip("\n")
    + "\n<<<END FILE>>>\n"
    + '<<<FILE path="src/RetryPolicy.php">>>\n'
    + REFERENCE_PHP_RETRY_POLICY_FILE.rstrip("\n")
    + "\n<<<END FILE>>>"
)


class CodingTrackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[1]

    def test_load_case_verifies_fixture_and_renders_only_visible_files(self) -> None:
        loaded = load_coding_case(self.repo_root, DEFAULT_CODING_CASE_PATH)

        self.assertEqual(loaded["case"]["track"], "A")
        self.assertIn("# Repository snapshot", loaded["user_message"])
        self.assertIn("src/paged_sync/sync.py", loaded["user_message"])
        self.assertIn("tests/test_sync.py", loaded["user_message"])
        self.assertNotIn("hidden_tests.py", loaded["user_message"])
        self.assertIsNone(
            loaded["card"]["primary_outcome"]["quality_scale_maximum"]
        )

    def test_every_coding_development_case_has_a_valid_track_a_contract(self) -> None:
        case_paths = sorted(
            (self.repo_root / "tasks/coding/dev").glob("*/case*.json")
        )

        self.assertTrue(case_paths)
        for case_path in case_paths:
            with self.subTest(case_path=case_path):
                loaded = load_coding_case(self.repo_root, case_path)
                self.assertEqual(loaded["case"]["track"], "A")

    def test_five_model_comparison_plan_is_frozen_and_consistent(self) -> None:
        case_dir = self.repo_root / "tasks/coding/dev/pagination-cycle-guard"
        plan = json.loads(
            (case_dir / "comparison-plan.json").read_text(encoding="utf-8")
        )
        case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
        loaded = load_coding_case(self.repo_root, case_dir / "case.json")

        def sha256(path: Path) -> str:
            return hashlib.sha256(path.read_bytes()).hexdigest()

        self.assertEqual(plan["status"], "frozen_before_comparison_execution")
        self.assertEqual(plan["case_id"], case["case_id"])
        self.assertEqual(plan["track"], "A")
        self.assertEqual(plan["study_mode"], "capability_sweep")
        self.assertEqual(plan["execution_order"], ["C", "A", "B", "E", "D"])
        self.assertEqual(set(plan["execution_order"]), set(plan["models"]))
        self.assertEqual(
            plan["models"],
            {
                "A": {
                    "name": "qwen3.6:35b-a3b-mxfp8",
                    "digest": "d82a30588f1c7bc2afa5226f3d67c8987bf505104f8f0512a0f8643ac4525d16",
                },
                "B": {
                    "name": "qwen3.8:27b-mlx",
                    "digest": "5642e97495e1a088883805981563dcdc4a040c2f53388b7a41d1f24d3622cf7e",
                },
                "C": {
                    "name": "gpt-oss:20b",
                    "digest": "17052f91a42e97930aa6e28a6c6c06a983e6a58dbb00434885a0cf5313e376f7",
                },
                "D": {
                    "name": "muse-glimmer:30b-mlx",
                    "digest": "ef32a55b4976faa955cbab0462d09bd081351ef5b87d73d8fcd299bf17c111d7",
                },
                "E": {
                    "name": "ornith-1.5:35b",
                    "digest": "9f3b89b2521908dd2e6f7a11fa368e62c8f89e1075f22604e4d1a76dd1240fcc",
                },
            },
        )

        frozen = plan["frozen_inputs"]
        self.assertEqual(frozen["case_file_sha256"], sha256(case_dir / "case.json"))
        self.assertEqual(
            frozen["benchmark_card_file_sha256"],
            sha256(case_dir / "benchmark-card.json"),
        )
        self.assertEqual(frozen["task_file_sha256"], sha256(case_dir / "TASK.md"))
        self.assertEqual(
            frozen["system_prompt_file_sha256"],
            sha256(case_dir / "prompt/system.txt"),
        )
        self.assertEqual(
            frozen["hidden_test_file_sha256"],
            sha256(case_dir / "verifier/hidden_tests.py"),
        )
        self.assertEqual(
            frozen["coding_runner_file_sha256"],
            # Historical identity of the runner used for the frozen v1 run.
            "20c6b949a5decdda7e93b44ce0bafd94d5b79d8204f8c146be1974d0c6c225e8",
        )
        self.assertEqual(
            frozen["fixture_manifest_sha256"],
            loaded["manifest_sha256"],
        )

        methodology = plan["methodology"]
        defaults = case["inference_defaults"]
        for setting in (
            "temperature",
            "seed",
            "think",
            "num_ctx",
            "num_predict",
            "keep_alive",
            "timeout_seconds",
        ):
            self.assertEqual(methodology[setting], defaults[setting])
        self.assertEqual(methodology["measured_attempts_per_model"], 1)
        self.assertEqual(methodology["automatic_retries"], 0)
        self.assertEqual(methodology["patch_repair"], "forbidden")
        self.assertTrue(plan["development_smoke"]["excluded_from_comparison"])
        self.assertTrue(
            plan["execution_authorization"][
                "plan_freeze_does_not_authorize_generation"
            ]
        )

    def test_frozen_baseline_is_red_in_both_test_layers(self) -> None:
        audit = audit_coding_case(self.repo_root, DEFAULT_CODING_CASE_PATH)

        self.assertEqual(audit["status"], "complete")
        self.assertFalse(audit["public_tests_pass"])
        self.assertFalse(audit["hidden_tests_pass"])
        self.assertTrue(audit["baseline_expectations_met"])

    def test_async_cache_case_uses_node_and_hides_acceptance_checks(self) -> None:
        loaded = load_coding_case(self.repo_root, ASYNC_CACHE_CASE_PATH)
        verification = loaded["case"]["verification"]

        self.assertEqual(loaded["case"]["task_family"], "feature_implementation")
        self.assertEqual(
            verification["public_test_command"],
            ["node", "--test", "tests/cache.test.mjs"],
        )
        self.assertEqual(
            verification["hidden_test_command"],
            ["node", "{hidden_test}", "{fixture}"],
        )
        self.assertNotIn("hidden_tests.mjs", loaded["user_message"])
        self.assertIn("tests/cache.test.mjs", loaded["user_message"])
        self.assertEqual(
            loaded["artifact_contract"]["allowed_path_globs"], ["src/*.mjs"]
        )

    def test_async_cache_baseline_is_red_with_recorded_node_runtime(self) -> None:
        audit = audit_coding_case(self.repo_root, ASYNC_CACHE_CASE_PATH)

        self.assertEqual(audit["status"], "complete")
        self.assertTrue(audit["baseline_expectations_met"])
        self.assertFalse(audit["public_tests_pass"])
        self.assertFalse(audit["hidden_tests_pass"])
        self.assertTrue(audit["verification_runtime"]["passed"])
        node_major = int(
            audit["verification_runtime"]["stdout"].removeprefix("v").split(".")[0]
        )
        self.assertGreaterEqual(node_major, 22)

    def test_async_cache_reference_artifact_passes_all_node_checks(self) -> None:
        result = verify_candidate_artifact(
            self.repo_root,
            ASYNC_CACHE_CASE_PATH,
            REFERENCE_ASYNC_CACHE_RESPONSE,
        )

        self.assertTrue(result["verified_success"], result)
        self.assertEqual(
            result["integrity"]["changed_paths"], ["src/async-cache.mjs"]
        )
        self.assertTrue(result["tests"]["runtime"]["passed"])
        node_major = int(
            result["tests"]["runtime"]["stdout"].removeprefix("v").split(".")[0]
        )
        self.assertGreaterEqual(node_major, 22)
        self.assertTrue(result["tests"]["public"]["passed"])
        self.assertTrue(result["tests"]["hidden"]["passed"])
        self.assertIn("8/8 hidden checks passed", result["tests"]["hidden"]["stdout"])

    def test_php_payment_case_uses_php_and_protects_contracts(self) -> None:
        loaded = load_coding_case(self.repo_root, PHP_PAYMENT_CASE_PATH)
        verification = loaded["case"]["verification"]

        self.assertEqual(loaded["case"]["task_family"], "api_migration")
        self.assertEqual(
            verification["public_test_command"], ["php", "tests/run.php"]
        )
        self.assertEqual(
            verification["hidden_test_command"],
            ["php", "{hidden_test}", "{fixture}"],
        )
        self.assertNotIn("hidden_tests.php", loaded["user_message"])
        self.assertIn("tests/run.php", loaded["user_message"])
        self.assertEqual(
            loaded["artifact_contract"]["allowed_path_globs"],
            ["src/CheckoutService.php", "src/RetryPolicy.php"],
        )

    def test_php_payment_baseline_is_red_with_recorded_php_runtime(self) -> None:
        audit = audit_coding_case(self.repo_root, PHP_PAYMENT_CASE_PATH)

        self.assertEqual(audit["status"], "complete")
        self.assertTrue(audit["baseline_expectations_met"])
        self.assertFalse(audit["public_tests_pass"])
        self.assertFalse(audit["hidden_tests_pass"])
        self.assertTrue(audit["verification_runtime"]["passed"])
        version = audit["verification_runtime"]["stdout"].splitlines()[0]
        major, minor, *_ = version.split()[1].split(".")
        self.assertGreaterEqual((int(major), int(minor)), (8, 4))

    def test_php_payment_reference_artifact_passes_all_checks(self) -> None:
        result = verify_candidate_artifact(
            self.repo_root,
            PHP_PAYMENT_CASE_PATH,
            REFERENCE_PHP_PAYMENT_RESPONSE,
        )

        self.assertTrue(result["verified_success"], result)
        self.assertEqual(
            result["integrity"]["changed_paths"],
            ["src/CheckoutService.php", "src/RetryPolicy.php"],
        )
        self.assertTrue(result["tests"]["runtime"]["passed"])
        self.assertTrue(result["tests"]["public"]["passed"])
        self.assertTrue(result["tests"]["hidden"]["passed"])
        self.assertIn("8/8 hidden checks passed", result["tests"]["hidden"]["stdout"])

    def test_php_payment_smoke_diagnostic_preserves_both_outcomes(self) -> None:
        report = json.loads(
            (self.repo_root / PHP_PAYMENT_SMOKE_DIAGNOSTIC_PATH).read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(
            report["report_type"], "posthoc_transport_normalization_diagnostic"
        )
        self.assertFalse(report["source_run"]["original_verified_success"])
        self.assertEqual(
            report["source_run"]["original_failure_code"], "malformed_artifact"
        )
        self.assertEqual(report["diagnostic_status"]["new_inference_attempts"], 0)
        self.assertFalse(report["diagnostic_status"]["changes_original_outcome"])
        self.assertFalse(
            report["diagnostic_status"]["eligible_for_formal_comparison"]
        )
        for candidate_file in report["transport_normalization"]["files"]:
            self.assertEqual(
                candidate_file["source_code_sha256"],
                candidate_file["normalized_code_sha256"],
            )
        verification = report["diagnostic_verification"]
        self.assertEqual(verification["public"]["passed"], 4)
        self.assertEqual(verification["public"]["total"], 4)
        self.assertEqual(verification["hidden"]["passed"], 8)
        self.assertEqual(verification["hidden"]["total"], 8)
        self.assertTrue(verification["verified_success_under_normalized_transport"])

    def test_php_fence_diagnostic_preserves_code_and_verifies_semantics(self) -> None:
        fenced_response = (
            "```php\n"
            + REFERENCE_PHP_CHECKOUT_FILE.rstrip("\n")
            + "\n```\n\n```php\n"
            + REFERENCE_PHP_RETRY_POLICY_FILE.rstrip("\n")
            + "\n```"
        )

        result = diagnose_fenced_file_transport(
            self.repo_root,
            PHP_PAYMENT_CASE_PATH,
            PHP_PAYMENT_TRANSPORT_PROTOCOL_PATH,
            fenced_response,
        )

        self.assertEqual(result["strict_output_status"], "malformed")
        self.assertEqual(result["strict_failure_code"], "malformed_artifact")
        self.assertEqual(result["diagnostic_status"], "complete")
        self.assertTrue(result["code_byte_identity_verified"])
        self.assertFalse(result["changes_primary_outcome"])
        self.assertEqual(result["new_inference_attempts"], 0)
        self.assertEqual(
            [item["path"] for item in result["files"]],
            ["src/CheckoutService.php", "src/RetryPolicy.php"],
        )
        for candidate_file in result["files"]:
            self.assertEqual(
                candidate_file["source_code_sha256"],
                candidate_file["normalized_code_sha256"],
            )
        self.assertTrue(result["verification"]["verified_success"])
        self.assertTrue(result["verification"]["tests"]["public"]["passed"])
        self.assertTrue(result["verification"]["tests"]["hidden"]["passed"])

    def test_php_fence_diagnostic_rejects_prose_and_strict_artifacts(self) -> None:
        fenced_response = (
            "```php\n"
            + REFERENCE_PHP_RETRY_POLICY_FILE.rstrip("\n")
            + "\n```"
        )
        cases = {
            "prose": "Here is the file:\n" + fenced_response,
            "strict": REFERENCE_PHP_PAYMENT_RESPONSE,
        }

        for name, response in cases.items():
            with self.subTest(name=name):
                result = diagnose_fenced_file_transport(
                    self.repo_root,
                    PHP_PAYMENT_CASE_PATH,
                    PHP_PAYMENT_TRANSPORT_PROTOCOL_PATH,
                    response,
                )
                self.assertEqual(result["diagnostic_status"], "not_eligible")
                self.assertIsNone(result["verification"])

    def test_php_payment_five_model_plan_is_frozen_and_consistent(self) -> None:
        case_dir = self.repo_root / "tasks/coding/dev/php-payment-result-migration"
        plan = json.loads(
            (case_dir / "comparison-plan.json").read_text(encoding="utf-8")
        )
        loaded = load_coding_case(self.repo_root, case_dir / "case.json")

        def file_sha256(path: Path) -> str:
            return hashlib.sha256(path.read_bytes()).hexdigest()

        self.assertEqual(plan["status"], "frozen_before_comparison_execution")
        self.assertEqual(plan["case_id"], loaded["case"]["case_id"])
        self.assertEqual(plan["case_version"], "1.0.0")
        self.assertEqual(plan["track"], "A")
        self.assertEqual(plan["study_mode"], "capability_sweep")
        self.assertEqual(plan["execution_order"], ["B", "C", "E", "D", "A"])
        self.assertEqual(set(plan["execution_order"]), set(plan["models"]))
        self.assertEqual(
            plan["models"],
            {
                "A": {
                    "name": "qwen3.6:35b-a3b-mxfp8",
                    "digest": "d82a30588f1c7bc2afa5226f3d67c8987bf505104f8f0512a0f8643ac4525d16",
                },
                "B": {
                    "name": "qwen3.8:27b-mlx",
                    "digest": "5642e97495e1a088883805981563dcdc4a040c2f53388b7a41d1f24d3622cf7e",
                },
                "C": {
                    "name": "gpt-oss:20b",
                    "digest": "17052f91a42e97930aa6e28a6c6c06a983e6a58dbb00434885a0cf5313e376f7",
                },
                "D": {
                    "name": "muse-glimmer:30b-mlx",
                    "digest": "ef32a55b4976faa955cbab0462d09bd081351ef5b87d73d8fcd299bf17c111d7",
                },
                "E": {
                    "name": "ornith-1.5:35b",
                    "digest": "9f3b89b2521908dd2e6f7a11fa368e62c8f89e1075f22604e4d1a76dd1240fcc",
                },
            },
        )

        prior_orders = ["DBCEA", "AEDBC", "CABED", "EDACB"]
        current_positions = {
            alias: plan["execution_order"].index(alias) + 1 for alias in plan["models"]
        }
        prior_positions = {
            alias: {order.index(alias) + 1 for order in prior_orders}
            for alias in plan["models"]
        }
        self.assertEqual(
            sum(
                current_positions[alias] not in prior_positions[alias]
                for alias in plan["models"]
            ),
            4,
        )
        latest_positions = {alias: "EDACB".index(alias) + 1 for alias in plan["models"]}
        self.assertGreaterEqual(
            min(
                abs(current_positions[alias] - latest_positions[alias])
                for alias in plan["models"]
            ),
            2,
        )

        frozen = plan["frozen_inputs"]
        self.assertEqual(frozen["case_file_sha256"], file_sha256(case_dir / "case.json"))
        self.assertEqual(
            frozen["benchmark_card_file_sha256"],
            file_sha256(case_dir / "benchmark-card.json"),
        )
        self.assertEqual(frozen["task_file_sha256"], loaded["task_sha256"])
        self.assertEqual(
            frozen["system_prompt_file_sha256"],
            file_sha256(case_dir / "prompt/system-whole-file-v1.txt"),
        )
        self.assertEqual(
            frozen["fixture_manifest_file_sha256"],
            file_sha256(case_dir / "fixture-manifest.json"),
        )
        self.assertEqual(frozen["fixture_manifest_sha256"], loaded["manifest_sha256"])
        self.assertEqual(frozen["hidden_test_file_sha256"], loaded["hidden_test_sha256"])
        self.assertEqual(
            frozen["transport_diagnostic_protocol_sha256"],
            file_sha256(case_dir / "transport-diagnostic-v1.json"),
        )
        self.assertEqual(
            frozen["coding_runner_file_sha256"],
            "e1efac7437e9154c1dfe9d31fb48313a83de363ceff5357d765a751292e28d2c",
        )
        self.assertEqual(
            frozen["cli_file_sha256"],
            "c2a77aa97c737ae9b6bace846d9646dad89a4658df4dcefb9637066406df0738",
        )
        self.assertEqual(
            frozen["harness_git_commit"],
            "9cffd0f5dad7538e630e927fdd50d9adafb253f6",
        )

        defaults = loaded["case"]["inference_defaults"]
        methodology = plan["methodology"]
        for setting in (
            "temperature",
            "seed",
            "think",
            "num_ctx",
            "num_predict",
            "keep_alive",
            "timeout_seconds",
        ):
            self.assertEqual(methodology[setting], defaults[setting])
        self.assertEqual(methodology["measured_attempts_per_model"], 1)
        self.assertEqual(methodology["automatic_retries"], 0)
        self.assertFalse(methodology["test_feedback_to_candidate"])
        self.assertTrue(plan["development_smoke"]["excluded_from_comparison"])
        self.assertEqual(plan["evaluation"]["primary_outcome"], "strict_verified_success")
        self.assertEqual(
            plan["evaluation"]["secondary_outcome"],
            "verified_success_under_normalized_transport",
        )
        self.assertTrue(
            plan["execution_authorization"][
                "explicit_user_authorization_received_before_freeze"
            ]
        )

    def test_php_payment_report_preserves_three_outcome_layers(self) -> None:
        case_dir = self.repo_root / "tasks/coding/dev/php-payment-result-migration"
        plan = json.loads(
            (case_dir / "comparison-plan.json").read_text(encoding="utf-8")
        )
        report = json.loads(
            (self.repo_root / PHP_PAYMENT_COMPARISON_REPORT_PATH).read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(report["plan_id"], plan["plan_id"])
        self.assertEqual(report["execution_order"], plan["execution_order"])
        self.assertEqual([run["alias"] for run in report["runs"]], ["B", "C", "E", "D", "A"])
        self.assertEqual(len(report["runs"]), 5)
        self.assertTrue(all(not run["strict"]["verified_success"] for run in report["runs"]))

        aggregate = report["aggregate"]
        self.assertEqual(aggregate["completed_inference_attempts"], 5)
        self.assertEqual(aggregate["strict_valid_artifacts"], 0)
        self.assertEqual(aggregate["strict_verified_successes"], 0)
        self.assertEqual(aggregate["preregistered_transport_diagnostic_eligible"], 1)
        self.assertEqual(aggregate["preregistered_transport_diagnostic_successes"], 1)
        self.assertEqual(aggregate["posthoc_transport_audits_executed"], 3)
        self.assertEqual(aggregate["posthoc_transport_audit_successes"], 2)
        self.assertEqual(aggregate["exploratory_verifier_confirmed_code_semantic_successes"], 3)

        by_alias = {run["alias"]: run for run in report["runs"]}
        self.assertEqual(by_alias["C"]["strict"]["failure_code"], "empty_output")
        self.assertEqual(
            by_alias["E"]["preregistered_transport_diagnostic"]["status"],
            "complete",
        )
        self.assertTrue(
            by_alias["E"]["preregistered_transport_diagnostic"][
                "verified_success_under_normalized_transport"
            ]
        )
        self.assertTrue(
            by_alias["B"]["posthoc_transport_audit"][
                "verified_success_under_posthoc_transport"
            ]
        )
        self.assertTrue(
            by_alias["D"]["posthoc_transport_audit"][
                "verified_success_under_posthoc_transport"
            ]
        )
        self.assertFalse(
            by_alias["A"]["posthoc_transport_audit"][
                "verified_success_under_posthoc_transport"
            ]
        )
        self.assertEqual(by_alias["A"]["posthoc_transport_audit"]["public_tests_passed"], 0)
        self.assertEqual(by_alias["A"]["posthoc_transport_audit"]["hidden_tests_passed"], 2)

        for run in report["runs"]:
            response_path = (
                self.repo_root
                / "results/coding-runs"
                / run["run_id"]
                / "response.txt"
            )
            if response_path.exists():
                self.assertEqual(
                    run["response_sha256"], hashlib.sha256(response_path.read_bytes()).hexdigest()
                )

    def test_async_cache_five_model_plan_is_frozen_and_consistent(self) -> None:
        case_dir = self.repo_root / "tasks/coding/dev/async-cache-coalescing"
        plan = json.loads(
            (case_dir / "comparison-plan.json").read_text(encoding="utf-8")
        )
        loaded = load_coding_case(self.repo_root, case_dir / "case.json")
        pagination_plan = json.loads(
            (
                self.repo_root
                / "tasks/coding/dev/pagination-cycle-guard/comparison-plan-whole-file-v1.1.json"
            ).read_text(encoding="utf-8")
        )

        def sha256(path: Path) -> str:
            return hashlib.sha256(path.read_bytes()).hexdigest()

        self.assertEqual(plan["status"], "frozen_before_comparison_execution")
        self.assertEqual(plan["case_id"], loaded["case"]["case_id"])
        self.assertEqual(plan["case_version"], "1.0.0")
        self.assertEqual(plan["track"], "A")
        self.assertEqual(plan["study_mode"], "capability_sweep")
        self.assertEqual(plan["models"], pagination_plan["models"])
        self.assertEqual(plan["execution_order"], ["E", "D", "A", "C", "B"])

        prior_distinct_orders = ["DBCEA", "AEDBC", "CABED"]
        current_order = "".join(plan["execution_order"])
        for alias in "ABCDE":
            current_position = current_order.index(alias)
            self.assertTrue(
                all(
                    order.index(alias) != current_position
                    for order in prior_distinct_orders
                )
            )

        frozen = plan["frozen_inputs"]
        self.assertEqual(
            frozen["case_file_sha256"], sha256(case_dir / "case.json")
        )
        self.assertEqual(
            frozen["benchmark_card_file_sha256"],
            sha256(case_dir / "benchmark-card.json"),
        )
        self.assertEqual(frozen["task_file_sha256"], sha256(case_dir / "TASK.md"))
        self.assertEqual(
            frozen["system_prompt_file_sha256"],
            sha256(case_dir / "prompt/system-whole-file-v1.txt"),
        )
        self.assertEqual(
            frozen["hidden_test_file_sha256"],
            sha256(case_dir / "verifier/hidden_tests.mjs"),
        )
        self.assertEqual(
            frozen["fixture_manifest_sha256"], loaded["manifest_sha256"]
        )
        self.assertEqual(
            frozen["coding_runner_file_sha256"],
            # Historical identity of the runner used for the frozen comparison.
            "cabd96c7d448738d6b3e0cfb077c18d90a0ff3ebef396cc544630aa0407410c5",
        )

        defaults = loaded["case"]["inference_defaults"]
        methodology = plan["methodology"]
        for setting in (
            "temperature",
            "seed",
            "think",
            "num_ctx",
            "num_predict",
            "keep_alive",
            "timeout_seconds",
        ):
            self.assertEqual(methodology[setting], defaults[setting])
        self.assertEqual(methodology["measured_attempts_per_model"], 1)
        self.assertEqual(methodology["warmup_attempts_per_model"], 0)
        self.assertEqual(methodology["automatic_retries"], 0)
        self.assertEqual(methodology["artifact_repair"], "forbidden")
        self.assertTrue(plan["development_smoke"]["excluded_from_comparison"])
        self.assertFalse(plan["development_smoke"]["verified_success"])
        self.assertTrue(
            plan["execution_authorization"][
                "plan_freeze_does_not_authorize_generation"
            ]
        )

    def test_whole_file_comparison_plan_is_frozen_and_paired_with_v1(self) -> None:
        case_dir = self.repo_root / "tasks/coding/dev/pagination-cycle-guard"
        plan = json.loads(
            (case_dir / "comparison-plan-whole-file-v1.1.json").read_text(
                encoding="utf-8"
            )
        )
        v1_plan = json.loads(
            (case_dir / "comparison-plan.json").read_text(encoding="utf-8")
        )
        loaded = load_coding_case(
            self.repo_root, DEFAULT_WHOLE_FILE_CODING_CASE_PATH
        )

        def sha256(path: Path) -> str:
            return hashlib.sha256(path.read_bytes()).hexdigest()

        self.assertEqual(plan["status"], "frozen_before_comparison_execution")
        self.assertEqual(plan["case_id"], loaded["case"]["case_id"])
        self.assertEqual(plan["case_version"], "1.1.0")
        self.assertEqual(plan["study_mode"], "capability_sweep")
        self.assertEqual(plan["models"], v1_plan["models"])
        self.assertEqual(plan["execution_order"], v1_plan["execution_order"])

        frozen = plan["frozen_inputs"]
        self.assertEqual(
            frozen["case_file_sha256"],
            sha256(case_dir / "case-whole-file-v1.1.json"),
        )
        self.assertEqual(
            frozen["benchmark_card_file_sha256"],
            sha256(case_dir / "benchmark-card-whole-file-v1.1.json"),
        )
        self.assertEqual(frozen["task_file_sha256"], sha256(case_dir / "TASK.md"))
        self.assertEqual(
            frozen["system_prompt_file_sha256"],
            sha256(case_dir / "prompt/system-whole-file-v1.1.txt"),
        )
        self.assertEqual(
            frozen["hidden_test_file_sha256"],
            sha256(case_dir / "verifier/hidden_tests.py"),
        )
        self.assertEqual(
            frozen["fixture_manifest_sha256"], loaded["manifest_sha256"]
        )
        self.assertEqual(
            frozen["coding_runner_file_sha256"],
            "2ccf436c953efafb66e981f9bb5ab7572f54e48cc34acd1cb2d34ac197248314",
        )
        self.assertEqual(
            frozen["coding_runner_git_commit"],
            "8b8a8f7e443530f2e6131ad4f2c2086353e9a58c",
        )

        defaults = loaded["case"]["inference_defaults"]
        for setting in (
            "temperature",
            "seed",
            "think",
            "num_ctx",
            "num_predict",
            "keep_alive",
            "timeout_seconds",
        ):
            self.assertEqual(plan["methodology"][setting], defaults[setting])
        self.assertEqual(plan["methodology"]["measured_attempts_per_model"], 1)
        self.assertEqual(plan["methodology"]["automatic_retries"], 0)
        self.assertEqual(plan["methodology"]["artifact_repair"], "forbidden")
        self.assertTrue(plan["development_smoke"]["verified_success"])
        self.assertTrue(plan["development_smoke"]["excluded_from_comparison"])
        self.assertTrue(
            plan["execution_authorization"][
                "plan_freeze_does_not_authorize_generation"
            ]
        )

    def test_first_coding_comparison_report_preserves_all_failed_attempts(
        self,
    ) -> None:
        report = json.loads(
            (
                self.repo_root
                / "reports/coding/pagination-cycle-guard-track-a-v1.json"
            ).read_text(encoding="utf-8")
        )
        plan = json.loads(
            (
                self.repo_root
                / "tasks/coding/dev/pagination-cycle-guard/comparison-plan.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(report["plan_id"], plan["plan_id"])
        self.assertEqual(report["execution_order"], plan["execution_order"])
        self.assertEqual(
            [run["alias"] for run in report["runs"]],
            plan["execution_order"],
        )
        self.assertEqual(
            [run["model"] for run in report["runs"]],
            [plan["models"][alias]["name"] for alias in plan["execution_order"]],
        )
        self.assertTrue(all(not run["verified_success"] for run in report["runs"]))
        self.assertEqual(report["aggregate"]["planned_attempts"], 5)
        self.assertEqual(report["aggregate"]["completed_inference_attempts"], 5)
        self.assertEqual(report["aggregate"]["applicable_patches"], 0)
        self.assertEqual(report["aggregate"]["verified_successes"], 0)
        self.assertIsNone(report["aggregate"]["time_to_verified_success"])

    def test_whole_file_report_preserves_frozen_and_posthoc_results(self) -> None:
        report = json.loads(
            (
                self.repo_root
                / "reports/coding/pagination-cycle-guard-track-a-whole-file-v1.1.json"
            ).read_text(encoding="utf-8")
        )
        plan = json.loads(
            (
                self.repo_root
                / "tasks/coding/dev/pagination-cycle-guard/"
                "comparison-plan-whole-file-v1.1.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(report["plan_id"], plan["plan_id"])
        self.assertEqual(report["execution_order"], plan["execution_order"])
        self.assertEqual(
            [run["alias"] for run in report["runs"]], plan["execution_order"]
        )
        self.assertEqual(
            [run["model"] for run in report["runs"]],
            [plan["models"][alias]["name"] for alias in plan["execution_order"]],
        )
        self.assertEqual(report["aggregate"]["completed_inference_attempts"], 5)
        self.assertEqual(report["aggregate"]["valid_whole_file_artifacts"], 4)
        self.assertEqual(report["aggregate"]["frozen_verifier_successes"], 3)
        self.assertEqual(report["aggregate"]["posthoc_counterexamples_found"], 1)
        self.assertEqual(report["aggregate"]["posthoc_audited_successes"], 2)

        by_alias = {run["alias"]: run for run in report["runs"]}
        self.assertTrue(by_alias["B"]["frozen_verifier_success"])
        self.assertFalse(by_alias["B"]["posthoc_requirement_audit"]["pass"])
        self.assertEqual(
            by_alias["B"]["posthoc_requirement_audit"]["observed_calls"],
            ["resume", "next", "resume"],
        )
        self.assertTrue(by_alias["E"]["posthoc_requirement_audit"]["pass"])
        self.assertTrue(by_alias["D"]["posthoc_requirement_audit"]["pass"])

    def test_async_cache_report_preserves_all_five_failed_outcomes(self) -> None:
        report = json.loads(
            (
                self.repo_root
                / "reports/coding/async-cache-coalescing-track-a-v1.json"
            ).read_text(encoding="utf-8")
        )
        plan = json.loads(
            (
                self.repo_root
                / "tasks/coding/dev/async-cache-coalescing/comparison-plan.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(report["plan_id"], plan["plan_id"])
        self.assertEqual(report["execution_order"], plan["execution_order"])
        self.assertEqual(
            [run["alias"] for run in report["runs"]], plan["execution_order"]
        )
        self.assertEqual(
            [run["model"] for run in report["runs"]],
            [plan["models"][alias]["name"] for alias in plan["execution_order"]],
        )
        self.assertTrue(all(not run["verified_success"] for run in report["runs"]))

        aggregate = report["aggregate"]
        self.assertEqual(aggregate["planned_attempts"], 5)
        self.assertEqual(aggregate["completed_inference_attempts"], 5)
        self.assertEqual(aggregate["valid_whole_file_artifacts"], 4)
        self.assertEqual(aggregate["public_test_suites_passed"], 2)
        self.assertEqual(aggregate["hidden_test_suites_passed"], 0)
        self.assertEqual(aggregate["verified_successes"], 0)

        by_alias = {run["alias"]: run for run in report["runs"]}
        self.assertEqual(
            (
                by_alias["B"]["public_tests_passed"],
                by_alias["B"]["hidden_tests_passed"],
            ),
            (4, 6),
        )
        self.assertEqual(
            (
                by_alias["D"]["public_tests_passed"],
                by_alias["D"]["hidden_tests_passed"],
            ),
            (4, 5),
        )
        self.assertEqual(by_alias["C"]["failure_code"], "empty_output")
        self.assertTrue(report["environment"]["repeated_resource_gate"]["passed"])
        self.assertEqual(
            report["environment"]["ollama_empty_for_postflight_seconds"], 30
        )

    def test_v1_2_replay_report_is_explicitly_retrospective(self) -> None:
        case_dir = self.repo_root / "tasks/coding/dev/pagination-cycle-guard"

        def file_sha256(path: Path) -> str:
            return hashlib.sha256(path.read_bytes()).hexdigest()

        report = json.loads(
            (
                self.repo_root
                / "reports/coding/"
                "pagination-cycle-guard-verifier-v1.2-retrospective-replay.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(report["report_type"], "retrospective_verifier_replay")
        self.assertFalse(report["formal_comparison"])
        self.assertEqual(report["aggregate"]["new_inference_attempts"], 0)
        self.assertEqual(report["aggregate"]["artifacts_replayed"], 4)
        self.assertEqual(report["aggregate"]["v1_2_replay_successes"], 2)
        self.assertEqual(
            report["aggregate"]["known_v1_1_false_positives_caught"], 1
        )

        input_hashes = report["v1_2_input_hashes"]
        self.assertEqual(
            input_hashes["case_file_sha256"],
            file_sha256(case_dir / "case-whole-file-v1.2.json"),
        )
        self.assertEqual(
            input_hashes["benchmark_card_file_sha256"],
            file_sha256(case_dir / "benchmark-card-whole-file-v1.2.json"),
        )
        self.assertEqual(
            input_hashes["hidden_test_file_sha256"],
            file_sha256(case_dir / "verifier/hidden_tests_v1_2.py"),
        )
        self.assertEqual(
            input_hashes["task_file_sha256"], file_sha256(case_dir / "TASK.md")
        )
        self.assertEqual(
            input_hashes["system_prompt_file_sha256"],
            file_sha256(case_dir / "prompt/system-whole-file-v1.1.txt"),
        )
        loaded = load_coding_case(
            self.repo_root, case_dir / "case-whole-file-v1.2.json"
        )
        self.assertEqual(
            input_hashes["fixture_manifest_sha256"], loaded["manifest_sha256"]
        )

        by_alias = {run["alias"]: run for run in report["runs"]}
        self.assertEqual(by_alias["C"]["replay_status"], "not_applicable")
        self.assertFalse(by_alias["A"]["v1_2_replay"]["verified_success"])
        self.assertTrue(
            by_alias["A"]["v1_2_replay"]["new_start_cursor_test_passed"]
        )
        self.assertTrue(by_alias["B"]["original_v1_1_frozen_verifier_success"])
        self.assertFalse(by_alias["B"]["v1_2_replay"]["verified_success"])
        self.assertFalse(
            by_alias["B"]["v1_2_replay"]["new_start_cursor_test_passed"]
        )
        self.assertTrue(by_alias["E"]["v1_2_replay"]["verified_success"])
        self.assertTrue(by_alias["D"]["v1_2_replay"]["verified_success"])

        for alias in ("A", "B", "E", "D"):
            response_path = (
                self.repo_root
                / "results/coding-runs"
                / by_alias[alias]["run_id"]
                / "response.txt"
            )
            if response_path.exists():
                self.assertEqual(
                    by_alias[alias]["response_sha256"], file_sha256(response_path)
                )

    def test_reference_patch_is_a_verified_success(self) -> None:
        result = verify_candidate_patch(
            self.repo_root,
            DEFAULT_CODING_CASE_PATH,
            REFERENCE_PATCH,
        )

        self.assertTrue(result["verified_success"], result)
        self.assertEqual(result["task_status"], "verified_success")
        self.assertEqual(result["verification_status"], "passed")
        self.assertEqual(
            result["integrity"]["changed_paths"], ["src/paged_sync/sync.py"]
        )
        self.assertTrue(result["tests"]["public"]["passed"])
        self.assertTrue(result["tests"]["hidden"]["passed"])

    def test_whole_file_case_is_a_separate_version_of_the_same_task(self) -> None:
        patch_case = load_coding_case(self.repo_root, DEFAULT_CODING_CASE_PATH)
        file_case = load_coding_case(
            self.repo_root, DEFAULT_WHOLE_FILE_CODING_CASE_PATH
        )

        self.assertEqual(patch_case["case"]["case_id"], file_case["case"]["case_id"])
        self.assertEqual(patch_case["case"]["case_version"], "1.0.0")
        self.assertEqual(file_case["case"]["case_version"], "1.1.0")
        self.assertEqual(
            file_case["artifact_contract"]["format"], "whole_file_envelope"
        )
        self.assertEqual(
            patch_case["manifest_sha256"], file_case["manifest_sha256"]
        )
        self.assertEqual(patch_case["task_sha256"], file_case["task_sha256"])
        self.assertEqual(
            patch_case["hidden_test_sha256"], file_case["hidden_test_sha256"]
        )
        self.assertEqual(
            patch_case["case"]["candidate_context"],
            file_case["case"]["candidate_context"],
        )
        self.assertEqual(
            patch_case["case"]["inference_defaults"],
            file_case["case"]["inference_defaults"],
        )
        self.assertEqual(
            patch_case["case"]["verification"]["public_test_command"],
            file_case["case"]["verification"]["public_test_command"],
        )
        self.assertEqual(
            patch_case["case"]["verification"]["baseline_expected"],
            file_case["case"]["verification"]["baseline_expected"],
        )
        self.assertIn('<<<FILE path="relative/path.py">>>', file_case["system_message"])
        self.assertIn("Do not return a Git diff", file_case["system_message"])

    def test_reference_whole_file_artifact_is_a_verified_success(self) -> None:
        result = verify_candidate_artifact(
            self.repo_root,
            DEFAULT_WHOLE_FILE_CODING_CASE_PATH,
            REFERENCE_FILE_RESPONSE,
        )

        self.assertTrue(result["verified_success"], result)
        self.assertEqual(result["artifact"]["format"], "whole_file_envelope")
        self.assertEqual(result["artifact"]["paths"], ["src/paged_sync/sync.py"])
        self.assertTrue(result["artifact_install"]["passed"])
        self.assertEqual(
            result["integrity"]["changed_paths"], ["src/paged_sync/sync.py"]
        )
        self.assertTrue(result["tests"]["public"]["passed"])
        self.assertTrue(result["tests"]["hidden"]["passed"])

    def test_v1_2_changes_only_case_card_and_hidden_verifier_inputs(self) -> None:
        case_dir = self.repo_root / "tasks/coding/dev/pagination-cycle-guard"
        v1_1 = load_coding_case(
            self.repo_root, case_dir / "case-whole-file-v1.1.json"
        )
        v1_2 = load_coding_case(
            self.repo_root, case_dir / "case-whole-file-v1.2.json"
        )

        self.assertEqual(v1_2["case"]["case_version"], "1.2.0")
        self.assertEqual(v1_2["case"]["prompt"]["version"], "1.1.0")
        self.assertEqual(v1_2["case"]["verification"]["version"], "1.2.0")
        self.assertEqual(v1_1["task_sha256"], v1_2["task_sha256"])
        self.assertEqual(v1_1["system_message"], v1_2["system_message"])
        self.assertEqual(v1_1["manifest_sha256"], v1_2["manifest_sha256"])
        self.assertEqual(
            v1_1["case"]["candidate_context"],
            v1_2["case"]["candidate_context"],
        )
        self.assertEqual(v1_1["artifact_contract"], v1_2["artifact_contract"])
        self.assertEqual(
            v1_1["case"]["inference_defaults"],
            v1_2["case"]["inference_defaults"],
        )
        self.assertNotEqual(v1_1["hidden_test_sha256"], v1_2["hidden_test_sha256"])

    def test_v1_2_baseline_is_red_and_reference_is_green(self) -> None:
        case_path = Path(
            "tasks/coding/dev/pagination-cycle-guard/case-whole-file-v1.2.json"
        )

        baseline = audit_coding_case(self.repo_root, case_path)
        reference = verify_candidate_artifact(
            self.repo_root,
            case_path,
            REFERENCE_FILE_RESPONSE,
        )

        self.assertEqual(baseline["status"], "complete")
        self.assertTrue(baseline["baseline_expectations_met"])
        self.assertFalse(baseline["public_tests_pass"])
        self.assertFalse(baseline["hidden_tests_pass"])
        self.assertTrue(reference["verified_success"], reference)
        self.assertEqual(reference["verifier_version"], "1.2.0")
        self.assertIn("Ran 7 tests", reference["tests"]["hidden"]["stderr"])

    def test_v1_2_retrospective_replay_exposes_qwen_3_8_false_positive(
        self,
    ) -> None:
        case_path = Path(
            "tasks/coding/dev/pagination-cycle-guard/case-whole-file-v1.2.json"
        )
        response_path = (
            self.repo_root
            / "results/coding-runs/coding-run-20260901T195110Z-f85acf4e/response.txt"
        )
        if not response_path.exists():
            self.skipTest("gitignored local v1.1 candidate artifact is unavailable")

        result = verify_candidate_artifact(
            self.repo_root,
            case_path,
            response_path.read_text(encoding="utf-8"),
        )

        self.assertFalse(result["verified_success"])
        self.assertEqual(result["failure_code"], "hidden_tests_failed")
        self.assertIn(
            "test_cycle_back_to_nonempty_start_cursor_raises_before_refetch",
            result["tests"]["hidden"]["stderr"],
        )
        self.assertIn("FAILED (failures=1)", result["tests"]["hidden"]["stderr"])

    def test_whole_file_parser_rejects_prose_duplicates_and_protected_paths(
        self,
    ) -> None:
        loaded = load_coding_case(
            self.repo_root, DEFAULT_WHOLE_FILE_CODING_CASE_PATH
        )
        contract = loaded["artifact_contract"]
        cases = {
            "prose": (
                "Here is the file:\n" + REFERENCE_FILE_RESPONSE,
                "malformed_artifact",
            ),
            "duplicate": (
                REFERENCE_FILE_RESPONSE + "\n" + REFERENCE_FILE_RESPONSE,
                "malformed_artifact",
            ),
            "protected": (
                '<<<FILE path="tests/test_sync.py">>>\npass\n<<<END FILE>>>',
                "artifact_scope_violation",
            ),
        }

        for name, (response, failure_code) in cases.items():
            with self.subTest(name=name):
                parsed = parse_candidate_files(response, contract)
                self.assertEqual(parsed["output_status"], "malformed")
                self.assertEqual(parsed["failure_code"], failure_code)

    def test_whole_file_verifier_rejects_a_new_allowed_path(self) -> None:
        result = verify_candidate_artifact(
            self.repo_root,
            DEFAULT_WHOLE_FILE_CODING_CASE_PATH,
            '<<<FILE path="src/paged_sync/new.py">>>\npass\n<<<END FILE>>>',
        )

        self.assertEqual(result["output_status"], "valid")
        self.assertEqual(result["verification_status"], "failed")
        self.assertEqual(result["failure_code"], "artifact_scope_violation")
        self.assertEqual(
            result["artifact_install"]["missing_paths"],
            ["src/paged_sync/new.py"],
        )

    def test_unchanged_whole_file_reaches_the_deterministic_tests(self) -> None:
        baseline = (
            self.repo_root
            / "tasks/coding/dev/pagination-cycle-guard/fixture/src/paged_sync/sync.py"
        ).read_text(encoding="utf-8")
        response = (
            '<<<FILE path="src/paged_sync/sync.py">>>\n'
            + baseline.rstrip("\n")
            + "\n<<<END FILE>>>"
        )

        result = verify_candidate_artifact(
            self.repo_root,
            DEFAULT_WHOLE_FILE_CODING_CASE_PATH,
            response,
        )

        self.assertEqual(result["output_status"], "valid")
        self.assertEqual(result["failure_code"], "public_tests_failed")
        self.assertTrue(result["artifact_install"]["passed"])
        self.assertFalse(result["tests"]["public"]["passed"])
        self.assertFalse(result["verified_success"])

    def test_one_outer_diff_fence_is_normalized(self) -> None:
        loaded = load_coding_case(self.repo_root, DEFAULT_CODING_CASE_PATH)
        parsed = parse_candidate_patch(
            f"```diff\n{REFERENCE_PATCH.rstrip()}\n```",
            loaded["case"]["patch_contract"],
        )

        self.assertEqual(parsed["output_status"], "valid")
        self.assertTrue(parsed["outer_fence_removed"])

    def test_test_modification_is_rejected_before_application(self) -> None:
        loaded = load_coding_case(self.repo_root, DEFAULT_CODING_CASE_PATH)
        test_patch = textwrap.dedent(
            """\
            diff --git a/tests/test_sync.py b/tests/test_sync.py
            --- a/tests/test_sync.py
            +++ b/tests/test_sync.py
            @@ -1,1 +1,1 @@
            -\"\"\"Candidate-visible regression tests for paged_sync.\"\"\"
            +\"\"\"Weakened tests.\"\"\"
            """
        )

        parsed = parse_candidate_patch(test_patch, loaded["case"]["patch_contract"])

        self.assertEqual(parsed["output_status"], "malformed")
        self.assertEqual(parsed["failure_code"], "patch_scope_violation")

    def test_empty_output_is_preserved_as_a_failed_outcome(self) -> None:
        result = verify_candidate_patch(
            self.repo_root,
            DEFAULT_CODING_CASE_PATH,
            "",
        )

        self.assertEqual(result["output_status"], "empty")
        self.assertEqual(result["verification_status"], "unavailable")
        self.assertEqual(result["failure_code"], "empty_output")
        self.assertFalse(result["verified_success"])

    def test_direct_runner_persists_a_verified_outcome(self) -> None:
        class FakeOllamaClient:
            def __init__(self, host: str, timeout_seconds: float) -> None:
                self.host = host.rstrip("/") + "/"

            def version(self) -> dict[str, str]:
                return {"version": "test-ollama"}

            def list_models(self) -> dict[str, object]:
                return {
                    "models": [
                        {
                            "name": "test-model",
                            "digest": "a" * 64,
                            "size": 123,
                            "details": {"quantization_level": "test"},
                        }
                    ]
                }

            def show_model(self, model: str) -> dict[str, object]:
                return {
                    "capabilities": ["completion"],
                    "parameters": "test",
                    "template": "template",
                }

            def stream_chat(self, payload: dict[str, object]):
                yield {
                    "message": {"content": REFERENCE_PATCH},
                    "done": False,
                }
                yield {
                    "message": {"content": ""},
                    "done": True,
                    "done_reason": "stop",
                    "total_duration": 2_000_000_000,
                    "load_duration": 100_000_000,
                    "prompt_eval_count": 500,
                    "prompt_eval_duration": 1_000_000_000,
                    "eval_count": 200,
                    "eval_duration": 1_000_000_000,
                }

        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch(
                "local_llm_benchmark.coding.OllamaClient", FakeOllamaClient
            ):
                result = run_track_a_once(
                    self.repo_root,
                    CodingRunConfig(
                        model="test-model",
                        results_dir=Path(temporary_directory),
                    ),
                )

            record = json.loads(
                (Path(result["run_dir"]) / "run.json").read_text(encoding="utf-8")
            )
            verification = json.loads(
                (Path(result["run_dir"]) / "verification.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertTrue(result["verified_success"])
        self.assertEqual(record["track"], "A")
        self.assertEqual(record["outcome"]["task_status"], "verified_success")
        self.assertEqual(record["deployment"]["ollama_version"], "test-ollama")
        self.assertTrue(verification["tests"]["hidden"]["passed"])

    def test_direct_whole_file_runner_persists_candidate_files(self) -> None:
        class FakeOllamaClient:
            def __init__(self, host: str, timeout_seconds: float) -> None:
                self.host = host.rstrip("/") + "/"

            def version(self) -> dict[str, str]:
                return {"version": "test-ollama"}

            def list_models(self) -> dict[str, object]:
                return {
                    "models": [
                        {
                            "name": "test-model",
                            "digest": "b" * 64,
                            "size": 456,
                            "details": {"quantization_level": "test"},
                        }
                    ]
                }

            def show_model(self, model: str) -> dict[str, object]:
                return {
                    "capabilities": ["completion"],
                    "parameters": "test",
                    "template": "template",
                }

            def stream_chat(self, payload: dict[str, object]):
                yield {
                    "message": {"content": REFERENCE_FILE_RESPONSE},
                    "done": False,
                }
                yield {
                    "message": {"content": ""},
                    "done": True,
                    "done_reason": "stop",
                    "total_duration": 2_000_000_000,
                    "load_duration": 100_000_000,
                    "prompt_eval_count": 500,
                    "prompt_eval_duration": 1_000_000_000,
                    "eval_count": 200,
                    "eval_duration": 1_000_000_000,
                }

        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch(
                "local_llm_benchmark.coding.OllamaClient", FakeOllamaClient
            ):
                generated = run_track_a_once(
                    self.repo_root,
                    CodingRunConfig(
                        model="test-model",
                        case_path=DEFAULT_WHOLE_FILE_CODING_CASE_PATH,
                        results_dir=Path(temporary_directory),
                        defer_verification=True,
                    ),
                )

            self.assertEqual(generated["status"], "verification_pending")
            self.assertIsNone(generated["verified_success"])
            completed = finalize_deferred_track_a_run(
                self.repo_root, Path(generated["run_dir"])
            )
            run_dir = Path(generated["run_dir"])
            record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            manifest = json.loads(
                (run_dir / "candidate-files.json").read_text(encoding="utf-8")
            )
            candidate = (
                run_dir / "candidate-files/src/paged_sync/sync.py"
            ).read_text(encoding="utf-8")

            self.assertTrue(completed["verified_success"])
            self.assertEqual(
                record["harness"]["name"], "local_llm_benchmark.direct_files"
            )
            self.assertEqual(record["harness"]["version"], "1.1.0")
            self.assertEqual(
                record["case"]["artifact_format"], "whole_file_envelope"
            )
            self.assertEqual(
                manifest["files"][0]["path"], "src/paged_sync/sync.py"
            )
            self.assertEqual(candidate, REFERENCE_SYNC_FILE)
            self.assertEqual(record["verification_execution"]["mode"], "deferred")
            self.assertIsNotNone(record["verification_execution"]["completed_at"])

    def test_deferred_javascript_run_records_node_verifier_runtime(self) -> None:
        class FakeOllamaClient:
            def __init__(self, host: str, timeout_seconds: float) -> None:
                self.host = host.rstrip("/") + "/"

            def version(self) -> dict[str, str]:
                return {"version": "test-ollama"}

            def list_models(self) -> dict[str, object]:
                return {
                    "models": [
                        {
                            "name": "test-model",
                            "digest": "c" * 64,
                            "size": 789,
                            "details": {"quantization_level": "test"},
                        }
                    ]
                }

            def show_model(self, model: str) -> dict[str, object]:
                return {
                    "capabilities": ["completion"],
                    "parameters": "test",
                    "template": "template",
                }

            def stream_chat(self, payload: dict[str, object]):
                yield {
                    "message": {"content": REFERENCE_ASYNC_CACHE_RESPONSE},
                    "done": False,
                }
                yield {
                    "message": {"content": ""},
                    "done": True,
                    "done_reason": "stop",
                    "total_duration": 2_000_000_000,
                    "load_duration": 100_000_000,
                    "prompt_eval_count": 500,
                    "prompt_eval_duration": 1_000_000_000,
                    "eval_count": 200,
                    "eval_duration": 1_000_000_000,
                }

        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch(
                "local_llm_benchmark.coding.OllamaClient", FakeOllamaClient
            ):
                generated = run_track_a_once(
                    self.repo_root,
                    CodingRunConfig(
                        model="test-model",
                        case_path=ASYNC_CACHE_CASE_PATH,
                        results_dir=Path(temporary_directory),
                        defer_verification=True,
                    ),
                )

            completed = finalize_deferred_track_a_run(
                self.repo_root, Path(generated["run_dir"])
            )
            record = json.loads(
                (Path(generated["run_dir"]) / "run.json").read_text(
                    encoding="utf-8"
                )
            )

        runtime = record["verification_execution"]["runtime"]
        self.assertTrue(completed["verified_success"])
        self.assertTrue(runtime["passed"])
        self.assertTrue(runtime["stdout"].startswith("v"))


if __name__ == "__main__":
    unittest.main()
