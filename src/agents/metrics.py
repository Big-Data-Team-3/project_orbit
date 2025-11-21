"""
Metrics and counters for agentic dashboard generation.

Tracks:
- dashboards_generated: Number of dashboards successfully generated
- hitl_triggered: Number of times HITL approval was requested
"""

import logging
import os
from typing import Optional
from threading import Lock
from datetime import datetime
from pathlib import Path
import json

logger = logging.getLogger(__name__)

# Thread-safe counters
_counters_lock = Lock()
_counters = {
    "dashboards_generated": 0,
    "hitl_triggered": 0,
    "dashboards_failed": 0,
    "workflows_completed": 0
}


class MetricsCollector:
    """Collects and stores metrics for dashboard generation."""
    
    def __init__(self, metrics_file: Optional[str] = None):
        """
        Initialize metrics collector.
        
        Args:
            metrics_file: Optional path to JSON file for persistent storage
        """
        self.metrics_file = metrics_file
        self._load_metrics()
    
    def _load_metrics(self) -> None:
        """Load metrics from file if it exists."""
        if not self.metrics_file:
            return
        
        metrics_path = Path(self.metrics_file)
        if metrics_path.exists():
            try:
                with open(metrics_path, 'r') as f:
                    loaded = json.load(f)
                    with _counters_lock:
                        _counters.update(loaded)
                logger.info(f"Loaded metrics from {metrics_path}")
            except Exception as e:
                logger.warning(f"Failed to load metrics from {metrics_path}: {e}")
    
    def _save_metrics(self) -> None:
        """Save metrics to file."""
        if not self.metrics_file:
            return
        
        metrics_path = Path(self.metrics_file)
        try:
            metrics_path.parent.mkdir(parents=True, exist_ok=True)
            with open(metrics_path, 'w') as f:
                json.dump(_counters, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save metrics to {metrics_path}: {e}")
    
    def increment_dashboard_generated(self, company_id: Optional[str] = None) -> None:
        """Increment dashboard generated counter."""
        with _counters_lock:
            _counters["dashboards_generated"] += 1
        self._save_metrics()
        logger.info(f"📊 Dashboard generated (total: {_counters['dashboards_generated']})" + 
                   (f" for {company_id}" if company_id else ""))
    
    def increment_hitl_triggered(self, company_id: Optional[str] = None) -> None:
        """Increment HITL triggered counter."""
        with _counters_lock:
            _counters["hitl_triggered"] += 1
        self._save_metrics()
        logger.info(f"⚠️  HITL triggered (total: {_counters['hitl_triggered']})" + 
                   (f" for {company_id}" if company_id else ""))
    
    def increment_dashboard_failed(self, company_id: Optional[str] = None) -> None:
        """Increment dashboard failed counter."""
        with _counters_lock:
            _counters["dashboards_failed"] += 1
        self._save_metrics()
        logger.warning(f"❌ Dashboard failed (total: {_counters['dashboards_failed']})" + 
                      (f" for {company_id}" if company_id else ""))
    
    def increment_workflow_completed(self) -> None:
        """Increment workflow completed counter."""
        with _counters_lock:
            _counters["workflows_completed"] += 1
        self._save_metrics()
    
    def get_metrics(self) -> dict:
        """Get current metrics."""
        with _counters_lock:
            return _counters.copy()
    
    def reset_metrics(self) -> None:
        """Reset all metrics (for testing)."""
        with _counters_lock:
            _counters["dashboards_generated"] = 0
            _counters["hitl_triggered"] = 0
            _counters["dashboards_failed"] = 0
            _counters["workflows_completed"] = 0
        self._save_metrics()


# Global metrics collector instance
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get or create global metrics collector."""
    global _metrics_collector
    if _metrics_collector is None:
        # Use data directory for metrics file
        project_root = Path(__file__).resolve().parents[2]
        metrics_file = project_root / "data" / "metrics.json"
        _metrics_collector = MetricsCollector(str(metrics_file))
    return _metrics_collector


# Convenience functions
def increment_dashboard_generated(company_id: Optional[str] = None) -> None:
    """Increment dashboard generated counter."""
    get_metrics_collector().increment_dashboard_generated(company_id)


def increment_hitl_triggered(company_id: Optional[str] = None) -> None:
    """Increment HITL triggered counter."""
    get_metrics_collector().increment_hitl_triggered(company_id)


def increment_dashboard_failed(company_id: Optional[str] = None) -> None:
    """Increment dashboard failed counter."""
    get_metrics_collector().increment_dashboard_failed(company_id)


def get_metrics() -> dict:
    """Get current metrics."""
    return get_metrics_collector().get_metrics()
