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
Main Streaming API Implementation

This module provides the central StreamingAPI class that coordinates
data producers, consumers, and protocols for real-time data streaming.

The API is designed with the following principles:
1. Zero-overhead when no consumers are registered
2. Minimal impact on Friture's main processing loop
3. Configurable rate limiting and backpressure handling
4. Thread-safe operation
5. Extensible architecture for new data types and protocols

Architecture:
- Producers: Extract data from Friture widgets
- Consumers: Process and forward data to external systems
- Protocols: Handle network communication
- Rate Limiter: Prevents overwhelming consumers
- Buffer Manager: Handles temporary storage and backpressure
"""

import logging
import threading
import time
from collections import defaultdict, deque
from typing import Dict, List, Optional, Callable, Any
from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from .data_types import DataType, StreamingData
from .consumers import DataConsumer
from .producers import DataProducer
from .protocols import StreamingProtocol
from .rate_limiter import RateLimiter
from .buffer_manager import BufferManager


class StreamingAPI(QObject):
    """
    Main streaming API coordinator.
    
    This class manages the entire streaming pipeline from data extraction
    to network transmission. It provides a simple interface for registering
    consumers and automatically handles the complex coordination between
    producers, rate limiting, buffering, and protocol handling.
    
    Signals:
        data_available: Emitted when new data is available for streaming
        consumer_registered: Emitted when a new consumer is registered
        consumer_unregistered: Emitted when a consumer is unregistered
        error_occurred: Emitted when an error occurs in the streaming pipeline
    """
    
    data_available = pyqtSignal(DataType, StreamingData)
    consumer_registered = pyqtSignal(DataType, str)
    consumer_unregistered = pyqtSignal(DataType, str)
    error_occurred = pyqtSignal(str, str)  # error_type, error_message
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.logger = logging.getLogger(__name__)
        
        # Core components
        self._producers: Dict[DataType, DataProducer] = {}
        self._consumers: Dict[DataType, List[DataConsumer]] = defaultdict(list)
        self._protocols: List[StreamingProtocol] = []
        self._rate_limiter = RateLimiter()
        self._buffer_manager = BufferManager()
        
        # State management
        self._is_streaming = False
        self._sequence_numbers: Dict[DataType, int] = defaultdict(int)
        self._statistics: Dict[str, Any] = defaultdict(int)
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Performance monitoring
        self._performance_timer = QTimer()
        self._performance_timer.timeout.connect(self._update_performance_stats)
        self._performance_timer.setInterval(1000)  # Update every second
        
        self.logger.info("StreamingAPI initialized")
    
    def register_producer(self, data_type: DataType, producer: DataProducer) -> None:
        """
        Register a data producer for a specific data type.
        
        Args:
            data_type: Type of data this producer generates
            producer: Producer instance
        """
        with self._lock:
            if data_type in self._producers:
                self.logger.warning(f"Replacing existing producer for {data_type}")
            
            self._producers[data_type] = producer
            producer.data_ready.connect(lambda data: self._handle_producer_data(data_type, data))
            
            self.logger.info(f"Registered producer for {data_type}")
    
    def register_consumer(self, data_type: DataType, consumer: DataConsumer) -> str:
        """
        Register a data consumer for a specific data type.
        
        Args:
            data_type: Type of data to consume
            consumer: Consumer instance
            
        Returns:
            Consumer ID for later reference
        """
        with self._lock:
            consumer_id = f"{data_type.value}_{len(self._consumers[data_type])}"
            consumer.set_id(consumer_id)
            
            self._consumers[data_type].append(consumer)
            
            # Start the producer if this is the first consumer
            if len(self._consumers[data_type]) == 1 and data_type in self._producers:
                self._producers[data_type].start()
            
            self.consumer_registered.emit(data_type, consumer_id)
            self.logger.info(f"Registered consumer {consumer_id} for {data_type}")
            
            return consumer_id
    
    def unregister_consumer(self, data_type: DataType, consumer_id: str) -> bool:
        """
        Unregister a data consumer.
        
        Args:
            data_type: Type of data the consumer was registered for
            consumer_id: Consumer ID returned from register_consumer
            
        Returns:
            True if consumer was found and removed, False otherwise
        """
        with self._lock:
            consumers = self._consumers[data_type]
            for i, consumer in enumerate(consumers):
                if consumer.get_id() == consumer_id:
                    consumers.pop(i)
                    
                    # Stop the producer if no consumers remain
                    if len(consumers) == 0 and data_type in self._producers:
                        self._producers[data_type].stop()
                    
                    self.consumer_unregistered.emit(data_type, consumer_id)
                    self.logger.info(f"Unregistered consumer {consumer_id}")
                    return True
            
            self.logger.warning(f"Consumer {consumer_id} not found for {data_type}")
            return False
    
    def add_protocol(self, protocol: StreamingProtocol) -> None:
        """
        Add a streaming protocol for network communication.
        
        Args:
            protocol: Protocol instance (WebSocket, TCP, UDP, etc.)
        """
        with self._lock:
            # Check if we already have a protocol of this type on the same port
            for existing_protocol in self._protocols:
                if (type(existing_protocol) == type(protocol) and 
                    existing_protocol.host == protocol.host and 
                    existing_protocol.port == protocol.port):
                    self.logger.warning(f"Protocol {type(protocol).__name__} already exists on {protocol.host}:{protocol.port}")
                    return
            
            self._protocols.append(protocol)
            protocol.error_occurred.connect(
                lambda error: self.error_occurred.emit("protocol", error)
            )
            
            if self._is_streaming:
                protocol.start()
            
            self.logger.info(f"Added protocol: {type(protocol).__name__}")
    
    def clear_protocols(self) -> None:
        """Clears all registered protocols and stops them if running."""
        with self._lock:
            for protocol in self._protocols:
                try:
                    protocol.stop()
                except Exception as e:
                    self.logger.error(f"Error stopping protocol during clear: {e}")
            self._protocols.clear()
            self.logger.info("All protocols cleared.")
            
    def start_streaming(self) -> None:
        """
        Start the streaming API.
        
        This activates all registered producers and protocols, beginning
        the data flow from Friture widgets to external consumers.
        """
        with self._lock:
            if self._is_streaming:
                self.logger.warning("Streaming already active")
                return
            
            self._is_streaming = True
            
            # Start all protocols
            for protocol in self._protocols:
                try:
                    protocol.start()
                except Exception as e:
                    self.logger.error(f"Failed to start protocol {type(protocol).__name__}: {e}")
            
            # Start producers that have consumers
            for data_type, producer in self._producers.items():
                if self._consumers[data_type]:
                    try:
                        producer.start()
                    except Exception as e:
                        self.logger.error(f"Failed to start producer for {data_type}: {e}")
            
            # Start performance monitoring
            self._performance_timer.start()
            
            self.logger.info("Streaming API started")
    
    def stop_streaming(self) -> None:
        """
        Stop the streaming API.
        
        This deactivates all producers and protocols, stopping the data flow.
        """
        with self._lock:
            if not self._is_streaming:
                return
            
            self._is_streaming = False
            
            # Stop performance monitoring
            self._performance_timer.stop()
            
            # Stop all producers
            for producer in self._producers.values():
                try:
                    producer.stop()
                except Exception as e:
                    self.logger.error(f"Failed to stop producer: {e}")
            
            # Stop all protocols
            for protocol in self._protocols:
                try:
                    protocol.stop()
                except Exception as e:
                    self.logger.error(f"Failed to stop protocol: {e}")
            
            self.logger.info("Streaming API stopped")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get streaming performance statistics.
        
        Returns:
            Dictionary containing performance metrics
        """
        with self._lock:
            stats = dict(self._statistics)
            stats['is_streaming'] = self._is_streaming
            stats['active_consumers'] = {
                data_type.value: len(consumers) 
                for data_type, consumers in self._consumers.items()
                if consumers
            }
            stats['active_producers'] = len(self._producers)
            stats['active_protocols'] = len(self._protocols)
            return stats
    
    def set_rate_limit(self, data_type: DataType, max_rate_hz: float) -> None:
        """
        Set rate limiting for a specific data type.
        
        Args:
            data_type: Data type to limit
            max_rate_hz: Maximum rate in Hz (0 = no limit)
        """
        self._rate_limiter.set_rate_limit(data_type, max_rate_hz)
        self.logger.info(f"Set rate limit for {data_type} to {max_rate_hz} Hz")
    
    def _handle_producer_data(self, data_type: DataType, data_payload: Any) -> None:
        """
        Handle data from a producer.
        
        This is the main data flow entry point. It applies rate limiting,
        creates the streaming data structure, and distributes to consumers.
        
        Args:
            data_type: Type of data received
            data_payload: The actual data from the producer
        """
        try:
            # Check rate limiting
            if not self._rate_limiter.should_process(data_type):
                self._statistics['rate_limited_count'] += 1
                return
            
            # Create streaming data structure
            with self._lock:
                sequence_number = self._sequence_numbers[data_type]
                self._sequence_numbers[data_type] += 1
            
            # Get producer metadata
            producer = self._producers[data_type]
            metadata_dict = producer.get_metadata()
            
            streaming_data = StreamingData(
                metadata=metadata_dict,
                data=data_payload
            )
            
            # Distribute to consumers
            self._distribute_to_consumers(data_type, streaming_data)
            
            # Update statistics
            self._statistics['total_data_points'] += 1
            self._statistics[f'{data_type.value}_count'] += 1
            
            # Emit signal for Qt-based consumers
            self.data_available.emit(data_type, streaming_data)
            
        except Exception as e:
            self.logger.error(f"Error handling producer data for {data_type}: {e}")
            self.error_occurred.emit("data_handling", str(e))
    
    def _distribute_to_consumers(self, data_type: DataType, streaming_data: StreamingData) -> None:
        """
        Distribute data to all registered consumers for a data type.
        
        Args:
            data_type: Type of data
            streaming_data: Data to distribute
        """
        consumers = self._consumers[data_type]
        if not consumers:
            return
        
        for consumer in consumers:
            try:
                # Check if consumer can handle the data rate
                if consumer.can_accept_data():
                    consumer.consume_data(streaming_data)
                else:
                    self._statistics['consumer_backpressure_count'] += 1
                    
            except Exception as e:
                self.logger.error(f"Error in consumer {consumer.get_id()}: {e}")
                self.error_occurred.emit("consumer", str(e))
    
    def _update_performance_stats(self) -> None:
        """Update performance statistics (called periodically)."""
        try:
            # Calculate data rates
            current_time = time.time()
            if hasattr(self, '_last_stats_time'):
                time_delta = current_time - self._last_stats_time
                if time_delta > 0:
                    total_count = self._statistics.get('total_data_points', 0)
                    if hasattr(self, '_last_total_count'):
                        rate = (total_count - self._last_total_count) / time_delta
                        self._statistics['data_rate_hz'] = rate
                    self._last_total_count = total_count
            
            self._last_stats_time = current_time
            
            # Log performance summary
            if self._statistics.get('total_data_points', 0) % 1000 == 0:
                self.logger.debug(f"Streaming stats: {dict(self._statistics)}")
                
        except Exception as e:
            self.logger.error(f"Error updating performance stats: {e}")


# Global API instance (singleton pattern)
_api_instance: Optional[StreamingAPI] = None


def get_streaming_api() -> StreamingAPI:
    """
    Get the global streaming API instance.
    
    Returns:
        Global StreamingAPI instance
    """
    global _api_instance
    if _api_instance is None:
        _api_instance = StreamingAPI()
    return _api_instance


def initialize_streaming_api(parent=None) -> StreamingAPI:
    """
    Initialize the global streaming API instance.
    
    Args:
        parent: Qt parent object
        
    Returns:
        Initialized StreamingAPI instance
    """
    global _api_instance
    if _api_instance is not None:
        logging.getLogger(__name__).warning("StreamingAPI already initialized")
        return _api_instance
    
    _api_instance = StreamingAPI(parent)
    return _api_instance