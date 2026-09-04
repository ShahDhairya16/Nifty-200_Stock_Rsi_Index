from datetime import date, datetime
from typing import Optional, List
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Numeric,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    """Base Declarative Class for all SQLAlchemy ORM models."""
    pass

class StockMaster(Base):
    """
    Table storing stock universe metadata (e.g. NIFTY 200 constituents).
    """
    __tablename__ = "stock_master"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    company_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    exchange: Mapped[str] = mapped_column(String(20), default="NSE", nullable=False)
    series: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    added_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    removed_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    prices: Mapped[List["DailyPrice"]] = relationship(
        "DailyPrice", back_populates="stock", cascade="all, delete-orphan"
    )
    job_errors: Mapped[List["JobError"]] = relationship("JobError", back_populates="stock")
    fetch_logs: Mapped[List["DataFetchLog"]] = relationship(
        "DataFetchLog", back_populates="stock", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<StockMaster(id={self.id}, symbol='{self.symbol}', active={self.active})>"


class DailyPrice(Base):
    """
    Table storing historical daily OHLCV price data for stocks.
    Database-level UNIQUE constraint on (stock_id, trade_date) prevents duplicates.
    """
    __tablename__ = "daily_prices"
    __table_args__ = (
        UniqueConstraint("stock_id", "trade_date", name="uq_stock_trade_date"),
        Index("ix_daily_prices_stock_id", "stock_id"),
        Index("ix_daily_prices_trade_date", "trade_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stock_master.id", ondelete="RESTRICT"), nullable=False
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    open_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 4), nullable=True)
    high_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 4), nullable=True)
    low_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 4), nullable=True)
    close_price: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    volume: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    stock: Mapped["StockMaster"] = relationship("StockMaster", back_populates="prices")

    def __repr__(self) -> str:
        return f"<DailyPrice(stock_id={self.stock_id}, trade_date={self.trade_date}, close={self.close_price})>"


class JobRun(Base):
    """
    Table tracking every automated job execution.
    """
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_name: Mapped[str] = mapped_column(String(100), nullable=False)
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expected_stocks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_stocks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_stocks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="STARTED")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    errors: Mapped[List["JobError"]] = relationship(
        "JobError", back_populates="job_run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<JobRun(id={self.id}, job_name='{self.job_name}', status='{self.status}')>"


class JobError(Base):
    """
    Table storing granular error details for individual job runs and stocks.
    """
    __tablename__ = "job_errors"
    __table_args__ = (
        Index("ix_job_errors_job_run_id", "job_run_id"),
        Index("ix_job_errors_stock_id", "stock_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("job_runs.id", ondelete="CASCADE"), nullable=False
    )
    stock_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("stock_master.id", ondelete="SET NULL"), nullable=True
    )
    error_type: Mapped[str] = mapped_column(String(100), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    retry_attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    job_run: Mapped["JobRun"] = relationship("JobRun", back_populates="errors")
    stock: Mapped[Optional["StockMaster"]] = relationship("StockMaster", back_populates="job_errors")

    def __repr__(self) -> str:
        return f"<JobError(id={self.id}, job_run_id={self.job_run_id}, error_type='{self.error_type}')>"


class DataFetchLog(Base):
    """
    Audit log dedicated to market data fetching activities per stock and date.
    """
    __tablename__ = "data_fetch_log"
    __table_args__ = (
        Index("ix_data_fetch_log_stock_date", "stock_id", "trade_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stock_master.id", ondelete="CASCADE"), nullable=False
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    fetch_status: Mapped[str] = mapped_column(String(50), nullable=False)  # SUCCESS, FAILED, SKIPPED
    source: Mapped[str] = mapped_column(String(50), nullable=False)        # NSELIB, NSE_BHAVCOPY, HISTORICAL_API
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    stock: Mapped["StockMaster"] = relationship("StockMaster", back_populates="fetch_logs")

    def __repr__(self) -> str:
        return f"<DataFetchLog(stock_id={self.stock_id}, trade_date={self.trade_date}, status='{self.fetch_status}')>"


class StockRSIMetrics(Base):
    """
    Table storing calculated RSI metrics (RSI 22, RSI 44, RSI 66, and Average RSI) per stock and date.
    Database-level UNIQUE constraint on (stock_id, trade_date) prevents duplicate calculations.
    """
    __tablename__ = "stock_rsi_metrics"
    __table_args__ = (
        UniqueConstraint("stock_id", "trade_date", name="uq_rsi_stock_trade_date"),
        Index("ix_stock_rsi_metrics_stock_id", "stock_id"),
        Index("ix_stock_rsi_metrics_trade_date", "trade_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stock_master.id", ondelete="CASCADE"), nullable=False
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    rsi_22: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), nullable=True)
    rsi_44: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), nullable=True)
    rsi_66: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), nullable=True)
    average_rsi: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), nullable=True)
    calculation_status: Mapped[str] = mapped_column(String(30), default="SUCCESS", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    stock: Mapped["StockMaster"] = relationship("StockMaster")

    def __repr__(self) -> str:
        return f"<StockRSIMetrics(stock_id={self.stock_id}, trade_date={self.trade_date}, avg_rsi={self.average_rsi})>"

