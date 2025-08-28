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
Data Producers for Friture Streaming API

Producers are responsible for extracting data from Friture widgets and
converting it into standardized streaming data formats. Each producer
is designed to have minimal performance impact on the source widget.

Design Principles:
- Zero-copy data access where possible
- Minimal computational overhead
- Non-blocking operation
- Automatic lifecycle management
- Rich metadata extraction

Implementation Notes:
- Producers connect to existing widget signals to avoid polling
- Data extraction happens in the main thread to avoid synchronization issues
- Producers can be started/stopped independently based on consumer demand
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import numpy as np

from PyQt5.QtCore import QObject, pyqtSignal

from .data_types import (DataType, PitchData, FFTSpectrumData, OctaveSpectrumData,
                        LevelsData, DelayEstimatorData, StreamingMetadata,
                        create_streaming_data)
from ..audiobackend import AudioBackend
from .consumers import QObjectABCMeta

class DataProducer(QObject, ABC, metaclass=QObjectABCMeta):
    """
    Abstract base class for data producers.
    
    All producers must implement the abstract methods and follow the
    established patterns for data extraction and lifecycle management.
    
    Signals:
        data_ready: Emitted when new data is available for streaming
        started: Emitted when producer starts
        stopped: Emitted when producer stops
        error_occurred: Emitted when an error occurs
    """
    
    data_ready = pyqtSignal(object)  # StreamingData
    started = pyqtSignal()
    stopped = pyqtSignal()
    error_occurred = pyqtSignal(str)
    
    def __init__(self, widget, widget_id: str, parent=None):
        super().__init__(parent)
        
        self.widget = widget
        self.widget_id = widget_id
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._is_active = False
        self._sequence_number = 0
        
    @abstractmethod
    def start(self) -> None:
        """Start data production."""
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """Stop data production."""
        pass
    
    @abstractmethod
    def extract_data(self) -> Any:
        """Extract data from the widget."""
        pass
    
    def get_metadata(self) -> StreamingMetadata:
        """
        Get metadata for the current data.
        
        Returns:
            StreamingMetadata instance
        """
        backend = AudioBackend()
        
        return StreamingMetadata(
            timestamp=time.time(),
            stream_time=backend.get_stream_time(),
            sample_rate=backend.SAMPLING_RATE if hasattr(backend, 'SAMPLING_RATE') else 48000,
            channels=backend.get_current_device_nchannels() if hasattr(backend, 'get_current_device_nchannels') else 1,
            data_type=self.get_data_type(),
            sequence_number=self._sequence_number,
            widget_id=self.widget_id,
            custom_metadata=self.get_custom_metadata()
        )
    
    @abstractmethod
    def get_data_type(self) -> DataType:
        """Get the data type this producer generates."""
        pass
    
    def get_custom_metadata(self) -> Dict[str, Any]:
        """
        Get custom metadata specific to this producer.
        
        Returns:
            Dictionary of custom metadata
        """
        return {}
    
    def _emit_data(self, data_payload: Any) -> None:
        """
        Emit data with proper metadata.
        
        Args:
            data_payload: The extracted data
        """
        try:
            streaming_data = create_streaming_data(
                data_type=self.get_data_type(),
                widget_id=self.widget_id,
                data_payload=data_payload,
                stream_time=AudioBackend().get_stream_time(),
                sample_rate=48000,  # Default, should be overridden
                channels=1,  # Default, should be overridden
                sequence_number=self._sequence_number,
                custom_metadata=self.get_custom_metadata()
            )
            
            self._sequence_number += 1
            self.data_ready.emit(streaming_data)
            
        except Exception as e:
            self.logger.error(f"Error emitting data: {e}")
            self.error_occurred.emit(str(e))


class PitchTrackerProducer(DataProducer):
    """
    Producer for pitch tracking data.
    
    Extracts fundamental frequency detection results from the pitch tracker
    widget, including confidence metrics and musical note information.
    """
    
    def __init__(self, pitch_widget, widget_id: str, parent=None):
        super().__init__(pitch_widget, widget_id, parent)
        
    def start(self) -> None:
        """Start producing pitch data."""
        if self._is_active:
            return
        
        self._is_active = True
        
        # Connect to the widget's data update signal
        # The pitch tracker updates its data in handle_new_data
        if hasattr(self.widget, 'tracker'):
            # Connect to the audio buffer's new data signal
            # This ensures we get notified whenever new pitch data is available
            self.widget.audiobuffer.new_data_available.connect(self._on_new_audio_data)
        
        self.started.emit()
        self.logger.info("PitchTrackerProducer started")
    
    def stop(self) -> None:
        """Stop producing pitch data."""
        if not self._is_active:
            return
        
        self._is_active = False
        
        # Disconnect from signals
        if hasattr(self.widget, 'tracker') and self.widget.audiobuffer:
            try:
                self.widget.audiobuffer.new_data_available.disconnect(self._on_new_audio_data)
            except TypeError:
                pass  # Signal was not connected
        
        self.stopped.emit()
        self.logger.info("PitchTrackerProducer stopped")
    
    def _on_new_audio_data(self, floatdata) -> None:
        """Handle new audio data and extract pitch information."""
        if not self._is_active:
            return
        
        try:
            # The pitch tracker processes data in handle_new_data
            # We extract the results after processing
            data = self.extract_data()
            if data is not None:
                self._emit_data(data)
        except Exception as e:
            self.logger.error(f"Error processing pitch data: {e}")
            self.error_occurred.emit(str(e))
    
    def extract_data(self) -> Optional[PitchData]:
        """Extract pitch data from the widget."""
        try:
            if not hasattr(self.widget, 'tracker'):
                return None
            
            tracker = self.widget.tracker
            
            # Get the latest pitch estimate
            latest_pitch = tracker.get_latest_estimate()
            
            # Calculate confidence based on signal strength and harmonic clarity
            # This is a simplified confidence metric
            confidence = 0.8 if latest_pitch and not np.isnan(latest_pitch) else 0.0
            
            # Convert frequency to note name
            note_name = None
            if latest_pitch and not np.isnan(latest_pitch):
                from ..pitch_tracker_data import frequency_to_note
                note_name = frequency_to_note(latest_pitch)
            
            # Estimate amplitude (simplified)
            amplitude_db = -20.0  # Default value, could be improved
            
            # Harmonic clarity (simplified)
            harmonic_clarity = confidence  # Simplified correlation
            
            return PitchData(
                frequency_hz=latest_pitch if latest_pitch and not np.isnan(latest_pitch) else None,
                confidence=confidence,
                note_name=note_name,
                amplitude_db=amplitude_db,
                harmonic_clarity=harmonic_clarity
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting pitch data: {e}")
            return None
    
    def get_data_type(self) -> DataType:
        """Get the data type this producer generates."""
        return DataType.PITCH_TRACKER
    
    def get_custom_metadata(self) -> Dict[str, Any]:
        """Get pitch tracker specific metadata."""
        metadata = {}
        
        if hasattr(self.widget, 'tracker'):
            metadata.update({
                'fft_size': getattr(self.widget.tracker, 'fft_size', 0),
                'overlap': getattr(self.widget.tracker, 'overlap', 0.0),
                'min_db': getattr(self.widget.tracker, 'min_db', -70.0),
                'min_freq': getattr(self.widget, 'min_freq', 80),
                'max_freq': getattr(self.widget, 'max_freq', 1000)
            })
        
        return metadata


class FFTSpectrumProducer(DataProducer):
    """
    Producer for FFT spectrum data.
    
    Extracts frequency domain analysis results from the spectrum widget,
    including magnitude spectrum, phase information, and peak detection.
    """
    
    def __init__(self, spectrum_widget, widget_id: str, parent=None):
        super().__init__(spectrum_widget, widget_id, parent)
        
    def start(self) -> None:
        """Start producing FFT spectrum data."""
        if self._is_active:
            return
        
        self._is_active = True
        
        # Connect to the widget's data processing
        if hasattr(self.widget, 'audiobuffer'):
            self.widget.audiobuffer.new_data_available.connect(self._on_new_audio_data)
        
        self.started.emit()
        self.logger.info("FFTSpectrumProducer started")
    
    def stop(self) -> None:
        """Stop producing FFT spectrum data."""
        if not self._is_active:
            return
        
        self._is_active = False
        
        if hasattr(self.widget, 'audiobuffer'):
            try:
                self.widget.audiobuffer.new_data_available.disconnect(self._on_new_audio_data)
            except TypeError:
                pass
        
        self.stopped.emit()
        self.logger.info("FFTSpectrumProducer stopped")
    
    def _on_new_audio_data(self, floatdata) -> None:
        """Handle new audio data and extract FFT information."""
        if not self._is_active:
            return
        
        try:
            data = self.extract_data()
            if data is not None:
                self._emit_data(data)
        except Exception as e:
            self.logger.error(f"Error processing FFT data: {e}")
            self.error_occurred.emit(str(e))
    
    def extract_data(self) -> Optional[FFTSpectrumData]:
        """Extract FFT spectrum data from the widget."""
        try:
            if not hasattr(self.widget, 'proc') or not hasattr(self.widget, 'freq'):
                return None
            
            proc = self.widget.proc
            frequencies = self.widget.freq.copy()
            
            # Get the latest spectrum data
            # This would need to be adapted based on how the spectrum widget stores its data
            if hasattr(self.widget, 'PlotZoneSpect') and hasattr(self.widget.PlotZoneSpect, '_spectrum_data'):
                spectrum_data = self.widget.PlotZoneSpect._spectrum_data
                
                # Extract magnitude data from the plot items
                if spectrum_data.plot_items and len(spectrum_data._plot_items) > 0:
                    curve = spectrum_data._plot_items[0]
                    if hasattr(curve, 'y_array'):
                        # Convert normalized plot coordinates back to dB values
                        magnitudes_db = curve.y_array().copy()
                        
                        # Get processing parameters
                        fft_size = getattr(proc, 'fft_size', 1024)
                        window_type = "hann"  # Default window type
                        overlap_factor = getattr(self.widget, 'overlap', 0.75)
                        weighting = self._get_weighting_string()
                        
                        # Find peak
                        if len(magnitudes_db) > 0:
                            peak_idx = np.argmax(magnitudes_db)
                            peak_frequency = frequencies[peak_idx] if peak_idx < len(frequencies) else 0.0
                            peak_magnitude = magnitudes_db[peak_idx]
                        else:
                            peak_frequency = 0.0
                            peak_magnitude = -np.inf
                        
                        return FFTSpectrumData(
                            frequencies=frequencies,
                            magnitudes_db=magnitudes_db,
                            phases=None,  # Phase data not typically stored in spectrum widget
                            fft_size=fft_size,
                            window_type=window_type,
                            overlap_factor=overlap_factor,
                            weighting=weighting,
                            peak_frequency=peak_frequency,
                            peak_magnitude=peak_magnitude
                        )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error extracting FFT data: {e}")
            return None
    
    def _get_weighting_string(self) -> str:
        """Get the current frequency weighting as a string."""
        weighting_map = {0: "none", 1: "A", 2: "B", 3: "C"}
        weighting_index = getattr(self.widget, 'weighting', 0)
        return weighting_map.get(weighting_index, "none")
    
    def get_data_type(self) -> DataType:
        """Get the data type this producer generates."""
        return DataType.FFT_SPECTRUM
    
    def get_custom_metadata(self) -> Dict[str, Any]:
        """Get FFT spectrum specific metadata."""
        metadata = {}
        
        if hasattr(self.widget, 'proc'):
            proc = self.widget.proc
            metadata.update({
                'fft_size': getattr(proc, 'fft_size', 0),
                'window_type': 'hann',
                'overlap_factor': getattr(self.widget, 'overlap', 0.0),
                'weighting': self._get_weighting_string(),
                'min_freq': getattr(self.widget, 'minfreq', 0),
                'max_freq': getattr(self.widget, 'maxfreq', 22000),
                'spec_min_db': getattr(self.widget, 'spec_min', -100),
                'spec_max_db': getattr(self.widget, 'spec_max', 0)
            })
        
        return metadata


class OctaveSpectrumProducer(DataProducer):
    """
    Producer for octave spectrum data.
    
    Extracts octave band analysis results from the octave spectrum widget,
    including energy measurements in standardized frequency bands.
    """
    
    def __init__(self, octave_widget, widget_id: str, parent=None):
        super().__init__(octave_widget, widget_id, parent)
        
    def start(self) -> None:
        """Start producing octave spectrum data."""
        if self._is_active:
            return
        
        self._is_active = True
        
        if hasattr(self.widget, 'audiobuffer'):
            self.widget.audiobuffer.new_data_available.connect(self._on_new_audio_data)
        
        self.started.emit()
        self.logger.info("OctaveSpectrumProducer started")
    
    def stop(self) -> None:
        """Stop producing octave spectrum data."""
        if not self._is_active:
            return
        
        self._is_active = False
        
        if hasattr(self.widget, 'audiobuffer'):
            try:
                self.widget.audiobuffer.new_data_available.disconnect(self._on_new_audio_data)
            except TypeError:
                pass
        
        self.stopped.emit()
        self.logger.info("OctaveSpectrumProducer stopped")
    
    def _on_new_audio_data(self, floatdata) -> None:
        """Handle new audio data and extract octave spectrum information."""
        if not self._is_active:
            return
        
        try:
            data = self.extract_data()
            if data is not None:
                self._emit_data(data)
        except Exception as e:
            self.logger.error(f"Error processing octave spectrum data: {e}")
            self.error_occurred.emit(str(e))
    
    def extract_data(self) -> Optional[OctaveSpectrumData]:
        """Extract octave spectrum data from the widget."""
        try:
            if not hasattr(self.widget, 'filters') or not hasattr(self.widget, 'dispbuffers'):
                return None
            
            filters = self.widget.filters
            
            # Get current band energies
            band_energies = np.array(self.widget.dispbuffers)
            
            # Convert to dB
            epsilon = 1e-30
            band_energies_db = 10.0 * np.log10(band_energies + epsilon)
            
            # Apply weighting
            weighting_index = getattr(self.widget, 'weighting', 0)
            if weighting_index == 1:  # A-weighting
                band_energies_db += filters.A
            elif weighting_index == 2:  # B-weighting
                band_energies_db += filters.B
            elif weighting_index == 3:  # C-weighting
                band_energies_db += filters.C
            
            # Calculate overall level
            overall_level = 10.0 * np.log10(np.sum(band_energies) + epsilon)
            
            return OctaveSpectrumData(
                center_frequencies=filters.fi.copy(),
                band_energies_db=band_energies_db,
                band_labels=getattr(filters, 'f_nominal', []),
                bands_per_octave=getattr(filters, 'bandsperoctave', 3),
                weighting=self._get_weighting_string(),
                response_time=getattr(self.widget, 'response_time', 1.0),
                overall_level=overall_level
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting octave spectrum data: {e}")
            return None
    
    def _get_weighting_string(self) -> str:
        """Get the current frequency weighting as a string."""
        weighting_map = {0: "none", 1: "A", 2: "B", 3: "C"}
        weighting_index = getattr(self.widget, 'weighting', 0)
        return weighting_map.get(weighting_index, "none")
    
    def get_data_type(self) -> DataType:
        """Get the data type this producer generates."""
        return DataType.OCTAVE_SPECTRUM
    
    def get_custom_metadata(self) -> Dict[str, Any]:
        """Get octave spectrum specific metadata."""
        metadata = {}
        
        if hasattr(self.widget, 'filters'):
            filters = self.widget.filters
            metadata.update({
                'bands_per_octave': getattr(filters, 'bandsperoctave', 3),
                'total_bands': getattr(filters, 'nbands', 0),
                'weighting': self._get_weighting_string(),
                'response_time': getattr(self.widget, 'response_time', 1.0),
                'spec_min_db': getattr(self.widget, 'spec_min', -80),
                'spec_max_db': getattr(self.widget, 'spec_max', -20)
            })
        
        return metadata


class LevelsProducer(DataProducer):
    """
    Producer for audio level data.
    
    Extracts peak and RMS level measurements from the levels widget,
    including ballistic characteristics and multi-channel support.
    """
    
    def __init__(self, levels_widget, widget_id: str, parent=None):
        super().__init__(levels_widget, widget_id, parent)
        
    def start(self) -> None:
        """Start producing levels data."""
        if self._is_active:
            return
        
        self._is_active = True
        
        if hasattr(self.widget, 'audiobuffer'):
            self.widget.audiobuffer.new_data_available.connect(self._on_new_audio_data)
        
        self.started.emit()
        self.logger.info("LevelsProducer started")
    
    def stop(self) -> None:
        """Stop producing levels data."""
        if not self._is_active:
            return
        
        self._is_active = False
        
        if hasattr(self.widget, 'audiobuffer'):
            try:
                self.widget.audiobuffer.new_data_available.disconnect(self._on_new_audio_data)
            except TypeError:
                pass
        
        self.stopped.emit()
        self.logger.info("LevelsProducer stopped")
    
    def _on_new_audio_data(self, floatdata) -> None:
        """Handle new audio data and extract levels information."""
        if not self._is_active:
            return
        
        try:
            data = self.extract_data()
            if data is not None:
                self._emit_data(data)
        except Exception as e:
            self.logger.error(f"Error processing levels data: {e}")
            self.error_occurred.emit(str(e))
    
    def extract_data(self) -> Optional[LevelsData]:
        """Extract levels data from the widget."""
        try:
            if not hasattr(self.widget, 'level_view_model'):
                return None
            
            view_model = self.widget.level_view_model
            
            # Extract level data
            peak_levels = [view_model.level_data.level_max]
            rms_levels = [view_model.level_data.level_rms]
            peak_hold_levels = [view_model.level_data_ballistic.peak_iec * 100 - 100]  # Convert IEC to dB
            
            channel_labels = ["Ch1"]
            
            # Add second channel if available
            if view_model.two_channels:
                peak_levels.append(view_model.level_data_2.level_max)
                rms_levels.append(view_model.level_data_2.level_rms)
                peak_hold_levels.append(view_model.level_data_ballistic_2.peak_iec * 100 - 100)
                channel_labels.append("Ch2")
            
            return LevelsData(
                peak_levels_db=np.array(peak_levels),
                rms_levels_db=np.array(rms_levels),
                peak_hold_levels_db=np.array(peak_hold_levels),
                channel_labels=channel_labels,
                integration_time=getattr(self.widget, 'response_time', 0.3),
                peak_hold_time=0.025  # Default peak hold time
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting levels data: {e}")
            return None
    
    def get_data_type(self) -> DataType:
        """Get the data type this producer generates."""
        return DataType.LEVELS
    
    def get_custom_metadata(self) -> Dict[str, Any]:
        """Get levels specific metadata."""
        return {
            'response_time': getattr(self.widget, 'response_time', 0.3),
            'two_channels': getattr(self.widget, 'two_channels', False)
        }


class DelayEstimatorProducer(DataProducer):
    """
    Producer for delay estimation data.
    
    Extracts cross-correlation delay estimation results from the delay
    estimator widget, including confidence metrics and polarity information.
    """
    
    def __init__(self, delay_widget, widget_id: str, parent=None):
        super().__init__(delay_widget, widget_id, parent)
        
    def start(self) -> None:
        """Start producing delay estimation data."""
        if self._is_active:
            return
        
        self._is_active = True
        
        self.started.emit()
        self.logger.info("DelayEstimatorProducer started")
    
    def stop(self) -> None:
        """Stop producing delay estimation data."""
        if not self._is_active:
            return
        
        self._is_active = False
        
        self.stopped.emit()
        self.logger.info("DelayEstimatorProducer stopped")
    
    def _process_data_from_widget(self, floatdata) -> None:
        """Handle new audio data and extract delay estimation information."""
        if not self._is_active:
            return
        
        try:
            data = self.extract_data()
            if data is not None:
                self._emit_data(data)
        except Exception as e:
            self.logger.error(f"Error processing delay estimation data: {e}")
            self.error_occurred.emit(str(e))
    
    def extract_data(self) -> Optional[DelayEstimatorData]:
        """Extract delay estimation data from the widget."""
        try:
            # Extract current delay estimation results
            delay_ms = getattr(self.widget, 'delay_ms', 0.0)
            distance_m = getattr(self.widget, 'distance_m', 0.0)
            correlation = getattr(self.widget, 'correlation', 0.0)
            xcorr_extremum = getattr(self.widget, 'Xcorr_extremum', 0.0)
            
            # Determine polarity
            if xcorr_extremum >= 0:
                polarity = "in_phase"
            elif xcorr_extremum < 0:
                polarity = "reversed"
            else:
                polarity = "unknown"
            
            # Convert correlation percentage to confidence
            confidence = correlation / 100.0 if correlation > 0 else 0.0
            
            # Calculate delay in samples
            sample_rate = AudioBackend().SAMPLING_RATE if hasattr(AudioBackend(), 'SAMPLING_RATE') else 48000
            delay_samples = int(delay_ms * sample_rate / 1000.0)
            
            return DelayEstimatorData(
                delay_ms=delay_ms,
                delay_samples=delay_samples,
                confidence=confidence,
                correlation_peak=abs(xcorr_extremum),
                polarity=polarity,
                distance_m=distance_m
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting delay estimation data: {e}")
            return None
    
    def get_data_type(self) -> DataType:
        """Get the data type this producer generates."""
        return DataType.DELAY_ESTIMATOR
    
    def get_custom_metadata(self) -> Dict[str, Any]:
        """Get delay estimator specific metadata."""
        return {
            'delay_range_s': getattr(self.widget, 'delayrange_s', 1.0),
            'two_channels': getattr(self.widget, 'two_channels', False),
            'subsampled_rate': getattr(self.widget, 'subsampled_sampling_rate', 12000)
        }