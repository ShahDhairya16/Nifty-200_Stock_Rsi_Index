from datetime import date
from typing import Dict, Any, List, Optional, Union
from sqlalchemy.orm import Session

from app.database.connection import get_db_session
from app.database.repositories import (
    JobRunRepository,
    JobErrorRepository,
    StockRepository
)
from app.services.stock_universe_service import StockUniverseService
from app.services.historical_data_service import HistoricalDataService
from app.services.bhavcopy_service import BhavcopyService
from app.services.missing_data_service import MissingDataService
from app.utils.date_utils import parse_date, format_date_iso
from app.utils.logger import logger

class IngestionService:
    """
    Orchestrator for all data ingestion workflows.
    Manages job runs, logs stock-level errors, and maintains operational traceability.
    """

    @staticmethod
    def sync_stock_universe() -> Dict[str, Any]:
        """
        Orchestrates NIFTY 200 universe synchronization with full DB job tracking.
        """
        with get_db_session() as session:
            job_run = JobRunRepository.create_job_run(
                session=session,
                job_name="NIFTY200_UNIVERSE_SYNC",
                run_date=date.today(),
                expected_stocks=200
            )

            try:
                summary = StockUniverseService.sync_nifty200_universe(session)
                
                status = "SUCCESS"
                if summary["errors"]:
                    status = "PARTIAL_SUCCESS"
                    for err in summary["errors"]:
                        JobErrorRepository.log_job_error(
                            session=session,
                            job_run_id=job_run.id,
                            error_type="UNIVERSE_SYNC_ERROR",
                            error_message=str(err)
                        )

                JobRunRepository.complete_job_run(
                    session=session,
                    job_run_id=job_run.id,
                    status=status,
                    successful_stocks=summary["updated_stocks"] + summary["new_stocks"],
                    failed_stocks=len(summary["errors"]),
                    error_message="; ".join(summary["errors"]) if summary["errors"] else None
                )
                
                summary["job_run_id"] = job_run.id
                return summary

            except Exception as e:
                logger.error(f"Critical failure in NIFTY 200 universe sync job: {e}")
                JobErrorRepository.log_job_error(
                    session=session,
                    job_run_id=job_run.id,
                    error_type="CRITICAL_UNIVERSE_SYNC_FAILURE",
                    error_message=str(e)
                )
                JobRunRepository.complete_job_run(
                    session=session,
                    job_run_id=job_run.id,
                    status="FAILED",
                    error_message=str(e)
                )
                raise

    @staticmethod
    def backfill_historical_data(
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
        symbols: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Orchestrates historical daily price backfill across active stocks with full DB job tracking.
        """
        with get_db_session() as session:
            active_stocks = StockRepository.get_all_active_stocks(session)
            expected_count = len(symbols) if symbols else len(active_stocks)
            stock_id_map = {s.symbol: s.id for s in active_stocks}

            job_run = JobRunRepository.create_job_run(
                session=session,
                job_name="NIFTY200_HISTORICAL_BACKFILL",
                run_date=date.today(),
                expected_stocks=expected_count
            )

            try:
                summary = HistoricalDataService.backfill_historical_data(
                    start_date=start_date,
                    end_date=end_date,
                    symbols=symbols,
                    session=session
                )

                # Track individual stock errors in job_errors table
                if summary["errors"]:
                    for err in summary["errors"]:
                        sym = err.get("symbol")
                        stk_id = stock_id_map.get(sym) if sym else None
                        JobErrorRepository.log_job_error(
                            session=session,
                            job_run_id=job_run.id,
                            stock_id=stk_id,
                            error_type="HISTORICAL_BACKFILL_ERROR",
                            error_message=err.get("error", "Unknown error")
                        )

                # Determine final status
                if summary["failed_stocks"] == 0:
                    final_status = "SUCCESS"
                elif summary["successful_stocks"] > 0:
                    final_status = "PARTIAL_SUCCESS"
                else:
                    final_status = "FAILED"

                JobRunRepository.complete_job_run(
                    session=session,
                    job_run_id=job_run.id,
                    status=final_status,
                    successful_stocks=summary["successful_stocks"],
                    failed_stocks=summary["failed_stocks"],
                    error_message=f"{len(summary['errors'])} stock failures occurred during backfill." if summary["errors"] else None
                )

                summary["job_run_id"] = job_run.id
                return summary

            except Exception as e:
                logger.error(f"Critical failure in historical backfill job: {e}")
                JobErrorRepository.log_job_error(
                    session=session,
                    job_run_id=job_run.id,
                    error_type="CRITICAL_HISTORICAL_BACKFILL_FAILURE",
                    error_message=str(e)
                )
                JobRunRepository.complete_job_run(
                    session=session,
                    job_run_id=job_run.id,
                    status="FAILED",
                    error_message=str(e)
                )
                raise

    @staticmethod
    def update_missing_market_data(
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None
    ) -> Dict[str, Any]:
        """
        Scans database for missing trading dates and triggers targeted historical backfill to fill gaps.
        """
        with get_db_session() as session:
            job_run = JobRunRepository.create_job_run(
                session=session,
                job_name="NIFTY200_MISSING_DATA_RECOVERY",
                run_date=date.today(),
                expected_stocks=200
            )

            try:
                parsed_start = parse_date(start_date)
                parsed_end = parse_date(end_date) or date.today()

                gap_summary = MissingDataService.get_missing_dates_summary(
                    start_date=parsed_start,
                    end_date=parsed_end,
                    session=session
                )

                stocks_with_gaps = list(gap_summary["gap_details"].keys())

                if not stocks_with_gaps:
                    logger.info("No missing trading data detected. Database is fully up to date.")
                    JobRunRepository.complete_job_run(
                        session=session,
                        job_run_id=job_run.id,
                        status="SUCCESS",
                        successful_stocks=200,
                        failed_stocks=0,
                        error_message="No missing data detected."
                    )
                    return {"status": "SUCCESS", "message": "No missing data detected."}

                logger.info(f"Detected {len(stocks_with_gaps)} stocks with missing trading dates. Executing targeted recovery...")

                backfill_res = HistoricalDataService.backfill_historical_data(
                    start_date=parsed_start,
                    end_date=parsed_end,
                    symbols=stocks_with_gaps,
                    session=session
                )

                final_status = "SUCCESS" if backfill_res["failed_stocks"] == 0 else "PARTIAL_SUCCESS"

                JobRunRepository.complete_job_run(
                    session=session,
                    job_run_id=job_run.id,
                    status=final_status,
                    successful_stocks=backfill_res["successful_stocks"],
                    failed_stocks=backfill_res["failed_stocks"],
                    error_message=f"Missing data recovery completed with {backfill_res['failed_stocks']} stock failures."
                )

                return backfill_res

            except Exception as e:
                logger.error(f"Critical failure during missing data recovery job: {e}")
                JobErrorRepository.log_job_error(
                    session=session,
                    job_run_id=job_run.id,
                    error_type="CRITICAL_MISSING_DATA_RECOVERY_FAILURE",
                    error_message=str(e)
                )
                JobRunRepository.complete_job_run(
                    session=session,
                    job_run_id=job_run.id,
                    status="FAILED",
                    error_message=str(e)
                )
                raise
