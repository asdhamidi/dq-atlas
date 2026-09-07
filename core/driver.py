"""
Driver: the core that ports-and-adapters everything hangs off of. Depends
only on the ports (config loader, session, result logger, record fetcher)
and the CHECK_REGISTRY -- never on a specific check type's implementation
or a specific backend (Snowflake vs mock). Swapping the backend means
swapping which adapters get passed into the constructor; this file doesn't
change.

Stages per run:
  1. resolve   -- load config rows, explode into CheckInstances
  2. dispatch  -- look up each instance's check_type in CHECK_REGISTRY
  3. execute   -- run checks (optionally concurrently), isolating errors
  4. detail    -- fetch sample failed records for checks that failed
  5. log       -- batch-write results + run summary
  6. summarize -- return a RunSummary
"""
import uuid
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

from core.models import CheckInstance, CheckResult, RunSummary
from core.registry import CHECK_REGISTRY, resolve_check_instances
from core.errors import CheckExecutionError
from core.ports import ConfigLoaderPort, SessionPort, ResultLoggerPort, RecordFetcherPort

logger = logging.getLogger("dq_framework.driver")


class DQDriver:
    def __init__(self, config_loader: ConfigLoaderPort, session: SessionPort, result_logger: ResultLoggerPort, record_fetcher: RecordFetcherPort, max_workers: int = 8):
        self.config_loader = config_loader
        self.session = session
        self.result_logger = result_logger
        self.record_fetcher = record_fetcher
        self.max_workers = max_workers

    def run(
        self,
        check_id: Optional[str] = None,
        table_name: Optional[str] = None,
        schedule_group: Optional[str] = None,
        run_all: bool = False,
        concurrent: bool = True,
        detail_limit: int = 20,
    ) -> RunSummary:
        run_id = str(uuid.uuid4())
        batch_start = datetime.utcnow()

        # 1. resolve
        config_rows = self.config_loader.load_config_rows(
            check_id=check_id, table_name=table_name,
            schedule_group=schedule_group, run_all=run_all,
        )
        instances: List[CheckInstance] = []
        resolution_errors: List[CheckResult] = []
        for row in config_rows:
            # A malformed row (missing a required field, wrong type for a
            # list-typed field, etc.) must not abort the whole batch -- it
            # should surface as one ERROR result for that row, the same
            # isolation guarantee execution failures already get below.
            try:
                instances.extend(resolve_check_instances(row))
            except Exception as e:
                check_id = row.get("CHECK_ID", "UNKNOWN")
                logger.exception(
                    "Failed to resolve check instance(s) for CHECK_ID=%s", check_id
                )
                resolution_errors.append(CheckResult(
                    run_id=run_id,
                    check_id=str(check_id),
                    check_type="UNRESOLVED",
                    status="ERROR",
                    error_message=f"Config row resolution failed: {e}",
                ))

        logger.info(
            "Run %s: resolved %d check instance(s) from %d config row(s) (%d resolution error(s))",
            run_id, len(instances), len(config_rows), len(resolution_errors),
        )

        # 2 & 3. dispatch + execute
        if concurrent and len(instances) > 1:
            results = self._execute_concurrent(instances, run_id)
        else:
            results = [self._execute_one(inst, run_id) for inst in instances]
        results = resolution_errors + results

        # 4. detail fetch -- only for checks that actually failed, sequential
        #    since it's low volume by construction (only failing checks).
        for r in results:
            if r.status == "SUCCESS" and r.pass_fail_flag == "FAIL":
                inst = next(
                    (i for i in instances if i.check_id == r.check_id and i.check_type == r.check_type),
                    None,
                )
                if inst:
                    try:
                        r.sample_failed_keys = self.record_fetcher.fetch_failed_records(inst, limit=detail_limit)
                    except Exception as e:
                        logger.warning("Detail fetch failed for check %s (%s): %s", r.check_id, r.check_type, e)

        # 5. log -- one batched write for the whole run, not one per check
        self.result_logger.log_results(results)

        summary = RunSummary(
            run_id=run_id,
            schedule_group=schedule_group,
            batch_start=batch_start,
            batch_end=datetime.utcnow(),
            checks_attempted=len(results),
            checks_passed=sum(1 for r in results if r.pass_fail_flag == "PASS"),
            checks_failed=sum(1 for r in results if r.pass_fail_flag == "FAIL"),
            checks_errored=sum(1 for r in results if r.status == "ERROR"),
        )
        summary.overall_status = (
            "ERROR" if summary.checks_errored else ("FAIL" if summary.checks_failed else "SUCCESS")
        )
        self.result_logger.log_run_summary(summary)
        return summary

    def _execute_concurrent(self, instances: List[CheckInstance], run_id: str) -> List[CheckResult]:
        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(self._execute_one, inst, run_id): inst for inst in instances}
            for future in as_completed(futures):
                # _execute_one already catches exceptions internally and
                # converts them into ERROR CheckResults, so this branch
                # should not normally trigger -- it's a guard so one truly
                # unexpected failure never silently drops a result from
                # the batch.
                try:
                    results.append(future.result())
                except Exception as e:
                    inst = futures[future]
                    logger.exception("Unhandled failure running check %s", inst.check_id)
                    results.append(self._error_result(inst, run_id, str(e), None))
        return results

    def _execute_one(self, instance: CheckInstance, run_id: str) -> CheckResult:
        check_fn = CHECK_REGISTRY.get(instance.check_type)
        if check_fn is None:
            return self._error_result(
                instance, run_id, f"No registered check function for type '{instance.check_type}'", None
            )
        try:
            return check_fn(instance, self.session, run_id)
        except CheckExecutionError as e:
            return self._error_result(instance, run_id, str(e), e.rendered_sql)
        except Exception as e:
            logger.exception("Unexpected error running check %s (%s)", instance.check_id, instance.check_type)
            return self._error_result(instance, run_id, str(e), None)

    @staticmethod
    def _error_result(instance: CheckInstance, run_id: str, message: str, rendered_sql) -> CheckResult:
        return CheckResult(
            run_id=run_id,
            check_id=instance.check_id,
            check_type=instance.check_type,
            status="ERROR",
            criticality=instance.criticality,
            check_status_at_run=instance.check_status,
            rendered_sql=rendered_sql,
            error_message=message,
        )
