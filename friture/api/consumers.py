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
Data Consumers for Friture Streaming API

Consumers are responsible for processing streaming data and forwarding it
to external systems. They implement backpressure handling and can be
configured with various delivery guarantees.

Consumer Types:
- CallbackConsumer: Invokes a callback function with each data point
- QueueConsumer: Stores data in a thread-safe queue for external polling
- NetworkConsumer: Forwards data over network protocols
- FileConsumer: Writes data to files for logging/analysis

Design Principles:
- Non-blocking operation to avoid impacting Friture performance
- Configurable backpressure handling (drop, buffer, throttle)
- Thread-safe implementation
- Comprehensive error handling and recovery
- Performance monitoring and statistics
"""

import logging
import queue
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from typing import Callable, Optional, Any, Dict
import json

from PyQt5.QtCore import QObject, pyqtSignal

from .data_types import StreamingData


class DataConsumer(QObject, ABC):
    """
    Abstract base class for data consumers.
    
    All consumers must implement the abstract methods and follow the
    established patterns for data processing and backpressure handling.
    
    Signals:
        data_processed: Emitted when data is successfully processed
        error_occurred: Emitted when an error occurs
        backpressure_detected: Emitted when backpressure is detected
    """
    
    data_processed = pyqtSignal(str)  # consumer_id
    error_occurred = pyqtSignal(str, str)  # consumer_id, error_message
    backpressure_detected = pyqtSignal(str)  # consumer_id
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._consumer_id = ""
        self._is_active = True
        self._statistics = {
            'total_consumed': 0,
            'total_dropped': 0,
            'total_errors': 0,
            'last_consume_time': 0.0
        }
        self._lock = threading.RLock()
    
    def set_id(self, consumer_id: str) -> None:
        """Set the consumer ID."""
        self._consumer_id = consumer_id
    
    def get_id(self) -> str:
        """Get the consumer ID."""
        return self._consumer_id
    
    @abstractmethod
    def consume_data(self, data: StreamingData) -> None:
        """
        Consume streaming data.
        
        Args:
            data: StreamingData to process
        """
        pass
    
    @abstractmethod
    def can_accept_data(self) -> bool:
        """
        Check if consumer can accept new data.
        
        Returns:
            True if consumer can accept data, False if backpressure detected
        """
        pass
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get consumer statistics.
        
        Returns:
            Dictionary of performance statistics
        """
        with self._lock:
            stats = self._statistics.copy()
            stats['consumer_id'] = self._consumer_id
            stats['is_active'] = self._is_active
            return stats
    
    def set_active(self, active: bool) -> None:
        """
        Set consumer active state.
        
        Args:
            active: True to activate, False to deactivate
        """
        self._is_active = active
    
    def _update_statistics(self, consumed: bool = True, dropped: bool = False, error: bool = False) -> None:
        """Update internal statistics."""
        with self._lock:
            if consumed:
                self._statistics['total_consumed'] += 1
                self._statistics['last_consume_time'] = time.time()
            if dropped:
                self._statistics['total_dropped'] += 1
            if error:
                self._statistics['total_errors'] += 1


class CallbackConsumer(DataConsumer):
    """
    Consumer that invokes a callback function for each data point.
    
    This is the simplest consumer type, suitable for real-time processing
    where the callback can handle data immediately without blocking.
    
    The callback function should have the signature:
        callback(data: StreamingData) -> None
    """
    
    def __init__(self, callback: Callable[[StreamingData], None], 
                 max_callback_time_ms: float = 10.0, parent=None):
        super().__init__(parent)
        
        self._callback = callback
        self._max_callback_time_ms = max_callback_time_ms
        self._last_callback_time = 0.0
    
    def consume_data(self, data: StreamingData) -> None:
        """
        Consume data by invoking the callback.
        
        Args:
            data: StreamingData to process
        """
        if not self._is_active:
            return
        
        try:
            start_time = time.time()
            self._callback(data)
            callback_time_ms = (time.time() - start_time) * 1000.0
            
            self._last_callback_time = callback_time_ms
            
            if callback_time_ms > self._max_callback_time_ms:
                self.logger.warning(
                    f"Callback took {callback_time_ms:.2f}ms "
                    f"(limit: {self._max_callback_time_ms}ms)"
                )
            
            self._update_statistics(consumed=True)
            self.data_processed.emit(self._consumer_id)
            
        except Exception as e:
            self.logger.error(f"Error in callback: {e}")
            self._update_statistics(error=True)
            self.error_occurred.emit(self._consumer_id, str(e))
    
    def can_accept_data(self) -> bool:
        """
        Check if callback consumer can accept data.
        
        Returns:
            True if last callback was fast enough, False otherwise
        """
        return self._last_callback_time <= self._max_callback_time_ms


class QueueConsumer(DataConsumer):
    """
    Consumer that stores data in a thread-safe queue.
    
    This consumer is suitable for scenarios where data processing happens
    in a separate thread or process. It provides configurable queue size
    and overflow handling strategies.
    
    Overflow Strategies:
    - 'drop_oldest': Remove oldest items when queue is full
    - 'drop_newest': Drop new items when queue is full
    - 'block': Block until space is available (not recommended)
    """
    
    def __init__(self, max_queue_size: int = 1000, 
                 overflow_strategy: str = 'drop_oldest', parent=None):
        super().__init__(parent)
        
        self._queue = queue.Queue(maxsize=max_queue_size)
        self._max_queue_size = max_queue_size
        self._overflow_strategy = overflow_strategy
        
        # For drop_oldest strategy, we need a deque
        if overflow_strategy == 'drop_oldest':
            self._deque = deque(maxlen=max_queue_size)
            self._use_deque = True
        else:
            self._use_deque = False
    
    def consume_data(self, data: StreamingData) -> None:
        """
        Consume data by adding to queue.
        
        Args:
            data: StreamingData to queue
        """
        if not self._is_active:
            return
        
        try:
            if self._use_deque:
                # deque automatically handles drop_oldest
                self._deque.append(data)
                self._update_statistics(consumed=True)
            else:
                if self._overflow_strategy == 'drop_newest':
                    try:
                        self._queue.put_nowait(data)
                        self._update_statistics(consumed=True)
                    except queue.Full:
                        self._update_statistics(dropped=True)
                        self.backpressure_detected.emit(self._consumer_id)
                elif self._overflow_strategy == 'block':
                    self._queue.put(data)  # This may block
                    self._update_statistics(consumed=True)
            
            self.data_processed.emit(self._consumer_id)
            
        except Exception as e:
            self.logger.error(f"Error queuing data: {e}")
            self._update_statistics(error=True)
            self.error_occurred.emit(self._consumer_id, str(e))
    
    def can_accept_data(self) -> bool:
        """
        Check if queue consumer can accept data.
        
        Returns:
            True if queue has space or uses drop strategy, False otherwise
        """
        if self._use_deque:
            return True  # deque handles overflow automatically
        
        if self._overflow_strategy == 'drop_newest':
            return not self._queue.full()
        elif self._overflow_strategy == 'block':
            return True  # Always accept (may block)
        else:  # drop_oldest
            return True
    
    def get_data(self, timeout: Optional[float] = None) -> Optional[StreamingData]:
        """
        Get data from the queue.
        
        Args:
            timeout: Maximum time to wait for data (None = no timeout)
            
        Returns:
            StreamingData if available, None if timeout or empty
        """
        try:
            if self._use_deque:
                if self._deque:
                    return self._deque.popleft()
                return None
            else:
                if timeout is None:
                    return self._queue.get_nowait()
                else:
                    return self._queue.get(timeout=timeout)
                    
        except (queue.Empty, IndexError):
            return None
    
    def get_queue_size(self) -> int:
        """
        Get current queue size.
        
        Returns:
            Number of items in queue
        """
        if self._use_deque:
            return len(self._deque)
        else:
            return self._queue.qsize()


class NetworkConsumer(DataConsumer):
    """
    Consumer that forwards data over network protocols.
    
    This consumer integrates with streaming protocols to send data
    over the network. It handles serialization, compression, and
    network error recovery.
    """
    
    def __init__(self, protocol, serialization_format: str = 'json', 
                 compression: bool = False, parent=None):
        super().__init__(parent)
        
        self._protocol = protocol
        self._serialization_format = serialization_format
        self._compression = compression
        
        # Buffer for handling network backpressure
        self._send_buffer = deque(maxlen=100)
        self._is_sending = False
    
    def consume_data(self, data: StreamingData) -> None:
        """
        Consume data by sending over network.
        
        Args:
            data: StreamingData to send
        """
        if not self._is_active:
            return
        
        try:
            # Serialize data
            if self._serialization_format == 'json':
                serialized = json.dumps(data.to_dict())
            else:
                # Could add other formats like MessagePack, Protocol Buffers, etc.
                serialized = str(data)
            
            # Add to send buffer
            self._send_buffer.append(serialized)
            
            # Try to send if not already sending
            if not self._is_sending:
                self._process_send_buffer()
            
            self._update_statistics(consumed=True)
            self.data_processed.emit(self._consumer_id)
            
        except Exception as e:
            self.logger.error(f"Error processing network data: {e}")
            self._update_statistics(error=True)
            self.error_occurred.emit(self._consumer_id, str(e))
    
    def can_accept_data(self) -> bool:
        """
        Check if network consumer can accept data.
        
        Returns:
            True if send buffer has space, False otherwise
        """
        return len(self._send_buffer) < self._send_buffer.maxlen
    
    def _process_send_buffer(self) -> None:
        """Process the send buffer (send queued data)."""
        self._is_sending = True
        
        try:
            while self._send_buffer:
                data = self._send_buffer.popleft()
                self._protocol.send_data(data)
        except Exception as e:
            self.logger.error(f"Error sending data: {e}")
        finally:
            self._is_sending = False


class FileConsumer(DataConsumer):
    """
    Consumer that writes data to files.
    
    This consumer is useful for logging, debugging, and offline analysis.
    It supports various file formats and rotation strategies.
    """
    
    def __init__(self, file_path: str, file_format: str = 'jsonl',
                 max_file_size_mb: int = 100, parent=None):
        super().__init__(parent)
        
        self._file_path = file_path
        self._file_format = file_format
        self._max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self._current_file = None
        self._current_file_size = 0
        self._file_counter = 0
    
    def consume_data(self, data: StreamingData) -> None:
        """
        Consume data by writing to file.
        
        Args:
            data: StreamingData to write
        """
        if not self._is_active:
            return
        
        try:
            # Check if we need to rotate the file
            if (self._current_file is None or 
                self._current_file_size >= self._max_file_size_bytes):
                self._rotate_file()
            
            # Serialize and write data
            if self._file_format == 'jsonl':
                line = json.dumps(data.to_dict()) + '\n'
                self._current_file.write(line)
                self._current_file_size += len(line.encode('utf-8'))
            
            # Flush periodically
            if self._statistics['total_consumed'] % 100 == 0:
                self._current_file.flush()
            
            self._update_statistics(consumed=True)
            self.data_processed.emit(self._consumer_id)
            
        except Exception as e:
            self.logger.error(f"Error writing to file: {e}")
            self._update_statistics(error=True)
            self.error_occurred.emit(self._consumer_id, str(e))
    
    def can_accept_data(self) -> bool:
        """
        Check if file consumer can accept data.
        
        Returns:
            True if file is writable, False otherwise
        """
        return self._current_file is not None and not self._current_file.closed
    
    def _rotate_file(self) -> None:
        """Rotate to a new file."""
        if self._current_file:
            self._current_file.close()
        
        file_path = f"{self._file_path}.{self._file_counter}"
        self._current_file = open(file_path, 'w')
        self._current_file_size = 0
        self._file_counter += 1
        
        self.logger.info(f"Rotated to new file: {file_path}")
    
    def __del__(self):
        """Cleanup file handle."""
        if self._current_file:
            self._current_file.close()