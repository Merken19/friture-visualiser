#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2025 Friture Contributors

# This file is part of Friture.
#
# Friture is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as published by
# the Free Software Foundation.
#
# Friture is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Friture.  If not, see <http://www.gnu.org/licenses/>.

"""
Example Implementations for Friture Streaming API

This module provides comprehensive examples demonstrating how to use
the Friture Streaming API for various applications and use cases.

Examples Include:
- Basic pitch tracking consumer
- Real-time spectrum analysis dashboard
- Multi-protocol data logging
- Custom data processing pipelines
- Performance monitoring and optimization
- Integration with external systems

These examples serve as both documentation and starting points for
custom implementations.
"""

import json
import logging
import time
from typing import Any, Dict
import numpy as np

from .streaming_api import get_streaming_api
from .data_types import DataType, StreamingData, PitchData, FFTSpectrumData
from .consumers import CallbackConsumer, QueueConsumer, FileConsumer
from .protocols import WebSocketProtocol, TCPProtocol, UDPProtocol


def example_basic_pitch_consumer():
    """
    Example: Basic pitch tracking consumer
    
    This example shows how to create a simple callback-based consumer
    for pitch tracking data. The callback function processes each
    pitch detection result as it arrives.
    """
    
    def pitch_callback(data: StreamingData) -> None:
        """Process pitch tracking data."""
        if isinstance(data.data, PitchData):
            pitch_data = data.data
            
            if pitch_data.frequency_hz:
                print(f"Pitch: {pitch_data.frequency_hz:.1f} Hz "
                      f"({pitch_data.note_name}) "
                      f"Confidence: {pitch_data.confidence:.2f}")
            else:
                print("No pitch detected")
    
    # Get the streaming API
    api = get_streaming_api()
    
    # Create and register the consumer
    consumer = CallbackConsumer(pitch_callback)
    consumer_id = api.register_consumer(DataType.PITCH_TRACKER, consumer)
    
    # Start streaming
    api.start_streaming()
    
    print(f"Pitch consumer registered with ID: {consumer_id}")
    print("Listening for pitch data... (Ctrl+C to stop)")
    
    try:
        # Keep the example running
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nStopping...")
        api.stop_streaming()


def example_spectrum_analysis_dashboard():
    """
    Example: Real-time spectrum analysis dashboard
    
    This example demonstrates how to create a web-based dashboard
    that displays real-time FFT spectrum data using WebSocket protocol.
    """
    
    class SpectrumDashboard:
        def __init__(self):
            self.api = get_streaming_api()
            self.websocket_protocol = WebSocketProtocol(port=8765)
            self.latest_spectrum = None
            
            # Setup WebSocket protocol
            self.api.add_protocol(self.websocket_protocol)
            
            # Create spectrum consumer
            self.consumer = CallbackConsumer(self.process_spectrum_data)
            self.consumer_id = self.api.register_consumer(
                DataType.FFT_SPECTRUM, self.consumer
            )
            
            # Setup connection handlers
            self.websocket_protocol.client_connected.connect(self.on_client_connected)
            self.websocket_protocol.client_disconnected.connect(self.on_client_disconnected)
        
        def process_spectrum_data(self, data: StreamingData) -> None:
            """Process FFT spectrum data for dashboard."""
            if isinstance(data.data, FFTSpectrumData):
                spectrum_data = data.data
                
                # Store latest spectrum
                self.latest_spectrum = {
                    'timestamp': data.metadata.timestamp,
                    'frequencies': spectrum_data.frequencies.tolist(),
                    'magnitudes': spectrum_data.magnitudes_db.tolist(),
                    'peak_frequency': spectrum_data.peak_frequency,
                    'peak_magnitude': spectrum_data.peak_magnitude,
                    'fft_size': spectrum_data.fft_size,
                    'weighting': spectrum_data.weighting
                }
                
                # Send to all connected clients
                message = json.dumps({
                    'type': 'spectrum_update',
                    'data': self.latest_spectrum
                })
                self.websocket_protocol.send_data(message)
        
        def on_client_connected(self, client_id: str) -> None:
            """Handle new client connection."""
            print(f"Dashboard client connected: {client_id}")
            
            # Send latest spectrum data to new client
            if self.latest_spectrum:
                welcome_message = json.dumps({
                    'type': 'initial_spectrum',
                    'data': self.latest_spectrum
                })
                self.websocket_protocol.send_data(welcome_message, client_id)
        
        def on_client_disconnected(self, client_id: str) -> None:
            """Handle client disconnection."""
            print(f"Dashboard client disconnected: {client_id}")
        
        def start(self) -> None:
            """Start the dashboard."""
            self.api.start_streaming()
            print("Spectrum dashboard started on ws://localhost:8765")
            print("Connect with a WebSocket client to receive spectrum data")
        
        def stop(self) -> None:
            """Stop the dashboard."""
            self.api.stop_streaming()
            print("Spectrum dashboard stopped")
    
    # Create and start dashboard
    dashboard = SpectrumDashboard()
    dashboard.start()
    
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        dashboard.stop()


def example_multi_protocol_logger():
    """
    Example: Multi-protocol data logging
    
    This example shows how to log data from multiple sources using
    different protocols and storage methods simultaneously.
    """
    
    class MultiProtocolLogger:
        def __init__(self):
            self.api = get_streaming_api()
            self.consumers = {}
            
            # Setup file logging for all data types
            self.setup_file_logging()
            
            # Setup network protocols
            self.setup_network_protocols()
            
            # Setup queue-based processing
            self.setup_queue_processing()
        
        def setup_file_logging(self) -> None:
            """Setup file logging for all data types."""
            for data_type in DataType:
                file_consumer = FileConsumer(
                    f"friture_log_{data_type.value}",
                    file_format='jsonl',
                    max_file_size_mb=50
                )
                
                consumer_id = self.api.register_consumer(data_type, file_consumer)
                self.consumers[f"file_{data_type.value}"] = consumer_id
                
                print(f"File logging enabled for {data_type.value}")
        
        def setup_network_protocols(self) -> None:
            """Setup multiple network protocols."""
            # WebSocket for web clients
            websocket = WebSocketProtocol(port=8765)
            self.api.add_protocol(websocket)
            
            # TCP for reliable delivery
            tcp = TCPProtocol(port=8766)
            self.api.add_protocol(tcp)
            
            # UDP for low-latency applications
            udp = UDPProtocol(port=8767)
            udp.add_client('localhost', 9000)  # Example client
            self.api.add_protocol(udp)
            
            print("Network protocols enabled: WebSocket:8765, TCP:8766, UDP:8767")
        
        def setup_queue_processing(self) -> None:
            """Setup queue-based processing for custom analysis."""
            # Create queue consumer for pitch data
            pitch_queue = QueueConsumer(max_queue_size=100, overflow_strategy='drop_oldest')
            consumer_id = self.api.register_consumer(DataType.PITCH_TRACKER, pitch_queue)
            
            # Start processing thread
            import threading
            processing_thread = threading.Thread(
                target=self.process_pitch_queue,
                args=(pitch_queue,),
                daemon=True
            )
            processing_thread.start()
            
            self.consumers['pitch_queue'] = consumer_id
            print("Queue-based pitch processing enabled")
        
        def process_pitch_queue(self, queue_consumer: QueueConsumer) -> None:
            """Process pitch data from queue (runs in separate thread)."""
            while True:
                try:
                    data = queue_consumer.get_data(timeout=1.0)
                    if data and isinstance(data.data, PitchData):
                        pitch_data = data.data
                        
                        # Example: Detect pitch stability
                        if pitch_data.frequency_hz and pitch_data.confidence > 0.8:
                            print(f"Stable pitch detected: {pitch_data.note_name} "
                                  f"({pitch_data.frequency_hz:.1f} Hz)")
                        
                except Exception as e:
                    logging.getLogger(__name__).error(f"Error processing pitch queue: {e}")
                    time.sleep(0.1)
        
        def start(self) -> None:
            """Start the multi-protocol logger."""
            self.api.start_streaming()
            print("Multi-protocol logger started")
        
        def stop(self) -> None:
            """Stop the multi-protocol logger."""
            self.api.stop_streaming()
            print("Multi-protocol logger stopped")
        
        def get_statistics(self) -> Dict[str, Any]:
            """Get comprehensive statistics."""
            stats = {
                'api_stats': self.api.get_statistics(),
                'consumer_count': len(self.consumers),
                'protocol_count': len(self.api._protocols)
            }
            
            # Add individual consumer statistics
            for name, consumer_id in self.consumers.items():
                # This would need access to consumer statistics
                stats[f'consumer_{name}'] = {'id': consumer_id}
            
            return stats
    
    # Create and start logger
    logger = MultiProtocolLogger()
    logger.start()
    
    try:
        while True:
            # Print statistics every 10 seconds
            time.sleep(10.0)
            stats = logger.get_statistics()
            print(f"Statistics: {json.dumps(stats, indent=2)}")
    except KeyboardInterrupt:
        logger.stop()


def example_custom_analysis_pipeline():
    """
    Example: Custom analysis pipeline
    
    This example demonstrates how to create a custom analysis pipeline
    that processes multiple data types and generates derived insights.
    """
    
    class CustomAnalysisPipeline:
        def __init__(self):
            self.api = get_streaming_api()
            
            # Data storage for analysis
            self.pitch_history = []
            self.spectrum_history = []
            
            # Analysis parameters
            self.analysis_window_seconds = 5.0
            self.pitch_stability_threshold = 0.1  # Hz
            
            # Setup consumers
            self.setup_consumers()
        
        def setup_consumers(self) -> None:
            """Setup consumers for analysis pipeline."""
            # Pitch tracking consumer
            pitch_consumer = CallbackConsumer(self.process_pitch_data)
            self.api.register_consumer(DataType.PITCH_TRACKER, pitch_consumer)
            
            # Spectrum consumer
            spectrum_consumer = CallbackConsumer(self.process_spectrum_data)
            self.api.register_consumer(DataType.FFT_SPECTRUM, spectrum_consumer)
        
        def process_pitch_data(self, data: StreamingData) -> None:
            """Process pitch data for analysis."""
            if isinstance(data.data, PitchData):
                pitch_data = data.data
                
                # Store in history
                self.pitch_history.append({
                    'timestamp': data.metadata.timestamp,
                    'frequency': pitch_data.frequency_hz,
                    'confidence': pitch_data.confidence,
                    'note': pitch_data.note_name
                })
                
                # Trim history to analysis window
                cutoff_time = data.metadata.timestamp - self.analysis_window_seconds
                self.pitch_history = [
                    p for p in self.pitch_history 
                    if p['timestamp'] > cutoff_time
                ]
                
                # Perform analysis
                self.analyze_pitch_stability()
        
        def process_spectrum_data(self, data: StreamingData) -> None:
            """Process spectrum data for analysis."""
            if isinstance(data.data, FFTSpectrumData):
                spectrum_data = data.data
                
                # Store key metrics
                self.spectrum_history.append({
                    'timestamp': data.metadata.timestamp,
                    'peak_frequency': spectrum_data.peak_frequency,
                    'peak_magnitude': spectrum_data.peak_magnitude,
                    'spectral_centroid': self.calculate_spectral_centroid(spectrum_data)
                })
                
                # Trim history
                cutoff_time = data.metadata.timestamp - self.analysis_window_seconds
                self.spectrum_history = [
                    s for s in self.spectrum_history 
                    if s['timestamp'] > cutoff_time
                ]
        
        def calculate_spectral_centroid(self, spectrum_data: FFTSpectrumData) -> float:
            """Calculate spectral centroid from spectrum data."""
            try:
                # Convert dB to linear scale
                linear_magnitudes = 10.0 ** (spectrum_data.magnitudes_db / 20.0)
                
                # Calculate weighted average frequency
                total_energy = np.sum(linear_magnitudes)
                if total_energy > 0:
                    weighted_freq = np.sum(spectrum_data.frequencies * linear_magnitudes)
                    return weighted_freq / total_energy
                else:
                    return 0.0
            except:
                return 0.0
        
        def analyze_pitch_stability(self) -> None:
            """Analyze pitch stability over the analysis window."""
            if len(self.pitch_history) < 10:  # Need minimum data
                return
            
            # Extract valid pitch frequencies
            valid_pitches = [
                p['frequency'] for p in self.pitch_history 
                if p['frequency'] is not None and p['confidence'] > 0.5
            ]
            
            if len(valid_pitches) < 5:
                return
            
            # Calculate pitch stability
            pitch_std = np.std(valid_pitches)
            pitch_mean = np.mean(valid_pitches)
            
            if pitch_std < self.pitch_stability_threshold:
                print(f"STABLE PITCH DETECTED: {pitch_mean:.1f} Hz "
                      f"(std: {pitch_std:.3f} Hz) over {len(valid_pitches)} samples")
                
                # Could trigger additional analysis or notifications here
                self.on_stable_pitch_detected(pitch_mean, pitch_std, len(valid_pitches))
        
        def on_stable_pitch_detected(self, frequency: float, stability: float, sample_count: int) -> None:
            """Handle stable pitch detection event."""
            # Example: Log to file, send notification, trigger recording, etc.
            analysis_result = {
                'event': 'stable_pitch',
                'frequency_hz': frequency,
                'stability_hz': stability,
                'sample_count': sample_count,
                'timestamp': time.time()
            }
            
            # Could save to database, send to external system, etc.
            print(f"Analysis result: {json.dumps(analysis_result, indent=2)}")
        
        def start(self) -> None:
            """Start the analysis pipeline."""
            self.api.start_streaming()
            print("Custom analysis pipeline started")
        
        def stop(self) -> None:
            """Stop the analysis pipeline."""
            self.api.stop_streaming()
            print("Custom analysis pipeline stopped")
    
    # Create and run pipeline
    pipeline = CustomAnalysisPipeline()
    pipeline.start()
    
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pipeline.stop()


def example_performance_monitoring():
    """
    Example: Performance monitoring and optimization
    
    This example shows how to monitor the streaming API performance
    and implement adaptive optimizations based on system load.
    """
    
    class PerformanceMonitor:
        def __init__(self):
            self.api = get_streaming_api()
            self.monitoring_active = False
            
            # Performance thresholds
            self.max_cpu_percent = 80.0
            self.max_memory_mb = 500.0
            self.max_queue_size = 100
            
        def start_monitoring(self) -> None:
            """Start performance monitoring."""
            self.monitoring_active = True
            
            import threading
            monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            monitor_thread.start()
            
            print("Performance monitoring started")
        
        def stop_monitoring(self) -> None:
            """Stop performance monitoring."""
            self.monitoring_active = False
            print("Performance monitoring stopped")
        
        def _monitor_loop(self) -> None:
            """Main monitoring loop (runs in separate thread)."""
            while self.monitoring_active:
                try:
                    # Get system metrics
                    import psutil
                    cpu_percent = psutil.cpu_percent(interval=1.0)
                    memory_mb = psutil.Process().memory_info().rss / (1024 * 1024)
                    
                    # Get API statistics
                    api_stats = self.api.get_statistics()
                    
                    # Check for performance issues
                    issues = []
                    
                    if cpu_percent > self.max_cpu_percent:
                        issues.append(f"High CPU usage: {cpu_percent:.1f}%")
                    
                    if memory_mb > self.max_memory_mb:
                        issues.append(f"High memory usage: {memory_mb:.1f} MB")
                    
                    # Check data rates
                    data_rate = api_stats.get('data_rate_hz', 0)
                    if data_rate > 200:  # High data rate
                        issues.append(f"High data rate: {data_rate:.1f} Hz")
                    
                    # Apply optimizations if needed
                    if issues:
                        print(f"Performance issues detected: {', '.join(issues)}")
                        self._apply_optimizations(cpu_percent, memory_mb, data_rate)
                    
                    # Log statistics periodically
                    if int(time.time()) % 30 == 0:  # Every 30 seconds
                        self._log_performance_stats(cpu_percent, memory_mb, api_stats)
                
                except Exception as e:
                    logging.getLogger(__name__).error(f"Error in monitoring loop: {e}")
                    time.sleep(1.0)
        
        def _apply_optimizations(self, cpu_percent: float, memory_mb: float, data_rate: float) -> None:
            """Apply performance optimizations based on current conditions."""
            # Reduce rate limits if CPU is high
            if cpu_percent > self.max_cpu_percent:
                for data_type in DataType:
                    current_limit = self.api._rate_limiter.get_rate_limit(data_type)
                    if current_limit and current_limit > 5.0:
                        new_limit = current_limit * 0.8  # Reduce by 20%
                        self.api.set_rate_limit(data_type, new_limit)
                        print(f"Reduced rate limit for {data_type.value} to {new_limit:.1f} Hz")
            
            # Clear buffers if memory is high
            if memory_mb > self.max_memory_mb:
                buffer_manager = self.api._buffer_manager
                for data_type in DataType:
                    cleared = buffer_manager.clear_buffer(data_type)
                    if cleared > 0:
                        print(f"Cleared {cleared} items from {data_type.value} buffer")
        
        def _log_performance_stats(self, cpu_percent: float, memory_mb: float, api_stats: Dict[str, Any]) -> None:
            """Log comprehensive performance statistics."""
            stats_summary = {
                'system': {
                    'cpu_percent': cpu_percent,
                    'memory_mb': memory_mb
                },
                'api': api_stats,
                'timestamp': time.time()
            }
            
            print(f"Performance Stats: {json.dumps(stats_summary, indent=2)}")
    
    # Create and start monitor
    monitor = PerformanceMonitor()
    monitor.start_monitoring()
    
    # Also start streaming for demonstration
    api = get_streaming_api()
    api.start_streaming()
    
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        monitor.stop_monitoring()
        api.stop_streaming()


def example_external_system_integration():
    """
    Example: Integration with external systems
    
    This example demonstrates how to integrate Friture streaming data
    with external systems like databases, message queues, or cloud services.
    """
    
    class ExternalSystemIntegrator:
        def __init__(self):
            self.api = get_streaming_api()
            
            # Simulated external systems
            self.database_queue = []
            self.alert_system_queue = []
            
            # Setup consumers
            self.setup_database_integration()
            self.setup_alert_system()
        
        def setup_database_integration(self) -> None:
            """Setup integration with database system."""
            def database_callback(data: StreamingData) -> None:
                """Store data in database (simulated)."""
                # In a real implementation, this would write to a database
                record = {
                    'table': f"{data.metadata.data_type.value}_data",
                    'timestamp': data.metadata.timestamp,
                    'widget_id': data.metadata.widget_id,
                    'data': data.to_dict()['data']
                }
                
                self.database_queue.append(record)
                
                # Simulate batch processing
                if len(self.database_queue) >= 10:
                    self._flush_to_database()
            
            # Register for all data types
            for data_type in DataType:
                consumer = CallbackConsumer(database_callback, max_callback_time_ms=5.0)
                self.api.register_consumer(data_type, consumer)
            
            print("Database integration enabled")
        
        def setup_alert_system(self) -> None:
            """Setup integration with alert system."""
            def alert_callback(data: StreamingData) -> None:
                """Check for alert conditions."""
                alerts = []
                
                # Example alert conditions
                if isinstance(data.data, PitchData):
                    pitch_data = data.data
                    if pitch_data.frequency_hz and pitch_data.frequency_hz > 2000:
                        alerts.append({
                            'type': 'high_pitch',
                            'frequency': pitch_data.frequency_hz,
                            'severity': 'warning'
                        })
                
                elif isinstance(data.data, FFTSpectrumData):
                    spectrum_data = data.data
                    if spectrum_data.peak_magnitude > -10:  # Very loud signal
                        alerts.append({
                            'type': 'high_amplitude',
                            'magnitude': spectrum_data.peak_magnitude,
                            'frequency': spectrum_data.peak_frequency,
                            'severity': 'critical'
                        })
                
                # Process alerts
                for alert in alerts:
                    self._send_alert(alert, data.metadata)
            
            # Register for relevant data types
            alert_consumer = CallbackConsumer(alert_callback)
            self.api.register_consumer(DataType.PITCH_TRACKER, alert_consumer)
            self.api.register_consumer(DataType.FFT_SPECTRUM, alert_consumer)
            
            print("Alert system enabled")
        
        def _flush_to_database(self) -> None:
            """Flush queued records to database (simulated)."""
            records = self.database_queue.copy()
            self.database_queue.clear()
            
            print(f"Flushing {len(records)} records to database")
            # In real implementation: database.bulk_insert(records)
        
        def _send_alert(self, alert: Dict[str, Any], metadata) -> None:
            """Send alert to external system (simulated)."""
            alert_record = {
                **alert,
                'timestamp': metadata.timestamp,
                'widget_id': metadata.widget_id,
                'source': 'friture_streaming_api'
            }
            
            self.alert_system_queue.append(alert_record)
            print(f"ALERT: {json.dumps(alert_record)}")
        
        def start(self) -> None:
            """Start the integration system."""
            self.api.start_streaming()
            print("External system integration started")
        
        def stop(self) -> None:
            """Stop the integration system."""
            # Flush any remaining data
            if self.database_queue:
                self._flush_to_database()
            
            self.api.stop_streaming()
            print("External system integration stopped")
    
    # Create and run integrator
    integrator = ExternalSystemIntegrator()
    integrator.start()
    
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        integrator.stop()


if __name__ == "__main__":
    """
    Run examples based on command line arguments.
    """
    import sys
    
    examples = {
        'pitch': example_basic_pitch_consumer,
        'dashboard': example_spectrum_analysis_dashboard,
        'logger': example_multi_protocol_logger,
        'pipeline': example_custom_analysis_pipeline,
        'integration': example_external_system_integration
    }
    
    if len(sys.argv) > 1 and sys.argv[1] in examples:
        example_name = sys.argv[1]
        print(f"Running example: {example_name}")
        examples[example_name]()
    else:
        print("Available examples:")
        for name in examples.keys():
            print(f"  python -m friture.api.examples {name}")