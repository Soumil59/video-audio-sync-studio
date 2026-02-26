#!/usr/bin/env python3
"""
Video-Audio Sync Editor (Windows Optimized Version)
Uses OpenCV and FFmpeg subprocess calls instead of MoviePy
"""

import sys
import os
import numpy as np
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Tuple
import logging
import subprocess
import tempfile

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QFileDialog, QMessageBox,
    QGroupBox, QFormLayout, QSpinBox, QDoubleSpinBox,
    QTextEdit, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

import librosa
import soundfile as sf
from scipy import signal
from scipy.io import wavfile

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Results from audio synchronization analysis"""
    offset_seconds: float
    confidence: float
    correlation_peak: float
    sample_rate: int
    method: str


class AudioSyncWorker(QThread):
    """Worker thread for audio synchronization processing"""
    
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(SyncResult)
    error = pyqtSignal(str)
    
    def __init__(self, video_path: str, audio_path: str, 
                 max_offset: int = 60):
        super().__init__()
        self.video_path = video_path
        self.audio_path = audio_path
        self.max_offset = max_offset
        
    def run(self):
        try:
            self.progress.emit(10, "Extracting audio from video...")
            video_audio = self.extract_video_audio_ffmpeg()
            
            self.progress.emit(30, "Loading external audio file...")
            external_audio = self.load_audio_file()
            
            self.progress.emit(50, "Performing cross-correlation analysis...")
            result = self.cross_correlation_sync(video_audio, external_audio)
            
            self.progress.emit(100, "Synchronization complete!")
            self.finished.emit(result)
            
        except Exception as e:
            logger.error(f"Error in sync worker: {str(e)}", exc_info=True)
            self.error.emit(str(e))
    
    def extract_video_audio_ffmpeg(self) -> Tuple[np.ndarray, int]:
        """Extract audio track from video using FFmpeg"""
        try:
            # Create temporary WAV file
            temp_audio = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            temp_audio_path = temp_audio.name
            temp_audio.close()
            
            # Use FFmpeg to extract audio
            cmd = [
                'ffmpeg',
                '-i', self.video_path,
                '-vn',  # No video
                '-acodec', 'pcm_s16le',  # PCM 16-bit
                '-ar', '22050',  # Sample rate
                '-ac', '1',  # Mono
                '-y',  # Overwrite
                temp_audio_path
            ]
            
            logger.info(f"Running FFmpeg: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.returncode != 0:
                raise Exception(f"FFmpeg failed: {result.stderr}")
            
            # Load the extracted audio
            sample_rate, audio = wavfile.read(temp_audio_path)
            
            # Clean up temp file
            try:
                os.unlink(temp_audio_path)
            except:
                pass
            
            # Convert to float and normalize
            audio = audio.astype(np.float32) / 32768.0
            
            return audio, sample_rate
            
        except FileNotFoundError:
            raise Exception("FFmpeg not found. Please install FFmpeg and add it to your PATH.")
        except Exception as e:
            raise Exception(f"Failed to extract video audio: {str(e)}")
    
    def load_audio_file(self) -> Tuple[np.ndarray, int]:
        """Load external audio file"""
        try:
            # Use librosa for robust audio loading
            audio, sr = librosa.load(self.audio_path, sr=22050, mono=True)
            return audio, sr
            
        except Exception as e:
            raise Exception(f"Failed to load audio file: {str(e)}")
    
    def cross_correlation_sync(self, video_audio: Tuple[np.ndarray, int],
                               external_audio: Tuple[np.ndarray, int]) -> SyncResult:
        """
        Find sync point using cross-correlation
        """
        vid_audio, vid_sr = video_audio
        ext_audio, ext_sr = external_audio
        
        # Normalize audio
        vid_audio = vid_audio / (np.max(np.abs(vid_audio)) + 1e-8)
        ext_audio = ext_audio / (np.max(np.abs(ext_audio)) + 1e-8)
        
        # Limit search range
        max_offset_samples = int(self.max_offset * vid_sr)
        
        # Use shorter signal as template
        if len(vid_audio) < len(ext_audio):
            template = vid_audio[:min(len(vid_audio), 30 * vid_sr)]
            search_signal = ext_audio[:min(len(ext_audio), 
                                          len(template) + max_offset_samples)]
            reverse = False
        else:
            template = ext_audio[:min(len(ext_audio), 30 * ext_sr)]
            search_signal = vid_audio[:min(len(vid_audio), 
                                          len(template) + max_offset_samples)]
            reverse = True
        
        # Compute cross-correlation
        correlation = signal.correlate(search_signal, template, mode='valid')
        
        # Find peak
        peak_index = np.argmax(correlation)
        peak_value = correlation[peak_index]
        
        # Calculate confidence
        confidence = peak_value / (np.sqrt(np.sum(template**2) * 
                                           np.sum(search_signal**2)) + 1e-8)
        
        # Convert to seconds
        if reverse:
            offset_seconds = peak_index / vid_sr
        else:
            offset_seconds = -peak_index / ext_sr
        
        return SyncResult(
            offset_seconds=float(offset_seconds),
            confidence=float(min(confidence, 1.0)),
            correlation_peak=float(peak_value),
            sample_rate=vid_sr,
            method='cross_correlation'
        )


class VideoProcessWorker(QThread):
    """Worker thread for video processing using FFmpeg"""
    
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(self, video_path: str, audio_path: str, 
                 output_path: str, offset: float, mute_original: bool = True):
        super().__init__()
        self.video_path = video_path
        self.audio_path = audio_path
        self.output_path = output_path
        self.offset = offset
        self.mute_original = mute_original
    
    def run(self):
        try:
            self.progress.emit(10, "Preparing files...")
            
            # Create temporary audio file with offset applied
            temp_audio = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            temp_audio_path = temp_audio.name
            temp_audio.close()
            
            # Apply offset to audio
            self.progress.emit(30, "Applying audio offset...")
            self.apply_offset_to_audio(temp_audio_path)
            
            # Combine video and audio using FFmpeg
            self.progress.emit(60, "Merging video and audio (this may take a while)...")
            
            if self.mute_original:
                # Replace original audio completely with new audio
                cmd = [
                    'ffmpeg',
                    '-i', self.video_path,
                    '-i', temp_audio_path,
                    '-c:v', 'copy',  # Copy video stream (fast)
                    '-c:a', 'aac',   # Encode audio as AAC
                    '-b:a', '192k',  # Audio bitrate
                    '-map', '0:v:0', # Video from first input
                    '-map', '1:a:0', # Audio from second input (new audio only)
                    '-shortest',     # Match shortest stream
                    '-y',            # Overwrite output
                    self.output_path
                ]
            else:
                # Mix original video audio with new audio
                cmd = [
                    'ffmpeg',
                    '-i', self.video_path,
                    '-i', temp_audio_path,
                    '-filter_complex', '[0:a]volume=0.3[original];[1:a]volume=1.0[new];[original][new]amix=inputs=2:duration=shortest',
                    '-c:v', 'copy',  # Copy video stream (fast)
                    '-c:a', 'aac',   # Encode audio as AAC
                    '-b:a', '192k',  # Audio bitrate
                    '-map', '0:v:0', # Video from first input
                    '-y',            # Overwrite output
                    self.output_path
                ]
            
            logger.info(f"Running FFmpeg: {' '.join(cmd)}")
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                universal_newlines=True
            )
            
            # Monitor progress
            while True:
                output = process.stderr.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    # Parse FFmpeg progress if needed
                    self.progress.emit(80, "Encoding video...")
            
            return_code = process.poll()
            
            # Clean up temp file
            try:
                os.unlink(temp_audio_path)
            except:
                pass
            
            if return_code != 0:
                stderr = process.stderr.read()
                raise Exception(f"FFmpeg encoding failed: {stderr}")
            
            self.progress.emit(100, "Export complete!")
            self.finished.emit(self.output_path)
            
        except Exception as e:
            logger.error(f"Error in video processing: {str(e)}", exc_info=True)
            self.error.emit(str(e))
    
    def apply_offset_to_audio(self, output_path: str):
        """Apply time offset to audio file"""
        try:
            # Load audio
            audio, sr = librosa.load(self.audio_path, sr=22050, mono=True)
            
            if self.offset > 0:
                # Add silence at beginning
                silence_samples = int(self.offset * sr)
                silence = np.zeros(silence_samples, dtype=np.float32)
                audio = np.concatenate([silence, audio])
            elif self.offset < 0:
                # Trim beginning
                trim_samples = int(abs(self.offset) * sr)
                audio = audio[trim_samples:]
            
            # Save as WAV
            sf.write(output_path, audio, sr)
            
        except Exception as e:
            raise Exception(f"Failed to apply offset: {str(e)}")


class VideoAudioSyncApp(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.video_path = None
        self.audio_path = None
        self.sync_result = None
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("Video-Audio Sync Editor (Windows)")
        self.setGeometry(100, 100, 900, 700)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Title
        title = QLabel("Video-Audio Synchronization Tool")
        title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)
        
        subtitle = QLabel("Windows Optimized Version")
        subtitle.setFont(QFont("Arial", 10))
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #666;")
        main_layout.addWidget(subtitle)
        
        # File selection group
        file_group = QGroupBox("1. Select Files")
        file_layout = QFormLayout()
        
        # Video file
        video_layout = QHBoxLayout()
        self.video_label = QLabel("No video selected")
        self.video_btn = QPushButton("Browse Video")
        self.video_btn.clicked.connect(self.select_video)
        video_layout.addWidget(self.video_label, 1)
        video_layout.addWidget(self.video_btn)
        file_layout.addRow("Video File:", video_layout)
        
        # Audio file
        audio_layout = QHBoxLayout()
        self.audio_label = QLabel("No audio selected")
        self.audio_btn = QPushButton("Browse Audio")
        self.audio_btn.clicked.connect(self.select_audio)
        audio_layout.addWidget(self.audio_label, 1)
        audio_layout.addWidget(self.audio_btn)
        file_layout.addRow("Audio File:", audio_layout)
        
        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)
        
        # Sync settings group
        sync_group = QGroupBox("2. Synchronization Settings")
        sync_layout = QFormLayout()
        
        self.max_offset_spin = QSpinBox()
        self.max_offset_spin.setRange(10, 300)
        self.max_offset_spin.setValue(60)
        self.max_offset_spin.setSuffix(" seconds")
        sync_layout.addRow("Max Search Range:", self.max_offset_spin)
        
        # Audio mixing option
        self.mute_original = QCheckBox("Mute original video audio")
        self.mute_original.setChecked(True)
        self.mute_original.setToolTip("When checked, only the new audio will be heard. When unchecked, both audios will be mixed together.")
        sync_layout.addRow("", self.mute_original)
        
        # Sync button
        self.sync_btn = QPushButton("Analyze & Find Sync Point")
        self.sync_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.sync_btn.clicked.connect(self.analyze_sync)
        self.sync_btn.setEnabled(False)
        sync_layout.addRow(self.sync_btn)
        
        sync_group.setLayout(sync_layout)
        main_layout.addWidget(sync_group)
        
        # Results group
        results_group = QGroupBox("3. Synchronization Results")
        results_layout = QVBoxLayout()
        
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setMaximumHeight(150)
        self.results_text.setPlainText("No analysis performed yet.")
        results_layout.addWidget(self.results_text)
        
        # Manual adjustment
        adjust_layout = QHBoxLayout()
        adjust_layout.addWidget(QLabel("Manual Offset Adjustment:"))
        self.offset_adjust = QDoubleSpinBox()
        self.offset_adjust.setRange(-300, 300)
        self.offset_adjust.setValue(0.0)
        self.offset_adjust.setSuffix(" seconds")
        self.offset_adjust.setSingleStep(0.1)
        self.offset_adjust.setDecimals(3)
        adjust_layout.addWidget(self.offset_adjust)
        results_layout.addLayout(adjust_layout)
        
        results_group.setLayout(results_layout)
        main_layout.addWidget(results_group)
        
        # Export group
        export_group = QGroupBox("4. Export Video")
        export_layout = QVBoxLayout()
        
        self.export_btn = QPushButton("Export Synced Video")
        self.export_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.export_btn.clicked.connect(self.export_video)
        self.export_btn.setEnabled(False)
        export_layout.addWidget(self.export_btn)
        
        export_group.setLayout(export_layout)
        main_layout.addWidget(export_group)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.status_label)
        
        main_layout.addStretch()
        
    def select_video(self):
        """Open file dialog to select video file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Video File",
            "",
            "Video Files (*.mp4 *.avi *.mov *.mkv *.flv *.wmv);;All Files (*)"
        )
        
        if file_path:
            self.video_path = file_path
            self.video_label.setText(Path(file_path).name)
            self.check_ready_to_sync()
    
    def select_audio(self):
        """Open file dialog to select audio file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Audio File",
            "",
            "Audio Files (*.mp3 *.wav *.aac *.flac *.ogg *.m4a);;All Files (*)"
        )
        
        if file_path:
            self.audio_path = file_path
            self.audio_label.setText(Path(file_path).name)
            self.check_ready_to_sync()
    
    def check_ready_to_sync(self):
        """Enable sync button if both files are selected"""
        if self.video_path and self.audio_path:
            self.sync_btn.setEnabled(True)
        else:
            self.sync_btn.setEnabled(False)
    
    def analyze_sync(self):
        """Start synchronization analysis"""
        self.sync_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # Create worker thread
        self.sync_worker = AudioSyncWorker(
            self.video_path,
            self.audio_path,
            max_offset=self.max_offset_spin.value()
        )
        
        self.sync_worker.progress.connect(self.update_progress)
        self.sync_worker.finished.connect(self.sync_complete)
        self.sync_worker.error.connect(self.sync_error)
        
        self.sync_worker.start()
    
    def update_progress(self, value: int, message: str):
        """Update progress bar and status"""
        self.progress_bar.setValue(value)
        self.status_label.setText(message)
    
    def sync_complete(self, result: SyncResult):
        """Handle completion of sync analysis"""
        self.sync_result = result
        self.sync_btn.setEnabled(True)
        self.export_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        # Update offset adjustment
        self.offset_adjust.setValue(result.offset_seconds)
        
        # Display results
        results_text = f"""
Synchronization Analysis Complete!

Method: Cross-Correlation
Detected Offset: {result.offset_seconds:.3f} seconds
Confidence Score: {result.confidence:.2%}
Correlation Peak: {result.correlation_peak:.2f}

Interpretation:
"""
        
        if result.offset_seconds > 0:
            results_text += f"• The external audio should start {result.offset_seconds:.3f} seconds INTO the video.\n"
        elif result.offset_seconds < 0:
            results_text += f"• The external audio starts {abs(result.offset_seconds):.3f} seconds BEFORE the video.\n"
        else:
            results_text += "• The audio and video are already aligned at the start.\n"
        
        if result.confidence > 0.7:
            results_text += "• High confidence - sync point is very reliable."
        elif result.confidence > 0.4:
            results_text += "• Medium confidence - sync point is fairly reliable."
        else:
            results_text += "• Low confidence - you may want to adjust manually."
        
        self.results_text.setPlainText(results_text)
        self.status_label.setText("Ready to export!")
        
        QMessageBox.information(
            self,
            "Sync Complete",
            f"Sync point found at {result.offset_seconds:.3f} seconds\n"
            f"Confidence: {result.confidence:.2%}"
        )
    
    def sync_error(self, error_msg: str):
        """Handle sync analysis error"""
        self.sync_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Error occurred")
        
        QMessageBox.critical(
            self,
            "Synchronization Error",
            f"An error occurred during synchronization:\n\n{error_msg}"
        )
    
    def export_video(self):
        """Export video with synced audio"""
        # Get output path
        default_name = Path(self.video_path).stem + "_synced.mp4"
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Synced Video",
            default_name,
            "MP4 Video (*.mp4);;All Files (*)"
        )
        
        if not output_path:
            return
        
        # Get final offset
        final_offset = self.offset_adjust.value()
        mute_original = self.mute_original.isChecked()
        
        self.export_btn.setEnabled(False)
        self.sync_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # Create worker thread
        self.process_worker = VideoProcessWorker(
            self.video_path,
            self.audio_path,
            output_path,
            final_offset,
            mute_original
        )
        
        self.process_worker.progress.connect(self.update_progress)
        self.process_worker.finished.connect(self.export_complete)
        self.process_worker.error.connect(self.export_error)
        
        self.process_worker.start()
    
    def export_complete(self, output_path: str):
        """Handle completion of video export"""
        self.export_btn.setEnabled(True)
        self.sync_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Export complete!")
        
        QMessageBox.information(
            self,
            "Export Complete",
            f"Video successfully exported to:\n{output_path}"
        )
    
    def export_error(self, error_msg: str):
        """Handle export error"""
        self.export_btn.setEnabled(True)
        self.sync_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Export failed")
        
        QMessageBox.critical(
            self,
            "Export Error",
            f"An error occurred during export:\n\n{error_msg}"
        )


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = VideoAudioSyncApp()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
