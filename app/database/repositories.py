from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import select, func, and_, or_, cast, Date
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session
from app.database.models import StockMaster, DailyPrice, JobRun, JobError, DataFetchLog, StockRSIMetrics
from app.utils.logger import logger

class StockRepository:
    """Repository handling database operations for stock_master."""

    @staticmethod
    def add_stock(
        session: Session,
        symbol: str,
        company_name: Optional[str] = None,
        exchange: str = "NSE",
        series: Optional[str] = "EQ",
        active: bool = True,
        added_date: Optional[date] = None
    ) -> StockMaster:
        """
        Inserts a single stock or returns existing stock if symbol already exists.
        """
        symbol_clean = symbol.strip().upper()
        existing = session.scalar(select(StockMaster).where(StockMaster.symbol == symbol_clean))
        if existing:
            logger.info(f"Stock '{symbol_clean}' already exists in stock_master (ID: {existing.id}).")
            return existing

        stock = StockMaster(
            symbol=symbol_clean,
            company_name=company_name,
            exchange=exchange,
            series=series,
            active=active,
            added_date=added_date or date.today()
        )
        session.add(stock)
        session.flush()
        logger.info(f"Added stock '{symbol_clean}' to stock_master (ID: {stock.id}).")
        return stock

    @staticmethod
    def get_stock_by_symbol(session: Session, symbol: str) -> Optional[StockMaster]:
        """Retrieves stock record by symbol."""
        symbol_clean = symbol.strip().upper()
        return session.scalar(select(StockMaster).where(StockMaster.symbol == symbol_clean))

    @staticmethod
    def get_all_active_stocks(session: Session) -> List[StockMaster]:
        """Retrieves list of all active stocks."""
        return list(session.scalars(select(StockMaster).where(StockMaster.active == True).order_by(StockMaster.symbol)).all())

    @staticmethod
    def get_all_stocks(session: Session) -> List[StockMaster]:
        """Retrieves all stocks ordered by symbol for frontend selectors and status views."""
        return list(session.scalars(select(StockMaster).order_by(StockMaster.symbol)).all())

    @staticmethod
    def update_stock_status(
        session: Session, symbol: str, active: bool, removed_date: Optional[date] = None
    ) -> Optional[StockMaster]:
        """
        Updates the active status of a stock without deleting historical data.
        """
        stock = StockRepository.get_stock_by_symbol(session, symbol)
        if stock:
            stock.active = active
            if not active:
                stock.removed_date = removed_date or date.today()
            else:
                stock.removed_date = None
            session.flush()
            logger.info(f"Updated stock '{stock.symbol}' active status to {active}.")
        return stock

    @staticmethod
    def bulk_insert_stocks(session: Session, stocks_data: List[Dict[str, Any]]) -> int:
        """
        Bulk inserts or updates stocks using MySQL ON DUPLICATE KEY UPDATE.
        Returns total count of processed stocks.
        """
        if not stocks_data:
            return 0

        # Prepare values
        insert_dicts = []
        today = date.today()
        for item in stocks_data:
            insert_dicts.append({
                "symbol": item["symbol"].strip().upper(),
                "company_name": item.get("company_name"),
                "exchange": item.get("exchange", "NSE"),
                "series": item.get("series", "EQ"),
                "active": item.get("active", True),
                "added_date": item.get("added_date", today),
            })

        stmt = mysql_insert(StockMaster).values(insert_dicts)
        update_cols = {
            "company_name": stmt.inserted.company_name,
            "exchange": stmt.inserted.exchange,
            "series": stmt.inserted.series,
            "active": stmt.inserted.active,
        }
        upsert_stmt = stmt.on_duplicate_key_update(**update_cols)
        session.execute(upsert_stmt)
        session.flush()
        session.expire_all()
        logger.info(f"Bulk upserted {len(insert_dicts)} stock records into stock_master.")
        return len(insert_dicts)


class DailyPriceRepository:
    """Repository handling database operations for daily_prices."""

    @staticmethod
    def insert_daily_price(
        session: Session,
        stock_id: int,
        trade_date: date,
        close_price: float,
        open_price: Optional[float] = None,
        high_price: Optional[float] = None,
        low_price: Optional[float] = None,
        volume: Optional[int] = None
    ) -> DailyPrice:
        """
        Inserts or updates a single daily price record using MySQL UPSERT.
        """
        data_dict = [{
            "stock_id": stock_id,
            "trade_date": trade_date,
            "open_price": open_price,
            "high_price": high_price,
            "low_price": low_price,
            "close_price": close_price,
            "volume": volume,
        }]
        DailyPriceRepository.bulk_insert_daily_prices(session, data_dict)
        return session.scalar(
            select(DailyPrice).where(
                and_(DailyPrice.stock_id == stock_id, DailyPrice.trade_date == trade_date)
            )
        )

    @staticmethod
    def bulk_insert_daily_prices(session: Session, price_dicts: List[Dict[str, Any]]) -> int:
        """
        Bulk inserts or updates daily price records using MySQL ON DUPLICATE KEY UPDATE.
        Guarantees idempotency and duplicate prevention at DB level.
        """
        if not price_dicts:
            return 0

        stmt = mysql_insert(DailyPrice).values(price_dicts)
        upsert_stmt = stmt.on_duplicate_key_update(
            open_price=stmt.inserted.open_price,
            high_price=stmt.inserted.high_price,
            low_price=stmt.inserted.low_price,
            close_price=stmt.inserted.close_price,
            volume=stmt.inserted.volume,
            updated_at=func.now()
        )
        session.execute(upsert_stmt)
        session.flush()
        session.expire_all()
        logger.info(f"Bulk upserted {len(price_dicts)} price records into daily_prices.")
        return len(price_dicts)

    @staticmethod
    def get_latest_price_date(session: Session, stock_id: Optional[int] = None) -> Optional[date]:
        """
        Returns the latest trade_date available for a specific stock or overall across all stocks.
        """
        query = select(func.max(DailyPrice.trade_date))
        if stock_id:
            query = query.where(DailyPrice.stock_id == stock_id)
        return session.scalar(query)

    @staticmethod
    def get_prices_by_stock(
        session: Session,
        stock_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[DailyPrice]:
        """Retrieves price records for a stock within an optional date range."""
        query = select(DailyPrice).where(DailyPrice.stock_id == stock_id)
        if start_date:
            query = query.where(DailyPrice.trade_date >= start_date)
        if end_date:
            query = query.where(DailyPrice.trade_date <= end_date)
        query = query.order_by(DailyPrice.trade_date.asc())
        return list(session.scalars(query).all())

    @staticmethod
    def get_stock_history_with_rsi(session: Session, stock_id: int) -> List[Dict[str, Any]]:
        """Retrieves one stock's OHLCV history with stored RSI metrics in one query."""
        query = (
            select(
                DailyPrice.trade_date, DailyPrice.open_price, DailyPrice.high_price,
                DailyPrice.low_price, DailyPrice.close_price, DailyPrice.volume,
                StockRSIMetrics.rsi_22, StockRSIMetrics.rsi_44,
                StockRSIMetrics.rsi_66, StockRSIMetrics.average_rsi
            )
            .outerjoin(
                StockRSIMetrics,
                and_(DailyPrice.stock_id == StockRSIMetrics.stock_id,
                     DailyPrice.trade_date == StockRSIMetrics.trade_date)
            )
            .where(DailyPrice.stock_id == stock_id)
            .order_by(DailyPrice.trade_date.asc())
        )
        rows = session.execute(query).all()
        return [
            {
                "trade_date": row.trade_date,
                "open_price": float(row.open_price) if row.open_price is not None else None,
                "high_price": float(row.high_price) if row.high_price is not None else None,
                "low_price": float(row.low_price) if row.low_price is not None else None,
                "close_price": float(row.close_price) if row.close_price is not None else None,
                "volume": int(row.volume) if row.volume is not None else None,
                "rsi_22": float(row.rsi_22) if row.rsi_22 is not None else None,
                "rsi_44": float(row.rsi_44) if row.rsi_44 is not None else None,
                "rsi_66": float(row.rsi_66) if row.rsi_66 is not None else None,
                "average_rsi": float(row.average_rsi) if row.average_rsi is not None else None,
            }
            for row in rows
        ]

    @staticmethod
    def get_price_coverage(session: Session) -> List[Dict[str, Any]]:
        """Retrieves price and RSI coverage for every stock in one grouped query."""
        price_counts = (
            select(DailyPrice.stock_id, func.count(DailyPrice.id).label("price_count"),
                   func.min(DailyPrice.trade_date).label("earliest_date"),
                   func.max(DailyPrice.trade_date).label("latest_date"))
            .group_by(DailyPrice.stock_id).subquery()
        )
        rsi_counts = (
            select(StockRSIMetrics.stock_id, func.count(StockRSIMetrics.id).label("rsi_count"))
            .group_by(StockRSIMetrics.stock_id).subquery()
        )
        query = (
            select(StockMaster.symbol, StockMaster.company_name, price_counts.c.price_count,
                   price_counts.c.earliest_date, price_counts.c.latest_date,
                   func.coalesce(rsi_counts.c.rsi_count, 0).label("rsi_count"))
            .outerjoin(price_counts, StockMaster.id == price_counts.c.stock_id)
            .outerjoin(rsi_counts, StockMaster.id == rsi_counts.c.stock_id)
            .order_by(StockMaster.symbol)
        )
        return [
            {"symbol": row.symbol, "company_name": row.company_name or row.symbol,
             "price_count": int(row.price_count or 0), "earliest_date": row.earliest_date,
             "latest_date": row.latest_date, "rsi_count": int(row.rsi_count or 0),
             "active": None}
            for row in session.execute(query).all()
        ]

    @staticmethod
    def get_prices_by_date(session: Session, trade_date: date) -> List[DailyPrice]:
        """Retrieves price records for all stocks on a specific trade date."""
        return list(
            session.scalars(
                select(DailyPrice).where(DailyPrice.trade_date == trade_date)
            ).all()
        )

    @staticmethod
    def get_missing_dates(
        session: Session, stock_id: int, start_date: date, end_date: date
    ) -> List[date]:
        """
        Returns a list of missing trading dates for a stock between start_date and end_date.
        Trading dates are identified as dates where ANY active stock has price records.
        """
        # Fetch all distinct trading dates in system within range
        system_trading_dates_query = select(DailyPrice.trade_date).where(
            and_(DailyPrice.trade_date >= start_date, DailyPrice.trade_date <= end_date)
        ).distinct()
        system_dates = set(session.scalars(system_trading_dates_query).all())

        # Fetch existing dates for this specific stock
        stock_dates_query = select(DailyPrice.trade_date).where(
            and_(
                DailyPrice.stock_id == stock_id,
                DailyPrice.trade_date >= start_date,
                DailyPrice.trade_date <= end_date
            )
        )
        stock_dates = set(session.scalars(stock_dates_query).all())

        missing = sorted(list(system_dates - stock_dates))
        return missing

    @staticmethod
    def get_last_n_trading_days(session: Session, n: int = 70) -> List[date]:
        """
        Retrieves the latest N distinct trading dates across all system stock price records.
        Returns dates sorted in ascending order (oldest to newest).
        """
        query = (
            select(DailyPrice.trade_date)
            .distinct()
            .order_by(DailyPrice.trade_date.desc())
            .limit(n)
        )
        desc_dates = list(session.scalars(query).all())
        return sorted(desc_dates)

    @staticmethod
    def get_closing_price_matrix_data(session: Session, trading_dates: List[date]) -> List[Dict[str, Any]]:
        """
        Retrieves closing price records for all active stocks across the specified trading dates.
        Returns list of dicts: [{'trade_date': date, 'symbol': str, 'close_price': float}]
        """
        if not trading_dates:
            return []

        query = (
            select(
                DailyPrice.trade_date,
                StockMaster.symbol,
                DailyPrice.close_price
            )
            .join(StockMaster, StockMaster.id == DailyPrice.stock_id)
            .where(
                and_(
                    DailyPrice.trade_date.in_(trading_dates),
                    StockMaster.active == True
                )
            )
            .order_by(DailyPrice.trade_date.asc(), StockMaster.symbol.asc())
        )
        
        results = session.execute(query).all()
        return [
            {
                "trade_date": row.trade_date,
                "symbol": row.symbol,
                "close_price": float(row.close_price)
            }
            for row in results
        ]


class JobRunRepository:
    """Repository handling execution tracking in job_runs."""

    @staticmethod
    def create_job_run(
        session: Session, job_name: str, run_date: date, expected_stocks: int = 0
    ) -> JobRun:
        """Creates a new job run entry with status STARTED."""
        job_run = JobRun(
            job_name=job_name,
            run_date=run_date,
            started_at=datetime.now(),
            expected_stocks=expected_stocks,
            status="STARTED"
        )
        session.add(job_run)
        session.flush()
        logger.info(f"Created JobRun '{job_name}' (ID: {job_run.id}).")
        return job_run

    @staticmethod
    def update_job_status(
        session: Session,
        job_run_id: int,
        status: str,
        successful_stocks: Optional[int] = None,
        failed_stocks: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> Optional[JobRun]:
        """Updates status and counter metrics for an existing job run."""
        job_run = session.get(JobRun, job_run_id)
        if job_run:
            job_run.status = status
            if successful_stocks is not None:
                job_run.successful_stocks = successful_stocks
            if failed_stocks is not None:
                job_run.failed_stocks = failed_stocks
            if error_message is not None:
                job_run.error_message = error_message
            session.flush()
            logger.info(f"Updated JobRun ID {job_run_id} status to '{status}'.")
        return job_run

    @staticmethod
    def complete_job_run(
        session: Session,
        job_run_id: int,
        status: str,
        successful_stocks: int = 0,
        failed_stocks: int = 0,
        error_message: Optional[str] = None
    ) -> Optional[JobRun]:
        """Marks a job run as completed with final timestamp and metrics."""
        job_run = session.get(JobRun, job_run_id)
        if job_run:
            job_run.status = status
            job_run.completed_at = datetime.now()
            job_run.successful_stocks = successful_stocks
            job_run.failed_stocks = failed_stocks
            job_run.error_message = error_message
            session.flush()
            logger.info(f"Completed JobRun ID {job_run_id} with status '{status}'.")
        return job_run

    @staticmethod
    def get_recent_job_runs(session: Session, limit: int = 20) -> List[JobRun]:
        """Retrieves recent job runs for operational status display."""
        return list(session.scalars(
            select(JobRun).order_by(JobRun.started_at.desc()).limit(limit)
        ).all())


class JobErrorRepository:
    """Repository handling detailed error logs in job_errors."""

    @staticmethod
    def log_job_error(
        session: Session,
        job_run_id: int,
        error_type: str,
        error_message: str,
        stock_id: Optional[int] = None,
        retry_attempt: int = 0
    ) -> JobError:
        """Logs a failure entry associated with a job run."""
        job_error = JobError(
            job_run_id=job_run_id,
            stock_id=stock_id,
            error_type=error_type,
            error_message=error_message,
            retry_attempt=retry_attempt
        )
        session.add(job_error)
        session.flush()
        logger.warning(f"Logged JobError for JobRun ID {job_run_id} (Type: {error_type}).")
        return job_error

    @staticmethod
    def get_errors_by_job_run(session: Session, job_run_id: int) -> List[JobError]:
        """Retrieves all error entries for a specific job run."""
        return list(
            session.scalars(
                select(JobError).where(JobError.job_run_id == job_run_id)
            ).all()
        )

    @staticmethod
    def get_recent_errors(session: Session, limit: int = 20) -> List[JobError]:
        """Retrieves recent job errors without exposing extra system details."""
        return list(session.scalars(
            select(JobError).order_by(JobError.created_at.desc()).limit(limit)
        ).all())


class DataFetchLogRepository:
    """Repository handling raw data fetch attempt logs."""

    @staticmethod
    def log_fetch_attempt(
        session: Session,
        stock_id: int,
        trade_date: date,
        fetch_status: str,
        source: str = "NSELIB",
        message: Optional[str] = None
    ) -> DataFetchLog:
        """Logs a market data fetch attempt."""
        log_entry = DataFetchLog(
            stock_id=stock_id,
            trade_date=trade_date,
            fetch_status=fetch_status,
            source=source,
            fetched_at=datetime.now(),
            message=message
        )
        session.add(log_entry)
        session.flush()
        return log_entry

    @staticmethod
    def get_fetch_logs(
        session: Session, stock_id: Optional[int] = None, trade_date: Optional[date] = None
    ) -> List[DataFetchLog]:
        """Retrieves fetch logs matching criteria."""
        query = select(DataFetchLog)
        if stock_id:
            query = query.where(DataFetchLog.stock_id == stock_id)
        if trade_date:
            query = query.where(DataFetchLog.trade_date == trade_date)
        return list(session.scalars(query.order_by(DataFetchLog.fetched_at.desc())).all())


class RSIMetricsRepository:
    """Repository handling database operations for stock_rsi_metrics."""

    @staticmethod
    def bulk_insert_rsi_metrics(session: Session, metrics_dicts: List[Dict[str, Any]]) -> int:
        """
        Bulk inserts or updates RSI calculation metrics using MySQL ON DUPLICATE KEY UPDATE.
        Guarantees idempotency and prevents duplicates for (stock_id, trade_date).
        """
        if not metrics_dicts:
            return 0

        stmt = mysql_insert(StockRSIMetrics).values(metrics_dicts)
        upsert_stmt = stmt.on_duplicate_key_update(
            rsi_22=stmt.inserted.rsi_22,
            rsi_44=stmt.inserted.rsi_44,
            rsi_66=stmt.inserted.rsi_66,
            average_rsi=stmt.inserted.average_rsi,
            calculation_status=stmt.inserted.calculation_status,
            updated_at=func.now()
        )
        session.execute(upsert_stmt)
        session.flush()
        session.expire_all()
        logger.info(f"Bulk upserted {len(metrics_dicts)} RSI metrics into stock_rsi_metrics.")
        return len(metrics_dicts)

    @staticmethod
    def get_rsi_metrics_by_stock(
        session: Session,
        stock_id: int,
        limit: Optional[int] = None
    ) -> List[StockRSIMetrics]:
        """Retrieves calculated RSI records for a stock ordered by trade date ascending."""
        query = (
            select(StockRSIMetrics)
            .where(StockRSIMetrics.stock_id == stock_id)
            .order_by(StockRSIMetrics.trade_date.asc())
        )
        if limit:
            query = query.limit(limit)
        return list(session.scalars(query).all())

    @staticmethod
    def get_latest_rsi_metric(session: Session, stock_id: int) -> Optional[StockRSIMetrics]:
        """Retrieves the latest calculated RSI record for a stock."""
        return session.scalar(
            select(StockRSIMetrics)
            .where(StockRSIMetrics.stock_id == stock_id)
            .order_by(StockRSIMetrics.trade_date.desc())
            .limit(1)
        )

    @staticmethod
    def get_latest_rsi_rankings(session: Session) -> List[Dict[str, Any]]:
        """
        Retrieves the latest calculated RSI metrics for all active stocks sorted by average_rsi DESC.
        Returns list of dicts with symbol, company_name, trade_date, rsi_22, rsi_44, rsi_66, average_rsi.
        """
        # Subquery for max trade_date per stock_id
        subq = (
            select(
                StockRSIMetrics.stock_id,
                func.max(StockRSIMetrics.trade_date).label("max_date")
            )
            .group_by(StockRSIMetrics.stock_id)
            .subquery()
        )

        query = (
            select(
                StockMaster.symbol,
                StockMaster.company_name,
                StockRSIMetrics.trade_date,
                StockRSIMetrics.rsi_22,
                StockRSIMetrics.rsi_44,
                StockRSIMetrics.rsi_66,
                StockRSIMetrics.average_rsi
            )
            .join(StockRSIMetrics, StockMaster.id == StockRSIMetrics.stock_id)
            .join(
                subq,
                and_(
                    StockRSIMetrics.stock_id == subq.c.stock_id,
                    StockRSIMetrics.trade_date == subq.c.max_date
                )
            )
            .where(StockMaster.active == True)
            .order_by(StockRSIMetrics.average_rsi.desc())
        )

        results = session.execute(query).all()
        return [
            {
                "symbol": row.symbol,
                "company_name": row.company_name or row.symbol,
                "trade_date": row.trade_date,
                "rsi_22": float(row.rsi_22) if row.rsi_22 is not None else None,
                "rsi_44": float(row.rsi_44) if row.rsi_44 is not None else None,
                "rsi_66": float(row.rsi_66) if row.rsi_66 is not None else None,
                "average_rsi": float(row.average_rsi) if row.average_rsi is not None else None
            }
            for row in results
        ]

