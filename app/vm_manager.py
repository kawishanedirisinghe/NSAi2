import psutil
import json
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
import subprocess
import os
import queue
from dataclasses import dataclass, asdict
from flask import current_app

@dataclass
class ResourceMetrics:
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_available: int
    memory_used: int
    disk_usage: float
    gpu_usage: Optional[List[Dict]] = None
    network_io: Optional[Dict] = None
    active_users: int = 0
    active_models: int = 0
    queue_size: int = 0

@dataclass
class ModelStatus:
    model_id: str
    model_name: str
    status: str  # loading, ready, busy, error, stopped
    memory_usage: int
    gpu_id: Optional[int] = None
    last_used: Optional[datetime] = None
    load_time: Optional[float] = None
    total_requests: int = 0
    avg_response_time: float = 0.0

class VMResourceManager:
    def __init__(self, config=None):
        self.config = config or {}
        self.metrics_history = []
        self.max_history = 1000  # Keep last 1000 metrics
        self.monitoring_active = False
        self.monitoring_thread = None
        self.model_statuses = {}
        self.resource_alerts = queue.Queue()
        
        # Thresholds for alerts
        self.cpu_threshold = self.config.get('cpu_threshold', 80.0)
        self.memory_threshold = self.config.get('memory_threshold', 85.0)
        self.gpu_threshold = self.config.get('gpu_threshold', 90.0)
        
        # Auto-scaling settings
        self.auto_scaling_enabled = self.config.get('auto_scaling', True)
        self.scale_up_threshold = self.config.get('scale_up_threshold', 75.0)
        self.scale_down_threshold = self.config.get('scale_down_threshold', 25.0)
        
        self.logger = logging.getLogger(__name__)
    
    def start_monitoring(self, interval=30):
        """Start resource monitoring in background thread"""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            args=(interval,),
            daemon=True
        )
        self.monitoring_thread.start()
        self.logger.info("VM resource monitoring started")
    
    def stop_monitoring(self):
        """Stop resource monitoring"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        self.logger.info("VM resource monitoring stopped")
    
    def _monitoring_loop(self, interval):
        """Main monitoring loop"""
        while self.monitoring_active:
            try:
                metrics = self.collect_metrics()
                self.metrics_history.append(metrics)
                
                # Keep only recent metrics
                if len(self.metrics_history) > self.max_history:
                    self.metrics_history.pop(0)
                
                # Check for alerts
                self._check_resource_alerts(metrics)
                
                # Auto-scaling logic
                if self.auto_scaling_enabled:
                    self._check_auto_scaling(metrics)
                
                time.sleep(interval)
                
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                time.sleep(interval)
    
    def collect_metrics(self) -> ResourceMetrics:
        """Collect current system metrics"""
        # Basic system metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Network I/O
        network = psutil.net_io_counters()
        network_io = {
            'bytes_sent': network.bytes_sent,
            'bytes_recv': network.bytes_recv,
            'packets_sent': network.packets_sent,
            'packets_recv': network.packets_recv
        }
        
        # GPU metrics (if available)
        gpu_usage = self._get_gpu_metrics()
        
        # Application-specific metrics
        active_users = self._get_active_users_count()
        active_models = len([m for m in self.model_statuses.values() if m.status in ['ready', 'busy']])
        
        return ResourceMetrics(
            timestamp=datetime.utcnow(),
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            memory_available=memory.available,
            memory_used=memory.used,
            disk_usage=disk.percent,
            gpu_usage=gpu_usage,
            network_io=network_io,
            active_users=active_users,
            active_models=active_models,
            queue_size=0  # TODO: Get actual queue size from task manager
        )
    
    def _get_gpu_metrics(self) -> Optional[List[Dict]]:
        """Get GPU utilization metrics using nvidia-smi"""
        try:
            result = subprocess.run([
                'nvidia-smi', 
                '--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu',
                '--format=csv,noheader,nounits'
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                return None
            
            gpu_metrics = []
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split(', ')
                    gpu_metrics.append({
                        'index': int(parts[0]),
                        'name': parts[1],
                        'utilization': float(parts[2]),
                        'memory_used': int(parts[3]),
                        'memory_total': int(parts[4]),
                        'temperature': int(parts[5])
                    })
            
            return gpu_metrics
            
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            return None
    
    def _get_active_users_count(self) -> int:
        """Get count of currently active users"""
        try:
            # This would integrate with your user session management
            from .models import UserSession
            from datetime import datetime, timedelta
            
            recent_time = datetime.utcnow() - timedelta(minutes=30)
            active_sessions = UserSession.query.filter(
                UserSession.is_active == True,
                UserSession.expires_at > datetime.utcnow()
            ).count()
            
            return active_sessions
        except Exception:
            return 0
    
    def _check_resource_alerts(self, metrics: ResourceMetrics):
        """Check for resource threshold violations"""
        alerts = []
        
        if metrics.cpu_percent > self.cpu_threshold:
            alerts.append({
                'type': 'cpu_high',
                'value': metrics.cpu_percent,
                'threshold': self.cpu_threshold,
                'message': f'CPU usage high: {metrics.cpu_percent:.1f}%'
            })
        
        if metrics.memory_percent > self.memory_threshold:
            alerts.append({
                'type': 'memory_high',
                'value': metrics.memory_percent,
                'threshold': self.memory_threshold,
                'message': f'Memory usage high: {metrics.memory_percent:.1f}%'
            })
        
        if metrics.gpu_usage:
            for gpu in metrics.gpu_usage:
                if gpu['utilization'] > self.gpu_threshold:
                    alerts.append({
                        'type': 'gpu_high',
                        'gpu_id': gpu['index'],
                        'value': gpu['utilization'],
                        'threshold': self.gpu_threshold,
                        'message': f'GPU {gpu["index"]} usage high: {gpu["utilization"]:.1f}%'
                    })
        
        # Add alerts to queue
        for alert in alerts:
            alert['timestamp'] = datetime.utcnow()
            self.resource_alerts.put(alert)
    
    def _check_auto_scaling(self, metrics: ResourceMetrics):
        """Check if auto-scaling actions are needed"""
        # This is a placeholder for auto-scaling logic
        # In a real implementation, this would integrate with container orchestration
        # or cloud auto-scaling services
        
        avg_cpu = self._get_average_cpu_last_minutes(5)
        avg_memory = self._get_average_memory_last_minutes(5)
        
        if avg_cpu > self.scale_up_threshold or avg_memory > self.scale_up_threshold:
            self.logger.info(f"Scale-up trigger: CPU {avg_cpu:.1f}%, Memory {avg_memory:.1f}%")
            # TODO: Implement scale-up logic
        
        elif avg_cpu < self.scale_down_threshold and avg_memory < self.scale_down_threshold:
            self.logger.info(f"Scale-down trigger: CPU {avg_cpu:.1f}%, Memory {avg_memory:.1f}%")
            # TODO: Implement scale-down logic
    
    def _get_average_cpu_last_minutes(self, minutes: int) -> float:
        """Get average CPU usage for last N minutes"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        recent_metrics = [m for m in self.metrics_history if m.timestamp > cutoff_time]
        
        if not recent_metrics:
            return 0.0
        
        return sum(m.cpu_percent for m in recent_metrics) / len(recent_metrics)
    
    def _get_average_memory_last_minutes(self, minutes: int) -> float:
        """Get average memory usage for last N minutes"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        recent_metrics = [m for m in self.metrics_history if m.timestamp > cutoff_time]
        
        if not recent_metrics:
            return 0.0
        
        return sum(m.memory_percent for m in recent_metrics) / len(recent_metrics)
    
    def register_model(self, model_id: str, model_name: str, gpu_id: Optional[int] = None):
        """Register a new model instance"""
        self.model_statuses[model_id] = ModelStatus(
            model_id=model_id,
            model_name=model_name,
            status='loading',
            memory_usage=0,
            gpu_id=gpu_id
        )
        self.logger.info(f"Registered model {model_name} with ID {model_id}")
    
    def update_model_status(self, model_id: str, status: str, memory_usage: int = 0, 
                           load_time: Optional[float] = None):
        """Update model status"""
        if model_id in self.model_statuses:
            model = self.model_statuses[model_id]
            model.status = status
            model.memory_usage = memory_usage
            if load_time is not None:
                model.load_time = load_time
            if status in ['ready', 'busy']:
                model.last_used = datetime.utcnow()
    
    def record_model_request(self, model_id: str, response_time: float):
        """Record a model request and response time"""
        if model_id in self.model_statuses:
            model = self.model_statuses[model_id]
            model.total_requests += 1
            model.avg_response_time = (
                (model.avg_response_time * (model.total_requests - 1) + response_time) 
                / model.total_requests
            )
            model.last_used = datetime.utcnow()
    
    def get_current_metrics(self) -> Dict:
        """Get current system metrics as dictionary"""
        if self.metrics_history:
            latest = self.metrics_history[-1]
            return asdict(latest)
        return {}
    
    def get_metrics_history(self, hours: int = 1) -> List[Dict]:
        """Get metrics history for specified hours"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        recent_metrics = [
            asdict(m) for m in self.metrics_history 
            if m.timestamp > cutoff_time
        ]
        return recent_metrics
    
    def get_model_statuses(self) -> Dict[str, Dict]:
        """Get all model statuses"""
        return {
            model_id: asdict(status) 
            for model_id, status in self.model_statuses.items()
        }
    
    def get_alerts(self, max_alerts: int = 50) -> List[Dict]:
        """Get recent alerts"""
        alerts = []
        while not self.resource_alerts.empty() and len(alerts) < max_alerts:
            try:
                alert = self.resource_alerts.get_nowait()
                alerts.append(alert)
            except queue.Empty:
                break
        return alerts
    
    def get_system_health(self) -> Dict:
        """Get overall system health status"""
        if not self.metrics_history:
            return {'status': 'unknown', 'message': 'No metrics available'}
        
        latest = self.metrics_history[-1]
        
        # Determine health status
        critical_issues = []
        warnings = []
        
        if latest.cpu_percent > 90:
            critical_issues.append(f"Critical CPU usage: {latest.cpu_percent:.1f}%")
        elif latest.cpu_percent > self.cpu_threshold:
            warnings.append(f"High CPU usage: {latest.cpu_percent:.1f}%")
        
        if latest.memory_percent > 95:
            critical_issues.append(f"Critical memory usage: {latest.memory_percent:.1f}%")
        elif latest.memory_percent > self.memory_threshold:
            warnings.append(f"High memory usage: {latest.memory_percent:.1f}%")
        
        if latest.disk_usage > 95:
            critical_issues.append(f"Critical disk usage: {latest.disk_usage:.1f}%")
        elif latest.disk_usage > 85:
            warnings.append(f"High disk usage: {latest.disk_usage:.1f}%")
        
        # Check GPU health
        if latest.gpu_usage:
            for gpu in latest.gpu_usage:
                if gpu['utilization'] > 95:
                    critical_issues.append(f"Critical GPU {gpu['index']} usage: {gpu['utilization']:.1f}%")
                elif gpu['utilization'] > self.gpu_threshold:
                    warnings.append(f"High GPU {gpu['index']} usage: {gpu['utilization']:.1f}%")
        
        # Determine overall status
        if critical_issues:
            status = 'critical'
            message = '; '.join(critical_issues)
        elif warnings:
            status = 'warning'
            message = '; '.join(warnings)
        else:
            status = 'healthy'
            message = 'All systems operating normally'
        
        return {
            'status': status,
            'message': message,
            'metrics': asdict(latest),
            'model_count': len(self.model_statuses),
            'active_models': len([m for m in self.model_statuses.values() if m.status in ['ready', 'busy']])
        }
    
    def optimize_for_vm(self) -> Dict:
        """Get VM optimization recommendations"""
        if not self.metrics_history:
            return {'recommendations': []}
        
        recommendations = []
        latest = self.metrics_history[-1]
        
        # CPU recommendations
        avg_cpu = self._get_average_cpu_last_minutes(30)
        if avg_cpu < 20:
            recommendations.append({
                'type': 'cpu',
                'action': 'downsize',
                'message': 'CPU usage consistently low, consider downsizing VM'
            })
        elif avg_cpu > 80:
            recommendations.append({
                'type': 'cpu',
                'action': 'upsize',
                'message': 'CPU usage consistently high, consider upgrading VM'
            })
        
        # Memory recommendations
        avg_memory = self._get_average_memory_last_minutes(30)
        if avg_memory < 30:
            recommendations.append({
                'type': 'memory',
                'action': 'downsize',
                'message': 'Memory usage low, consider reducing VM memory'
            })
        elif avg_memory > 85:
            recommendations.append({
                'type': 'memory',
                'action': 'upsize',
                'message': 'Memory usage high, consider increasing VM memory'
            })
        
        # Model optimization
        idle_models = [
            m for m in self.model_statuses.values() 
            if m.status == 'ready' and m.last_used and 
            (datetime.utcnow() - m.last_used).total_seconds() > 3600
        ]
        
        if idle_models:
            recommendations.append({
                'type': 'models',
                'action': 'cleanup',
                'message': f'{len(idle_models)} models idle for >1 hour, consider unloading'
            })
        
        return {
            'recommendations': recommendations,
            'optimization_score': self._calculate_optimization_score()
        }
    
    def _calculate_optimization_score(self) -> float:
        """Calculate system optimization score (0-100)"""
        if not self.metrics_history:
            return 50.0
        
        latest = self.metrics_history[-1]
        score = 100.0
        
        # Penalize high resource usage
        if latest.cpu_percent > 80:
            score -= (latest.cpu_percent - 80) * 0.5
        if latest.memory_percent > 80:
            score -= (latest.memory_percent - 80) * 0.5
        
        # Penalize very low usage (waste)
        if latest.cpu_percent < 10:
            score -= (10 - latest.cpu_percent) * 0.3
        if latest.memory_percent < 20:
            score -= (20 - latest.memory_percent) * 0.2
        
        # Bonus for optimal usage (30-70%)
        if 30 <= latest.cpu_percent <= 70:
            score += 5
        if 30 <= latest.memory_percent <= 70:
            score += 5
        
        return max(0, min(100, score))

# Global VM manager instance
vm_manager = VMResourceManager()