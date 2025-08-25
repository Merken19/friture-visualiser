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
Integration Module for Friture Streaming API

This module provides seamless integration between the streaming API
and Friture's existing dock system. It automatically detects available
widgets and sets up appropriate producers with minimal configuration.

Features:
- Automatic widget detection and producer setup
- Dynamic producer lifecycle management
- Integration with Friture's settings system
- Backward compatibility with existing code
- Performance monitoring and optimization

The integration is designed to be completely transparent to existing
Friture functionality while adding streaming capabilities.
"""

import logging
from typing import Dict, Optional, Any

from PyQt5.QtCore import QObject, QSettings

from .streaming_api import get_streaming_api
from .data_types import DataType
from .producers import (PitchTrackerProducer, FFTSpectrumProducer, 
                       OctaveSpectrumProducer, LevelsProducer, DelayEstimatorProducer)
from .consumers import CallbackConsumer, QueueConsumer, NetworkConsumer
from .protocols import WebSocketProtocol, TCPProtocol, UDPProtocol, HTTPSSEProtocol
from ..widgetdict import widgetIds


class StreamingIntegration(QObject):
    """
    Integration manager for Friture streaming API.
    
    This class handles the integration between Friture's dock system
    and the streaming API, automatically setting up producers and
    managing their lifecycle based on dock creation and destruction.
    """
    
    def __init__(self, dock_manager, parent=None):
        super().__init__(parent)
        
        self.logger = logging.getLogger(__name__)
        self.dock_manager = dock_manager
        self.streaming_api = get_streaming_api()
        
        # Track active producers
        self._active_producers: Dict[str, Any] = {}
        
        # Widget type to producer class mapping
        self._producer_classes = {
            8: PitchTrackerProducer,    # Pitch Tracker
            2: FFTSpectrumProducer,     # FFT Spectrum
            4: OctaveSpectrumProducer,  # Octave Spectrum
            6: DelayEstimatorProducer,  # Delay Estimator
            # Note: Levels widget is handled separately as it's not a dock
        }
        
        # Connect to dock manager signals
        self._connect_dock_signals()
        
        # Setup existing docks
        self._setup_existing_docks()
        
        self.logger.info("StreamingIntegration initialized")
    
    def _connect_dock_signals(self) -> None:
        """Connect to dock manager signals for automatic setup."""
        # Note: This would need to be adapted based on actual dock manager signals
        # For now, we'll implement a polling approach or manual setup
        pass
    
    def _setup_existing_docks(self) -> None:
        """Setup producers for existing docks."""
        try:
            for dock in self.dock_manager.docks:
                self._setup_dock_producer(dock)
        except Exception as e:
            self.logger.error(f"Error setting up existing docks: {e}")
    
    def _setup_dock_producer(self, dock) -> None:
        """
        Setup a producer for a dock.
        
        Args:
            dock: Dock instance to setup producer for
        """
        try:
            if not hasattr(dock, 'widgetId') or not hasattr(dock, 'audiowidget'):
                return
            
            widget_id = dock.widgetId
            widget = dock.audiowidget
            dock_name = dock.objectName()
            
            if widget_id in self._producer_classes:
                producer_class = self._producer_classes[widget_id]
                producer = producer_class(widget, dock_name, self)
                
                # Register with streaming API
                data_type = producer.get_data_type()
                self.streaming_api.register_producer(data_type, producer)
                
                # Track the producer
                self._active_producers[dock_name] = producer
                
                self.logger.info(f"Setup producer for dock {dock_name} (type: {data_type})")
            
        except Exception as e:
            self.logger.error(f"Error setting up producer for dock: {e}")
    
    def setup_levels_producer(self, levels_widget) -> None:
        """
        Setup producer for the levels widget.
        
        Args:
            levels_widget: Levels widget instance
        """
        try:
            producer = LevelsProducer(levels_widget, "levels_widget", self)
            self.streaming_api.register_producer(DataType.LEVELS, producer)
            self._active_producers["levels_widget"] = producer
            
            self.logger.info("Setup producer for levels widget")
            
        except Exception as e:
            self.logger.error(f"Error setting up levels producer: {e}")
    
    def get_available_data_types(self) -> List[DataType]:
        """
        Get list of currently available data types.
        
        Returns:
            List of DataType enums for active producers
        """
        data_types = []
        for producer in self._active_producers.values():
            data_types.append(producer.get_data_type())
        return data_types
    
    def get_producer_info(self, dock_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a producer.
        
        Args:
            dock_name: Name of the dock
            
        Returns:
            Dictionary with producer information
        """
        if dock_name not in self._active_producers:
            return None
        
        producer = self._active_producers[dock_name]
        return {
            'dock_name': dock_name,
            'data_type': producer.get_data_type().value,
            'is_active': producer._is_active,
            'sequence_number': producer._sequence_number,
            'custom_metadata': producer.get_custom_metadata()
        }


def setup_streaming_integration(dock_manager, levels_widget=None) -> StreamingIntegration:
    """
    Setup streaming integration for Friture.
    
    This is the main entry point for enabling streaming API functionality
    in Friture. It should be called during Friture initialization.
    
    Args:
        dock_manager: Friture's dock manager instance
        levels_widget: Levels widget instance (optional)
        
    Returns:
        StreamingIntegration instance
    """
    integration = StreamingIntegration(dock_manager)
    
    if levels_widget:
        integration.setup_levels_producer(levels_widget)
    
    return integration


def create_default_streaming_setup(integration: StreamingIntegration, 
                                 enable_websocket: bool = True,
                                 enable_tcp: bool = False,
                                 enable_udp: bool = False,
                                 enable_http_sse: bool = False) -> None:
    """
    Create a default streaming setup with common protocols.
    
    Args:
        integration: StreamingIntegration instance
        enable_websocket: Enable WebSocket protocol
        enable_tcp: Enable TCP protocol
        enable_udp: Enable UDP protocol
        enable_http_sse: Enable HTTP SSE protocol
    """
    api = integration.streaming_api
    
    # Add protocols
    if enable_websocket:
        websocket_protocol = WebSocketProtocol()
        api.add_protocol(websocket_protocol)
    
    if enable_tcp:
        tcp_protocol = TCPProtocol()
        api.add_protocol(tcp_protocol)
    
    if enable_udp:
        udp_protocol = UDPProtocol()
        api.add_protocol(udp_protocol)
    
    if enable_http_sse:
        sse_protocol = HTTPSSEProtocol()
        api.add_protocol(sse_protocol)
    
    # Set reasonable rate limits
    api.set_rate_limit(DataType.PITCH_TRACKER, 20.0)  # 20 Hz
    api.set_rate_limit(DataType.FFT_SPECTRUM, 15.0)   # 15 Hz
    api.set_rate_limit(DataType.OCTAVE_SPECTRUM, 10.0) # 10 Hz
    api.set_rate_limit(DataType.LEVELS, 30.0)         # 30 Hz
    
    logging.getLogger(__name__).info("Default streaming setup created")


def save_streaming_settings(settings: QSettings, integration: StreamingIntegration) -> None:
    """
    Save streaming API settings.
    
    Args:
        settings: QSettings instance
        integration: StreamingIntegration instance
    """
    settings.beginGroup("StreamingAPI")
    
    try:
        # Save enabled state
        api = integration.streaming_api
        settings.setValue("enabled", api._is_streaming)
        
        # Save rate limits
        settings.beginGroup("RateLimits")
        for data_type in DataType:
            rate_limit = api._rate_limiter.get_rate_limit(data_type)
            if rate_limit is not None:
                settings.setValue(data_type.value, rate_limit)
        settings.endGroup()
        
        # Save protocol configurations
        settings.beginGroup("Protocols")
        for i, protocol in enumerate(api._protocols):
            settings.beginGroup(f"protocol_{i}")
            settings.setValue("type", type(protocol).__name__)
            settings.setValue("host", protocol.host)
            settings.setValue("port", protocol.port)
            settings.endGroup()
        settings.endGroup()
        
    finally:
        settings.endGroup()


def load_streaming_settings(settings: QSettings, integration: StreamingIntegration) -> None:
    """
    Load streaming API settings.
    
    Args:
        settings: QSettings instance
        integration: StreamingIntegration instance
    """
    settings.beginGroup("StreamingAPI")
    
    try:
        # Load enabled state
        enabled = settings.value("enabled", False, type=bool)
        
        # Load rate limits
        settings.beginGroup("RateLimits")
        api = integration.streaming_api
        for data_type in DataType:
            rate_limit = settings.value(data_type.value, type=float)
            if rate_limit is not None:
                api.set_rate_limit(data_type, rate_limit)
        settings.endGroup()
        
        # Load protocol configurations
        settings.beginGroup("Protocols")
        for group in settings.childGroups():
            settings.beginGroup(group)
            protocol_type = settings.value("type", "")
            host = settings.value("host", "localhost")
            port = settings.value("port", 8080, type=int)
            
            # Create protocol based on type
            if protocol_type == "WebSocketProtocol":
                protocol = WebSocketProtocol(host, port)
                api.add_protocol(protocol)
            elif protocol_type == "TCPProtocol":
                protocol = TCPProtocol(host, port)
                api.add_protocol(protocol)
            # Add other protocol types as needed
            
            settings.endGroup()
        settings.endGroup()
        
        # Start streaming if it was enabled
        if enabled:
            api.start_streaming()
        
    finally:
        settings.endGroup()