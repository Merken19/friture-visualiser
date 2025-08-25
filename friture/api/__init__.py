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
Friture Streaming API

This module provides a high-performance, zero-overhead streaming API for accessing
real-time audio analysis data from Friture docks. The API is designed to enable
external applications to consume Friture's audio processing results without
impacting the main application's performance.

Key Features:
- Zero-copy data access where possible
- Configurable streaming protocols (WebSocket, TCP, UDP, HTTP SSE)
- Type-safe data structures with comprehensive metadata
- Extensible architecture for adding new data sources
- Built-in rate limiting and backpressure handling
- Comprehensive logging and monitoring

Supported Data Sources:
- Pitch Tracker: Real-time fundamental frequency detection
- FFT Spectrum: Frequency domain analysis with configurable resolution
- Octave Spectrum: Octave band analysis with A/B/C weighting
- Spectrogram: Time-frequency analysis data
- Levels: Peak and RMS level measurements
- Delay Estimator: Cross-correlation delay measurements

Example Usage:
    from friture.api import StreamingAPI, DataType
    
    # Initialize the API
    api = StreamingAPI()
    
    # Register for pitch data
    api.register_consumer(DataType.PITCH_TRACKER, my_callback)
    
    # Start streaming
    api.start_streaming()
"""

from .streaming_api import StreamingAPI
from .data_types import DataType, StreamingData
from .protocols import WebSocketProtocol, TCPProtocol, UDPProtocol, HTTPSSEProtocol
from .consumers import DataConsumer, CallbackConsumer, QueueConsumer
from .producers import PitchTrackerProducer, FFTSpectrumProducer, OctaveSpectrumProducer

__all__ = [
    'StreamingAPI',
    'DataType',
    'StreamingData',
    'WebSocketProtocol',
    'TCPProtocol', 
    'UDPProtocol',
    'HTTPSSEProtocol',
    'DataConsumer',
    'CallbackConsumer',
    'QueueConsumer',
    'PitchTrackerProducer',
    'FFTSpectrumProducer',
    'OctaveSpectrumProducer'
]