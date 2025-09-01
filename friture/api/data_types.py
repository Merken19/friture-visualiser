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
Data Types and Structures for Friture Streaming API

This module defines the core data types and structures used throughout the
streaming API. All data structures are designed for efficient serialization
and minimal memory overhead.

Design Principles:
- Immutable data structures where possible
- Rich metadata for proper interpretation
- Efficient binary serialization support
- Type safety with runtime validation
- Extensible for future data types
"""

import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Union
import numpy as np


class DataType(Enum):
    """
    Enumeration of supported data types for streaming.
    
    Each data type corresponds to a specific audio analysis widget in Friture
    and has associated metadata and data structure requirements.
    """
    PITCH_TRACKER = "pitch_tracker"
    FFT_SPECTRUM = "fft_spectrum"
    OCTAVE_SPECTRUM = "octave_spectrum"
    SPECTROGRAM = "spectrogram"
    LEVELS = "levels"
    DELAY_ESTIMATOR = "delay_estimator"
    SCOPE = "scope"


@dataclass(frozen=True)
class StreamingMetadata:
    """
    Metadata associated with streaming data.
    
    This provides essential context for interpreting the data correctly,
    including timing information, sampling parameters, and data characteristics.
    
    Attributes:
        timestamp: Unix timestamp when data was captured (seconds)
        stream_time: Audio stream time when data was captured (seconds)
        sample_rate: Audio sampling rate (Hz)
        channels: Number of audio channels
        data_type: Type of analysis data
        sequence_number: Monotonic sequence number for ordering
        widget_id: Identifier of the source widget/dock
        custom_metadata: Additional type-specific metadata
    """
    timestamp: float
    stream_time: float
    sample_rate: int
    channels: int
    data_type: DataType
    sequence_number: int
    widget_id: str
    custom_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PitchData:
    """
    Pitch tracking analysis results.
    
    Contains fundamental frequency detection results with confidence metrics
    and musical note information.
    
    Attributes:
        frequency_hz: Detected fundamental frequency in Hz (None if no pitch detected)
        confidence: Confidence score [0.0, 1.0] for the detection
        note_name: Musical note name (e.g., "A4", "C#3") if frequency is valid
        amplitude_db: Signal amplitude in dB at the detected frequency
        harmonic_clarity: Measure of harmonic structure clarity [0.0, 1.0]
    """
    frequency_hz: Optional[float]
    confidence: float
    note_name: Optional[str]
    amplitude_db: float
    harmonic_clarity: float


@dataclass(frozen=True)
class FFTSpectrumData:
    """
    FFT spectrum analysis results.

    Contains frequency domain representation of the audio signal with
    associated frequency bins and processing parameters.

    Attributes:
        frequencies: Frequency bin centers in Hz
        magnitudes_db: Magnitude spectrum in dB scale (10 * log10 of power spectrum)
        phases: Phase spectrum in radians (optional)
        fft_size: FFT size used for analysis
        window_type: Window function applied ("hann", "hamming", etc.)
        overlap_factor: Overlap factor used [0.0, 1.0)
        weighting: Frequency weighting applied ("none", "A", "B", "C")
        peak_frequency: Frequency of maximum magnitude
        peak_magnitude: Maximum magnitude in dB
    """
    frequencies: np.ndarray
    magnitudes_db: np.ndarray
    phases: Optional[np.ndarray]
    fft_size: int
    window_type: str
    overlap_factor: float
    weighting: str
    peak_frequency: float
    peak_magnitude: float


@dataclass(frozen=True)
class OctaveSpectrumData:
    """
    Octave band spectrum analysis results.
    
    Contains energy measurements in standardized octave or fractional-octave bands
    according to IEC standards.
    
    Attributes:
        center_frequencies: Center frequencies of octave bands in Hz
        band_energies_db: Energy in each band in dB
        band_labels: Human-readable labels for each band
        bands_per_octave: Number of bands per octave (1, 3, 6, 12, 24)
        weighting: Frequency weighting applied ("none", "A", "B", "C")
        response_time: Integration time constant in seconds
        overall_level: Overall sound pressure level in dB
    """
    center_frequencies: np.ndarray
    band_energies_db: np.ndarray
    band_labels: List[str]
    bands_per_octave: int
    weighting: str
    response_time: float
    overall_level: float


@dataclass(frozen=True)
class LevelsData:
    """
    Audio level measurements.
    
    Contains peak and RMS level measurements for each channel with
    ballistic characteristics according to audio standards.
    
    Attributes:
        peak_levels_db: Peak levels per channel in dB FS
        rms_levels_db: RMS levels per channel in dB FS
        peak_hold_levels_db: Peak hold levels with ballistic decay
        channel_labels: Labels for each channel
        integration_time: RMS integration time in seconds
        peak_hold_time: Peak hold time in seconds
    """
    peak_levels_db: np.ndarray
    rms_levels_db: np.ndarray
    peak_hold_levels_db: np.ndarray
    channel_labels: List[str]
    integration_time: float
    peak_hold_time: float


@dataclass(frozen=True)
class SpectrogramData:
    """
    Time-frequency analysis results for spectrograms.
    
    Contains a 2D array representing the spectrum over time, which is
    ideal for waterfall displays and detailed time-frequency analysis.
    
    Attributes:
        timestamps: Array of timestamps for each time slice (seconds)
        frequencies: Array of frequency bins (Hz)
        magnitudes_db: 2D array of magnitudes (time x frequency)
        fft_size: FFT size used for analysis
        overlap_factor: Overlap factor used [0.0, 1.0)
        window_type: Window function applied
    """
    timestamps: np.ndarray
    frequencies: np.ndarray
    magnitudes_db: np.ndarray
    fft_size: int
    overlap_factor: float
    window_type: str


@dataclass(frozen=True)
class ScopeData:
    """
    Time-domain waveform data.
    
    Contains a segment of the raw audio waveform, suitable for oscilloscope-style
    displays and time-domain analysis.
    
    Attributes:
        timestamps: Array of timestamps for each sample (seconds)
        samples: Array of audio samples (channel x time)
        trigger_mode: Triggering mode used ('auto', 'normal', 'free')
        trigger_level: Triggering level
    """
    timestamps: np.ndarray
    samples: np.ndarray
    trigger_mode: str
    trigger_level: float


@dataclass(frozen=True)
class DelayEstimatorData:
    """
    Delay estimation results between two audio channels.
    
    Contains cross-correlation analysis results for measuring time delays
    and phase relationships between audio signals.
    
    Attributes:
        delay_ms: Estimated delay in milliseconds
        delay_samples: Estimated delay in samples
        confidence: Confidence of the delay estimate [0.0, 1.0]
        correlation_peak: Maximum correlation value
        polarity: Signal polarity relationship (\"in_phase\", \"reversed\", \"unknown\")
        distance_m: Equivalent distance in meters (assuming sound speed 340 m/s)
    """
    delay_ms: float
    delay_samples: int
    confidence: float
    correlation_peak: float
    polarity: str
    distance_m: float


@dataclass(frozen=True)
class StreamingData:
    """
    Container for all streaming data with metadata.
    
    This is the top-level data structure that gets transmitted through
    the streaming API. It contains both the analysis results and all
    necessary metadata for proper interpretation.
    
    Attributes:
        metadata: Streaming metadata
        data: Analysis results (type depends on data_type)
    """
    metadata: StreamingMetadata
    data: Union[PitchData, FFTSpectrumData, OctaveSpectrumData, 
                LevelsData, DelayEstimatorData, SpectrogramData, ScopeData]
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.
        
        Returns:
            Dictionary representation suitable for JSON serialization
        """
        result = {
            'metadata': {
                'timestamp': self.metadata.timestamp,
                'stream_time': self.metadata.stream_time,
                'sample_rate': self.metadata.sample_rate,
                'channels': self.metadata.channels,
                'data_type': self.metadata.data_type.value,
                'sequence_number': self.metadata.sequence_number,
                'widget_id': self.metadata.widget_id,
                'custom_metadata': self.metadata.custom_metadata
            },
            'data': self._data_to_dict()
        }
        return result
    
    def _data_to_dict(self) -> Dict[str, Any]:
        """Convert data payload to dictionary format."""
        if isinstance(self.data, PitchData):
            return {
                'frequency_hz': self.data.frequency_hz,
                'confidence': self.data.confidence,
                'note_name': self.data.note_name,
                'amplitude_db': self.data.amplitude_db,
                'harmonic_clarity': self.data.harmonic_clarity
            }
        elif isinstance(self.data, FFTSpectrumData):
            return {
                'frequencies': self.data.frequencies.tolist(),
                'magnitudes_db': self.data.magnitudes_db.tolist(),
                'phases': self.data.phases.tolist() if self.data.phases is not None else None,
                'fft_size': self.data.fft_size,
                'window_type': self.data.window_type,
                'overlap_factor': self.data.overlap_factor,
                'weighting': self.data.weighting,
                'peak_frequency': self.data.peak_frequency,
                'peak_magnitude': self.data.peak_magnitude
            }
        elif isinstance(self.data, OctaveSpectrumData):
            return {
                'center_frequencies': self.data.center_frequencies.tolist(),
                'band_energies_db': self.data.band_energies_db.tolist(),
                'band_labels': self.data.band_labels,
                'bands_per_octave': self.data.bands_per_octave,
                'weighting': self.data.weighting,
                'response_time': self.data.response_time,
                'overall_level': self.data.overall_level
            }
        elif isinstance(self.data, LevelsData):
            return {
                'peak_levels_db': self.data.peak_levels_db.tolist(),
                'rms_levels_db': self.data.rms_levels_db.tolist(),
                'peak_hold_levels_db': self.data.peak_hold_levels_db.tolist(),
                'channel_labels': self.data.channel_labels,
                'integration_time': self.data.integration_time,
                'peak_hold_time': self.data.peak_hold_time
            }
        elif isinstance(self.data, DelayEstimatorData):
            return {
                'delay_ms': self.data.delay_ms,
                'delay_samples': self.data.delay_samples,
                'confidence': self.data.confidence,
                'correlation_peak': self.data.correlation_peak,
                'polarity': self.data.polarity,
                'distance_m': self.data.distance_m
            }
        elif isinstance(self.data, SpectrogramData):
            return {
                'timestamps': self.data.timestamps.tolist(),
                'frequencies': self.data.frequencies.tolist(),
                'magnitudes_db': self.data.magnitudes_db.tolist(),
                'fft_size': self.data.fft_size,
                'overlap_factor': self.data.overlap_factor,
                'window_type': self.data.window_type
            }
        elif isinstance(self.data, ScopeData):
            return {
                'timestamps': self.data.timestamps.tolist(),
                'samples': self.data.samples.tolist(),
                'trigger_mode': self.data.trigger_mode,
                'trigger_level': self.data.trigger_level
            }
        else:
            return {}


def create_streaming_data(data_type: DataType, 
                         widget_id: str,
                         data_payload: Any,
                         stream_time: float,
                         sample_rate: int,
                         channels: int,
                         sequence_number: int,
                         custom_metadata: Optional[Dict[str, Any]] = None) -> StreamingData:
    """
    Factory function to create StreamingData instances.
    
    Args:
        data_type: Type of analysis data
        widget_id: Identifier of the source widget
        data_payload: The actual analysis results
        stream_time: Audio stream time when data was captured
        sample_rate: Audio sampling rate
        channels: Number of audio channels
        sequence_number: Monotonic sequence number
        custom_metadata: Additional metadata
        
    Returns:
        StreamingData instance ready for transmission
    """
    metadata = StreamingMetadata(
        timestamp=time.time(),
        stream_time=stream_time,
        sample_rate=sample_rate,
        channels=channels,
        data_type=data_type,
        sequence_number=sequence_number,
        widget_id=widget_id,
        custom_metadata=custom_metadata or {}
    )
    
    return StreamingData(metadata=metadata, data=data_payload)
