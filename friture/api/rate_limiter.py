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
Rate Limiting for Friture Streaming API

This module implements rate limiting to prevent overwhelming consumers
and network connections with high-frequency data updates. It uses a
token bucket algorithm for smooth rate limiting with burst capability.

Features:
- Per-data-type rate limiting
- Token bucket algorithm with configurable burst size
- Adaptive rate limiting based on consumer performance
- Statistics and monitoring
- Thread-safe implementation

The rate limiter is designed to be lightweight and have minimal impact
on Friture's main processing loop while providing effective protection
against data flooding.
"""

import logging
import threading
import time
from collections import defaultdict
from typing import Dict

from .data_types import DataType


class TokenBucket:
    """
    Token bucket implementation for rate limiting.
    
    The token bucket algorithm allows for smooth rate limiting with
    the ability to handle bursts of activity up to a configured limit.
    
    Attributes:
        capacity: Maximum number of tokens in the bucket
        tokens: Current number of tokens
        fill_rate: Rate at which tokens are added (tokens per second)
        last_update: Last time tokens were added
    """
    
    def __init__(self, capacity: float, fill_rate: float):
        self.capacity = capacity
        self.tokens = capacity
        self.fill_rate = fill_rate
        self.last_update = time.time()
        self._lock = threading.Lock()
    
    def consume(self, tokens: float = 1.0) -> bool:
        """
        Try to consume tokens from the bucket.
        
        Args:
            tokens: Number of tokens to consume
            
        Returns:
            True if tokens were consumed, False if insufficient tokens
        """
        with self._lock:
            now = time.time()
            
            # Add tokens based on elapsed time
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)
            self.last_update = now
            
            # Check if we have enough tokens
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            else:
                return False
    
    def get_tokens(self) -> float:
        """
        Get current number of tokens.
        
        Returns:
            Current token count
        """
        with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)
            self.last_update = now
            return self.tokens


class RateLimiter:
    """
    Rate limiter for streaming API data types.
    
    Manages rate limiting for different data types using token bucket
    algorithms. Each data type can have independent rate limits and
    burst capabilities.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Token buckets for each data type
        self._buckets: Dict[DataType, TokenBucket] = {}
        
        # Rate limit configurations
        self._rate_limits: Dict[DataType, float] = {}
        
        # Statistics
        self._statistics = defaultdict(int)
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Default rate limits (Hz)
        self._default_limits = {
            DataType.PITCH_TRACKER: 50.0,      # 50 Hz for pitch updates
            DataType.FFT_SPECTRUM: 30.0,       # 30 Hz for spectrum updates
            DataType.OCTAVE_SPECTRUM: 20.0,    # 20 Hz for octave spectrum
            DataType.LEVELS: 100.0,            # 100 Hz for level meters
            DataType.DELAY_ESTIMATOR: 10.0,    # 10 Hz for delay estimation
            DataType.SPECTROGRAM: 25.0,        # 25 Hz for spectrogram updates
            DataType.SCOPE: 60.0               # 60 Hz for scope updates
        }
        
        # Initialize with default limits
        for data_type, rate_limit in self._default_limits.items():
            self.set_rate_limit(data_type, rate_limit)
    
    def set_rate_limit(self, data_type: DataType, max_rate_hz: float) -> None:
        """
        Set rate limit for a data type.
        
        Args:
            data_type: Data type to limit
            max_rate_hz: Maximum rate in Hz (0 = no limit)
        """
        with self._lock:
            if max_rate_hz <= 0:
                # Remove rate limiting
                if data_type in self._buckets:
                    del self._buckets[data_type]
                if data_type in self._rate_limits:
                    del self._rate_limits[data_type]
                self.logger.info(f"Removed rate limit for {data_type}")
            else:
                # Set up token bucket
                # Allow burst of 2x the rate for 1 second
                capacity = max_rate_hz * 2.0
                self._buckets[data_type] = TokenBucket(capacity, max_rate_hz)
                self._rate_limits[data_type] = max_rate_hz
                self.logger.info(f"Set rate limit for {data_type} to {max_rate_hz} Hz")
    
    def should_process(self, data_type: DataType) -> bool:
        """
        Check if data should be processed based on rate limits.
        
        Args:
            data_type: Type of data to check
            
        Returns:
            True if data should be processed, False if rate limited
        """
        with self._lock:
            # No rate limit configured
            if data_type not in self._buckets:
                self._statistics[f'{data_type.value}_allowed'] += 1
                return True
            
            # Check token bucket
            bucket = self._buckets[data_type]
            if bucket.consume(1.0):
                self._statistics[f'{data_type.value}_allowed'] += 1
                return True
            else:
                self._statistics[f'{data_type.value}_rate_limited'] += 1
                return False
    
    def get_rate_limit(self, data_type: DataType) -> Optional[float]:
        """
        Get current rate limit for a data type.
        
        Args:
            data_type: Data type to query
            
        Returns:
            Rate limit in Hz, or None if no limit set
        """
        return self._rate_limits.get(data_type)
    
    def get_statistics(self) -> Dict[str, int]:
        """
        Get rate limiting statistics.
        
        Returns:
            Dictionary of statistics
        """
        with self._lock:
            stats = dict(self._statistics)
            
            # Add current token counts
            for data_type, bucket in self._buckets.items():
                stats[f'{data_type.value}_tokens'] = bucket.get_tokens()
            
            return stats
    
    def reset_statistics(self) -> None:
        """Reset all statistics counters."""
        with self._lock:
            self._statistics.clear()
            self.logger.info("Rate limiter statistics reset")