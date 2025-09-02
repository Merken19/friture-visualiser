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
from typing import Dict, Optional, Any, List

from PyQt5.QtCore import QObject, QSettings

from .streaming_api import get_streaming_api
from .data_types import DataType
from .producers import (PitchTrackerProducer, FFTSpectrumProducer,
                       OctaveSpectrumProducer, LevelsProducer, DelayEstimatorProducer,
                       SpectrogramProducer, ScopeProducer, RawAudioProducer)
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
    
    def __init__(self, dock_manager, audio_buffer, parent=None):
        super().__init__(parent)
        
        self.logger = logging.getLogger(__name__)
        self.dock_manager = dock_manager
        self.audio_buffer = audio_buffer
        self.streaming_api = get_streaming_api()
        
        # Track active producers
        self._active_producers: Dict[str, Any] = {}
        
        # Widget type to producer class mapping
        # These IDs must match the widget IDs defined in widgetdict.py
        self._producer_classes = {
            8: PitchTrackerProducer,    # Pitch Tracker
            2: FFTSpectrumProducer,     # FFT Spectrum
            4: OctaveSpectrumProducer,  # Octave Spectrum
            3: SpectrogramProducer,     # 2D Spectrogram (corrected from 5 to 3)
            1: ScopeProducer,           # Scope
            6: DelayEstimatorProducer,  # Delay Estimator
            # Note: Levels widget is handled separately as it's not a dock
        }
        
        # Connect to dock manager signals
        if hasattr(self.dock_manager, 'new_dock_created'):  # Ideal signal
            self.dock_manager.new_dock_created.connect(self._setup_dock_producer)
        if hasattr(self.dock_manager, 'dock_about_to_be_destroyed'): # Ideal signal
            self.dock_manager.dock_about_to_be_destroyed.connect(self._teardown_dock_producer)
        
        # Setup existing docks
        self._setup_existing_docks()
        
        # Connect to audio buffer AFTER all widget connections are established
        # This ensures widgets process data before streaming API extracts it
        self.audio_buffer.new_data_available.connect(self._on_new_audio_data_from_buffer)
        
        self.logger.info("StreamingIntegration initialized")

    def _teardown_dock_producer(self, dock) -> None:
        """
        Teardown the producer for a dock that is being destroyed.
        """
        try:
            dock_name = dock.objectName()
            if dock_name in self._active_producers:
                producer = self._active_producers.pop(dock_name)
                producer.stop()
                # Unregister from API if necessary, though stopping should be enough
                self.logger.info(f"Tore down producer for dock {dock_name}")
        except Exception as e:
            self.logger.error(f"Error tearing down producer for dock: {e}")
    
    def _on_new_audio_data_from_buffer(self, floatdata):
        """
        Handle new audio data from buffer and trigger producer data extraction.
        
        This method is called after widgets have processed the audio data,
        ensuring that producers extract fresh, processed data.
        
        Args:
            floatdata: Audio data from the buffer
        """
        try:
            # Trigger data extraction for all active producers
            for producer in self._active_producers.values():
                if hasattr(producer, '_process_data_from_widget') and producer._is_active:
                    producer._process_data_from_widget(floatdata)
        except Exception as e:
            self.logger.error(f"Error processing audio data for streaming: {e}")
    
    def _connect_dock_signals(self) -> None:
        """Connect to dock manager signals for automatic setup."""
        # Note: This would need to be adapted based on actual dock manager signals
        # For now, we'll implement a polling approach or manual setup
        pass
    
    def _setup_existing_docks(self) -> None:
        """Setup producers for existing docks."""
        try:
            self.logger.info(f"Setting up producers for {len(self.dock_manager.docks)} existing docks")
            for dock in self.dock_manager.docks:
                self.logger.info(f"Processing dock: {dock.objectName()}, widgetId: {getattr(dock, 'widgetId', 'None')}")
                self._setup_dock_producer(dock)
        except Exception as e:
            self.logger.error(f"Error setting up existing docks: {e}")
    
    def _setup_dock_producer(self, dock) -> None:
        """
        Setup a producer for a dock.

        Args:
            dock: Dock instance to setup producer for
        """
        dock_name = dock.objectName()
        try:
            self.logger.info(f"Setting up producer for dock {dock_name}")

            if not hasattr(dock, 'widgetId'):
                self.logger.warning(f"Dock {dock_name} has no widgetId attribute")
                return

            if not hasattr(dock, 'audiowidget'):
                self.logger.warning(f"Dock {dock_name} has no audiowidget attribute")
                return

            widget_id = dock.widgetId
            widget = dock.audiowidget

            self.logger.info(f"Dock {dock_name}: widgetId={widget_id}, widget={type(widget).__name__}")

            if widget_id in self._producer_classes:
                producer_class = self._producer_classes[widget_id]
                self.logger.info(f"Creating {producer_class.__name__} for dock {dock_name}")

                producer = producer_class(widget, dock_name, self)

                # Register with streaming API
                data_type = producer.get_data_type()
                self.streaming_api.register_producer(data_type, producer)

                # Track the producer
                self._active_producers[dock_name] = producer

                self.logger.info(f"Successfully setup producer for dock {dock_name} (type: {data_type})")
            else:
                self.logger.warning(f"No producer class found for widgetId {widget_id} in dock {dock_name}")

        except Exception as e:
            self.logger.error(f"Error setting up producer for dock {dock_name}: {e}")
    
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

    def setup_raw_audio_producer(self, audio_backend) -> None:
        """
        Setup producer for raw microphone audio data.

        This producer connects directly to the audio backend for minimal overhead
        and provides unprocessed audio samples for real-time streaming applications.

        Args:
            audio_backend: AudioBackend instance
        """
        try:
            producer = RawAudioProducer(audio_backend, "raw_audio_producer", self)
            self.streaming_api.register_producer(DataType.RAW_AUDIO, producer)
            self._active_producers["raw_audio_producer"] = producer

            self.logger.info("Setup producer for raw audio data")

        except Exception as e:
            self.logger.error(f"Error setting up raw audio producer: {e}")

    def refresh_dock_producers(self) -> None:
        """
        Refresh producers for all docks. This can be called after the application
        is fully initialized to ensure all docks have producers set up.
        """
        self.logger.info("Refreshing dock producers...")
        self._setup_existing_docks()
        self.logger.info(f"Active producers after refresh: {list(self._active_producers.keys())}")
    
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


def setup_streaming_integration(dock_manager, levels_widget=None, audio_buffer=None, audio_backend=None) -> StreamingIntegration:
    """
    Setup streaming integration for Friture.

    This is the main entry point for enabling streaming API functionality
    in Friture. It should be called during Friture initialization.

    Args:
        dock_manager: Friture's dock manager instance
        levels_widget: Levels widget instance (optional)
        audio_buffer: Audio buffer instance (required for proper data flow)
        audio_backend: AudioBackend instance (optional, for raw audio producer)

    Returns:
        StreamingIntegration instance
    """
    if audio_buffer is None:
        raise ValueError("audio_buffer is required for streaming integration")

    integration = StreamingIntegration(dock_manager, audio_buffer)

    if levels_widget:
        integration.setup_levels_producer(levels_widget)

    if audio_backend:
        integration.setup_raw_audio_producer(audio_backend)

    return integration


def create_default_streaming_setup(integration: StreamingIntegration, 
                                   enable_websocket: bool = True,
                                   enable_tcp: bool = False,
                                   enable_udp: bool = False,
                                   enable_http_sse: bool = False) -> None:
    """
    Create a default streaming setup with common protocols and consumers.
    
    Args:
        integration: StreamingIntegration instance
        enable_websocket: Enable WebSocket protocol
        enable_tcp: Enable TCP protocol
        enable_udp: Enable UDP protocol
        enable_http_sse: Enable HTTP SSE protocol
    """
    from friture.api.consumers import NetworkConsumer

    logger = logging.getLogger(__name__)
    api = integration.streaming_api

    # Clear any existing protocols first
    api.clear_protocols()
    logger.debug("Cleared existing protocols from streaming API.")

    def add_protocol_with_consumer(name: str, protocol_cls, enabled: bool):
        if not enabled:
            logger.debug("%s protocol disabled by config.", name.upper())
            return

        try:
            protocol = protocol_cls()
            api.add_protocol(protocol)
            logger.info("%s protocol added successfully.", name.upper())
        except Exception as e:
            logger.warning("Failed to add %s protocol: %s", name.upper(), e)
            return

        try:
            consumer = NetworkConsumer(protocol=protocol)
            # Register the consumer for the main data types
            for dtype in [
                DataType.LEVELS,
                DataType.FFT_SPECTRUM,
                DataType.OCTAVE_SPECTRUM,
                DataType.PITCH_TRACKER,
                DataType.SPECTROGRAM,
                DataType.SCOPE,
                DataType.RAW_AUDIO,
            ]:
                api.register_consumer(dtype, consumer)
                logger.info(
                    "Registered %s consumer for data type %s", name.upper(), dtype.name
                )
            logger.info("Default %s consumer registered successfully.", name.upper())
        except Exception as e:
            logger.warning("Failed to register consumer for %s protocol: %s", name.upper(), e)

    # Add protocols + consumers
    add_protocol_with_consumer("websocket", WebSocketProtocol, enable_websocket)
    add_protocol_with_consumer("tcp", TCPProtocol, enable_tcp)
    add_protocol_with_consumer("udp", UDPProtocol, enable_udp)
    add_protocol_with_consumer("http_sse", HTTPSSEProtocol, enable_http_sse)

    # Set reasonable rate limits / Friture is designed with 25Hz in mind
    try:
        api.set_rate_limit(DataType.PITCH_TRACKER, 25.0)   # 25 Hz
        api.set_rate_limit(DataType.FFT_SPECTRUM, 25.0)    # 25 Hz
        api.set_rate_limit(DataType.OCTAVE_SPECTRUM, 25.0) # 25 Hz
        api.set_rate_limit(DataType.LEVELS, 25.0)          # 25 Hz
        api.set_rate_limit(DataType.RAW_AUDIO, 25.0)       # 25 Hz for raw audio
        logger.info("Rate limits set to 25 Hz for all major data types.")
    except Exception as e:
        logger.warning("Failed to set rate limits: %s", e)

    logger.info("Default streaming setup completed successfully.")


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
                print("Tried to add websocket protocol in integration.py load_streaming_settings")
            elif protocol_type == "TCPProtocol":
                protocol = TCPProtocol(host, port)
                api.add_protocol(protocol)
                print("Tried to add TCP protocol in integration.py load_streaming_settings")
            # Add other protocol types as needed
            
            settings.endGroup()
        settings.endGroup()
        
        # Start streaming if it was enabled
        if enabled:
            api.start_streaming()
        
    finally:
        settings.endGroup()