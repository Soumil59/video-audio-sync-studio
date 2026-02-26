#!/usr/bin/env python3
"""
Video-Audio Sync Editor - Professional Edition
Sophisticated UI with advanced export settings
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
    QTextEdit, QCheckBox, QComboBox, QFrame, QGraphicsDropShadowEffect,
    QScrollArea
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPropertyAnimation, QEasingCurve, QTimer
from PyQt6.QtGui import QFont, QPalette, QColor, QLinearGradient, QPainter, QIcon

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


# Modern color palette
COLORS = {
    'bg_dark': '#0A0E27',
    'bg_medium': '#161B33',
    'bg_light': '#1E2544',
    'accent_primary': '#00D9FF',
    'accent_secondary': '#7C3AED',
    'accent_success': '#10B981',
    'text_primary': '#F8FAFC',
    'text_secondary': '#94A3B8',
    'border': '#2D3656',
    'hover': '#252B4A'
}


@dataclass
class SyncResult:
    """Results from audio synchronization analysis"""
    offset_seconds: float
    confidence: float
    correlation_peak: float
    sample_rate: int
    method: str


@dataclass
class ExportSettings:
    """Export quality settings"""
    format: str = 'mp4'
    video_codec: str = 'libx264'
    audio_codec: str = 'aac'
    resolution: str = 'original'
    video_bitrate: str = '8M'
    audio_bitrate: str = '192k'
    preset: str = 'medium'
    crf: int = 23


class AudioSyncWorker(QThread):
    """Worker thread for audio synchronization processing"""
    
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(SyncResult)
    error = pyqtSignal(str)
    
    def __init__(self, video_path: str, audio_path: str, max_offset: int = 60):
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
            temp_audio = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            temp_audio_path = temp_audio.name
            temp_audio.close()
            
            cmd = [
                'ffmpeg', '-i', self.video_path, '-vn',
                '-acodec', 'pcm_s16le', '-ar', '22050', '-ac', '1',
                '-y', temp_audio_path
            ]
            
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            if result.returncode != 0:
                raise Exception(f"FFmpeg failed: {result.stderr}")
            
            sample_rate, audio = wavfile.read(temp_audio_path)
            
            try:
                os.unlink(temp_audio_path)
            except:
                pass
            
            audio = audio.astype(np.float32) / 32768.0
            return audio, sample_rate
            
        except FileNotFoundError:
            raise Exception("FFmpeg not found. Please install FFmpeg.")
        except Exception as e:
            raise Exception(f"Failed to extract video audio: {str(e)}")
    
    def load_audio_file(self) -> Tuple[np.ndarray, int]:
        """Load external audio file"""
        try:
            audio, sr = librosa.load(self.audio_path, sr=22050, mono=True)
            return audio, sr
        except Exception as e:
            raise Exception(f"Failed to load audio file: {str(e)}")
    
    def cross_correlation_sync(self, video_audio: Tuple[np.ndarray, int],
                               external_audio: Tuple[np.ndarray, int]) -> SyncResult:
        """Find sync point using cross-correlation"""
        vid_audio, vid_sr = video_audio
        ext_audio, ext_sr = external_audio
        
        vid_audio = vid_audio / (np.max(np.abs(vid_audio)) + 1e-8)
        ext_audio = ext_audio / (np.max(np.abs(ext_audio)) + 1e-8)
        
        max_offset_samples = int(self.max_offset * vid_sr)
        
        if len(vid_audio) < len(ext_audio):
            template = vid_audio[:min(len(vid_audio), 30 * vid_sr)]
            search_signal = ext_audio[:min(len(ext_audio), len(template) + max_offset_samples)]
            reverse = False
        else:
            template = ext_audio[:min(len(ext_audio), 30 * ext_sr)]
            search_signal = vid_audio[:min(len(vid_audio), len(template) + max_offset_samples)]
            reverse = True
        
        correlation = signal.correlate(search_signal, template, mode='valid')
        peak_index = np.argmax(correlation)
        peak_value = correlation[peak_index]
        
        confidence = peak_value / (np.sqrt(np.sum(template**2) * np.sum(search_signal**2)) + 1e-8)
        
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
    
    def __init__(self, video_path: str, audio_path: str, output_path: str, 
                 offset: float, mute_original: bool, export_settings: ExportSettings):
        super().__init__()
        self.video_path = video_path
        self.audio_path = audio_path
        self.output_path = output_path
        self.offset = offset
        self.mute_original = mute_original
        self.export_settings = export_settings
    
    def run(self):
        try:
            self.progress.emit(10, "Preparing files...")
            
            temp_audio = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            temp_audio_path = temp_audio.name
            temp_audio.close()
            
            self.progress.emit(30, "Applying audio offset...")
            self.apply_offset_to_audio(temp_audio_path)
            
            self.progress.emit(50, "Encoding video (this may take a while)...")
            
            # Build FFmpeg command based on settings
            cmd = self.build_ffmpeg_command(temp_audio_path)
            
            logger.info(f"Running FFmpeg: {' '.join(cmd)}")
            
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, universal_newlines=True
            )
            
            while True:
                output = process.stderr.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    self.progress.emit(75, "Encoding video...")
            
            return_code = process.poll()
            
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
    
    def build_ffmpeg_command(self, temp_audio_path: str) -> list:
        """Build FFmpeg command based on export settings"""
        s = self.export_settings
        cmd = ['ffmpeg', '-i', self.video_path, '-i', temp_audio_path]
        
        # Video filters (resolution scaling)
        video_filters = []
        if s.resolution != 'original':
            video_filters.append(f'scale={s.resolution}')
        
        if self.mute_original:
            # Replace audio
            if video_filters:
                cmd.extend(['-vf', ','.join(video_filters)])
            else:
                cmd.extend(['-c:v', s.video_codec])
            
            cmd.extend([
                '-c:a', s.audio_codec,
                '-b:v', s.video_bitrate,
                '-b:a', s.audio_bitrate,
                '-crf', str(s.crf),
                '-preset', s.preset,
                '-map', '0:v:0',
                '-map', '1:a:0',
                '-shortest'
            ])
        else:
            # Mix audio
            audio_filter = '[0:a]volume=0.3[original];[1:a]volume=1.0[new];[original][new]amix=inputs=2:duration=shortest'
            
            if video_filters:
                cmd.extend(['-vf', ','.join(video_filters)])
            
            cmd.extend([
                '-filter_complex', audio_filter,
                '-c:v', s.video_codec,
                '-c:a', s.audio_codec,
                '-b:v', s.video_bitrate,
                '-b:a', s.audio_bitrate,
                '-crf', str(s.crf),
                '-preset', s.preset,
                '-map', '0:v:0'
            ])
        
        cmd.extend(['-y', self.output_path])
        return cmd
    
    def apply_offset_to_audio(self, output_path: str):
        """Apply time offset to audio file"""
        try:
            audio, sr = librosa.load(self.audio_path, sr=22050, mono=True)
            
            if self.offset > 0:
                silence_samples = int(self.offset * sr)
                silence = np.zeros(silence_samples, dtype=np.float32)
                audio = np.concatenate([silence, audio])
            elif self.offset < 0:
                trim_samples = int(abs(self.offset) * sr)
                audio = audio[trim_samples:]
            
            sf.write(output_path, audio, sr)
        except Exception as e:
            raise Exception(f"Failed to apply offset: {str(e)}")


class ModernButton(QPushButton):
    """Custom styled button with hover effects"""
    
    def __init__(self, text, primary=False):
        super().__init__(text)
        self.primary = primary
        self.setup_style()
    
    def setup_style(self):
        if self.primary:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {COLORS['accent_primary']}, stop:1 {COLORS['accent_secondary']});
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 12px 24px;
                    font-size: 14px;
                    font-weight: 600;
                    letter-spacing: 0.5px;
                }}
                QPushButton:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #00E5FF, stop:1 #8B5CF6);
                }}
                QPushButton:pressed {{
                    padding: 13px 24px 11px 24px;
                }}
                QPushButton:disabled {{
                    background: {COLORS['bg_light']};
                    color: {COLORS['text_secondary']};
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {COLORS['bg_light']};
                    color: {COLORS['text_primary']};
                    border: 2px solid {COLORS['border']};
                    border-radius: 8px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background: {COLORS['hover']};
                    border-color: {COLORS['accent_primary']};
                }}
                QPushButton:pressed {{
                    padding: 11px 20px 9px 20px;
                }}
            """)


class ModernProgressBar(QProgressBar):
    """Custom styled progress bar with gradient"""
    
    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                border-radius: 6px;
                background: {COLORS['bg_light']};
                text-align: center;
                color: {COLORS['text_primary']};
                font-weight: 600;
                height: 12px;
            }}
            QProgressBar::chunk {{
                border-radius: 6px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {COLORS['accent_primary']}, stop:1 {COLORS['accent_secondary']});
            }}
        """)


class VideoAudioSyncApp(QMainWindow):
    """Main application window with modern UI"""
    
    def __init__(self):
        super().__init__()
        self.video_path = None
        self.audio_path = None
        self.sync_result = None
        self.export_settings = ExportSettings()
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("Video-Audio Sync Studio")
        self.setGeometry(100, 100, 1100, 800)
        
        # Set dark theme palette
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(COLORS['bg_dark']))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(COLORS['text_primary']))
        palette.setColor(QPalette.ColorRole.Base, QColor(COLORS['bg_medium']))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(COLORS['bg_light']))
        palette.setColor(QPalette.ColorRole.Text, QColor(COLORS['text_primary']))
        palette.setColor(QPalette.ColorRole.Button, QColor(COLORS['bg_light']))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLORS['text_primary']))
        self.setPalette(palette)
        
        # Main scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background: {COLORS['bg_dark']};
                border: none;
            }}
            QScrollBar:vertical {{
                background: {COLORS['bg_medium']};
                width: 10px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: {COLORS['accent_primary']};
                border-radius: 5px;
            }}
        """)
        
        # Central widget
        central_widget = QWidget()
        scroll.setWidget(central_widget)
        self.setCentralWidget(scroll)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(40, 30, 40, 30)
        
        # Header with gradient
        header_widget = QWidget()
        header_widget.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {COLORS['accent_primary']}, stop:1 {COLORS['accent_secondary']});
                border-radius: 12px;
                padding: 30px;
            }}
        """)
        header_layout = QVBoxLayout(header_widget)
        
        title = QLabel("🎬 Video-Audio Sync Studio")
        title.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        title.setStyleSheet("color: white;")
        header_layout.addWidget(title)
        
        subtitle = QLabel("Professional audio synchronization with AI-powered detection")
        subtitle.setFont(QFont("Segoe UI", 12))
        subtitle.setStyleSheet("color: rgba(255, 255, 255, 0.9);")
        header_layout.addWidget(subtitle)
        
        main_layout.addWidget(header_widget)
        
        # File selection section
        file_section = self.create_section("1️⃣ Select Files", self.create_file_selection())
        main_layout.addWidget(file_section)
        
        # Sync settings section
        sync_section = self.create_section("2️⃣ Analysis Settings", self.create_sync_settings())
        main_layout.addWidget(sync_section)
        
        # Results section
        results_section = self.create_section("3️⃣ Synchronization Results", self.create_results_display())
        main_layout.addWidget(results_section)
        
        # Export settings section
        export_section = self.create_section("4️⃣ Export Settings", self.create_export_settings())
        main_layout.addWidget(export_section)
        
        # Progress section
        self.progress_widget = QWidget()
        progress_layout = QVBoxLayout(self.progress_widget)
        self.progress_bar = ModernProgressBar()
        self.progress_bar.setVisible(False)
        progress_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setFont(QFont("Segoe UI", 11))
        self.status_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        progress_layout.addWidget(self.status_label)
        
        main_layout.addWidget(self.progress_widget)
        main_layout.addStretch()
    
    def create_section(self, title: str, content_widget: QWidget) -> QWidget:
        """Create a styled section container"""
        section = QWidget()
        section.setStyleSheet(f"""
            QWidget {{
                background: {COLORS['bg_medium']};
                border-radius: 12px;
                border: 1px solid {COLORS['border']};
            }}
        """)
        
        layout = QVBoxLayout(section)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(15)
        
        section_title = QLabel(title)
        section_title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        section_title.setStyleSheet(f"color: {COLORS['text_primary']};")
        layout.addWidget(section_title)
        
        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        layout.addWidget(divider)
        
        layout.addWidget(content_widget)
        
        return section
    
    def create_file_selection(self) -> QWidget:
        """Create file selection UI"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)
        
        # Video file
        video_container = QWidget()
        video_layout = QHBoxLayout(video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        
        video_label_container = QWidget()
        video_label_container.setStyleSheet(f"""
            QWidget {{
                background: {COLORS['bg_light']};
                border-radius: 6px;
                padding: 10px;
            }}
        """)
        video_label_layout = QVBoxLayout(video_label_container)
        video_label_layout.setContentsMargins(10, 5, 10, 5)
        
        video_title = QLabel("📹 Video File")
        video_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        video_title.setStyleSheet(f"color: {COLORS['text_secondary']};")
        video_label_layout.addWidget(video_title)
        
        self.video_label = QLabel("No file selected")
        self.video_label.setFont(QFont("Segoe UI", 11))
        self.video_label.setStyleSheet(f"color: {COLORS['text_primary']};")
        video_label_layout.addWidget(self.video_label)
        
        video_layout.addWidget(video_label_container, 1)
        
        self.video_btn = ModernButton("Browse", False)
        self.video_btn.clicked.connect(self.select_video)
        video_layout.addWidget(self.video_btn)
        
        layout.addWidget(video_container)
        
        # Audio file
        audio_container = QWidget()
        audio_layout = QHBoxLayout(audio_container)
        audio_layout.setContentsMargins(0, 0, 0, 0)
        
        audio_label_container = QWidget()
        audio_label_container.setStyleSheet(f"""
            QWidget {{
                background: {COLORS['bg_light']};
                border-radius: 6px;
                padding: 10px;
            }}
        """)
        audio_label_layout = QVBoxLayout(audio_label_container)
        audio_label_layout.setContentsMargins(10, 5, 10, 5)
        
        audio_title = QLabel("🎵 Audio File")
        audio_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        audio_title.setStyleSheet(f"color: {COLORS['text_secondary']};")
        audio_label_layout.addWidget(audio_title)
        
        self.audio_label = QLabel("No file selected")
        self.audio_label.setFont(QFont("Segoe UI", 11))
        self.audio_label.setStyleSheet(f"color: {COLORS['text_primary']};")
        audio_label_layout.addWidget(self.audio_label)
        
        audio_layout.addWidget(audio_label_container, 1)
        
        self.audio_btn = ModernButton("Browse", False)
        self.audio_btn.clicked.connect(self.select_audio)
        audio_layout.addWidget(self.audio_btn)
        
        layout.addWidget(audio_container)
        
        return widget
    
    def create_sync_settings(self) -> QWidget:
        """Create sync settings UI"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(15)
        
        # Max offset
        self.max_offset_spin = QSpinBox()
        self.max_offset_spin.setRange(10, 300)
        self.max_offset_spin.setValue(60)
        self.max_offset_spin.setSuffix(" seconds")
        self.max_offset_spin.setStyleSheet(f"""
            QSpinBox {{
                background: {COLORS['bg_light']};
                color: {COLORS['text_primary']};
                border: 2px solid {COLORS['border']};
                border-radius: 6px;
                padding: 8px;
                font-size: 13px;
            }}
            QSpinBox:focus {{
                border-color: {COLORS['accent_primary']};
            }}
        """)
        
        offset_label = QLabel("Search Range:")
        offset_label.setFont(QFont("Segoe UI", 11))
        offset_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        form_layout.addRow(offset_label, self.max_offset_spin)
        
        # Mute original
        self.mute_original = QCheckBox("Mute original video audio")
        self.mute_original.setChecked(True)
        self.mute_original.setStyleSheet(f"""
            QCheckBox {{
                color: {COLORS['text_primary']};
                font-size: 12px;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 20px;
                height: 20px;
                border-radius: 4px;
                border: 2px solid {COLORS['border']};
                background: {COLORS['bg_light']};
            }}
            QCheckBox::indicator:checked {{
                background: {COLORS['accent_primary']};
                border-color: {COLORS['accent_primary']};
            }}
        """)
        form_layout.addRow("", self.mute_original)
        
        layout.addLayout(form_layout)
        
        # Analyze button
        self.sync_btn = ModernButton("🔍 Analyze & Find Sync Point", True)
        self.sync_btn.clicked.connect(self.analyze_sync)
        self.sync_btn.setEnabled(False)
        layout.addWidget(self.sync_btn)
        
        return widget
    
    def create_results_display(self) -> QWidget:
        """Create results display UI"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setMaximumHeight(150)
        self.results_text.setStyleSheet(f"""
            QTextEdit {{
                background: {COLORS['bg_light']};
                color: {COLORS['text_primary']};
                border: 2px solid {COLORS['border']};
                border-radius: 8px;
                padding: 15px;
                font-family: 'Consolas', monospace;
                font-size: 12px;
                line-height: 1.6;
            }}
        """)
        self.results_text.setPlainText("⏳ No analysis performed yet. Select files and click Analyze.")
        layout.addWidget(self.results_text)
        
        # Manual adjustment
        adjust_widget = QWidget()
        adjust_layout = QHBoxLayout(adjust_widget)
        adjust_layout.setContentsMargins(0, 10, 0, 0)
        
        adjust_label = QLabel("Manual Offset:")
        adjust_label.setFont(QFont("Segoe UI", 11))
        adjust_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        adjust_layout.addWidget(adjust_label)
        
        self.offset_adjust = QDoubleSpinBox()
        self.offset_adjust.setRange(-300, 300)
        self.offset_adjust.setValue(0.0)
        self.offset_adjust.setSuffix(" seconds")
        self.offset_adjust.setSingleStep(0.1)
        self.offset_adjust.setDecimals(3)
        self.offset_adjust.setStyleSheet(f"""
            QDoubleSpinBox {{
                background: {COLORS['bg_light']};
                color: {COLORS['text_primary']};
                border: 2px solid {COLORS['border']};
                border-radius: 6px;
                padding: 8px;
                font-size: 13px;
                min-width: 150px;
            }}
            QDoubleSpinBox:focus {{
                border-color: {COLORS['accent_primary']};
            }}
        """)
        adjust_layout.addWidget(self.offset_adjust)
        adjust_layout.addStretch()
        
        layout.addWidget(adjust_widget)
        
        return widget
    
    def create_export_settings(self) -> QWidget:
        """Create export settings UI"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        
        label_style = f"color: {COLORS['text_secondary']}; font-size: 11px;"
        combo_style = f"""
            QComboBox {{
                background: {COLORS['bg_light']};
                color: {COLORS['text_primary']};
                border: 2px solid {COLORS['border']};
                border-radius: 6px;
                padding: 8px;
                font-size: 13px;
                min-width: 150px;
            }}
            QComboBox:focus {{
                border-color: {COLORS['accent_primary']};
            }}
            QComboBox::drop-down {{
                border: none;
                padding-right: 10px;
            }}
            QComboBox QAbstractItemView {{
                background: {COLORS['bg_light']};
                color: {COLORS['text_primary']};
                selection-background-color: {COLORS['accent_primary']};
                border: 1px solid {COLORS['border']};
            }}
        """
        
        # Format
        format_label = QLabel("Format:")
        format_label.setStyleSheet(label_style)
        self.format_combo = QComboBox()
        self.format_combo.addItems(['mp4', 'avi', 'mov', 'mkv'])
        self.format_combo.setStyleSheet(combo_style)
        form_layout.addRow(format_label, self.format_combo)
        
        # Resolution
        res_label = QLabel("Resolution:")
        res_label.setStyleSheet(label_style)
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(['original', '3840x2160 (4K)', '1920x1080 (1080p)', 
                                        '1280x720 (720p)', '854x480 (480p)'])
        self.resolution_combo.setStyleSheet(combo_style)
        form_layout.addRow(res_label, self.resolution_combo)
        
        # Quality preset
        preset_label = QLabel("Quality Preset:")
        preset_label.setStyleSheet(label_style)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(['ultrafast', 'superfast', 'veryfast', 'faster', 
                                    'fast', 'medium', 'slow', 'slower', 'veryslow'])
        self.preset_combo.setCurrentText('medium')
        self.preset_combo.setStyleSheet(combo_style)
        form_layout.addRow(preset_label, self.preset_combo)
        
        # Video bitrate
        vbitrate_label = QLabel("Video Bitrate:")
        vbitrate_label.setStyleSheet(label_style)
        self.vbitrate_combo = QComboBox()
        self.vbitrate_combo.addItems(['4M', '8M', '12M', '16M', '20M', '25M'])
        self.vbitrate_combo.setCurrentText('8M')
        self.vbitrate_combo.setStyleSheet(combo_style)
        form_layout.addRow(vbitrate_label, self.vbitrate_combo)
        
        # Audio bitrate
        abitrate_label = QLabel("Audio Bitrate:")
        abitrate_label.setStyleSheet(label_style)
        self.abitrate_combo = QComboBox()
        self.abitrate_combo.addItems(['128k', '192k', '256k', '320k'])
        self.abitrate_combo.setCurrentText('192k')
        self.abitrate_combo.setStyleSheet(combo_style)
        form_layout.addRow(abitrate_label, self.abitrate_combo)
        
        layout.addLayout(form_layout)
        
        # Export button
        self.export_btn = ModernButton("🚀 Export Synced Video", True)
        self.export_btn.clicked.connect(self.export_video)
        self.export_btn.setEnabled(False)
        layout.addWidget(self.export_btn)
        
        return widget
    
    def select_video(self):
        """Open file dialog to select video file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Video File", "",
            "Video Files (*.mp4 *.avi *.mov *.mkv *.flv *.wmv);;All Files (*)"
        )
        
        if file_path:
            self.video_path = file_path
            self.video_label.setText(Path(file_path).name)
            self.check_ready_to_sync()
    
    def select_audio(self):
        """Open file dialog to select audio file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Audio File", "",
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
        
        self.sync_worker = AudioSyncWorker(
            self.video_path, self.audio_path,
            max_offset=self.max_offset_spin.value()
        )
        
        self.sync_worker.progress.connect(self.update_progress)
        self.sync_worker.finished.connect(self.sync_complete)
        self.sync_worker.error.connect(self.sync_error)
        
        self.sync_worker.start()
    
    def update_progress(self, value: int, message: str):
        """Update progress bar and status"""
        self.progress_bar.setValue(value)
        self.status_label.setText(f"⚙️ {message}")
    
    def sync_complete(self, result: SyncResult):
        """Handle completion of sync analysis"""
        self.sync_result = result
        self.sync_btn.setEnabled(True)
        self.export_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        self.offset_adjust.setValue(result.offset_seconds)
        
        # Confidence indicator
        if result.confidence > 0.7:
            confidence_emoji = "✅"
            confidence_text = "High"
        elif result.confidence > 0.4:
            confidence_emoji = "⚠️"
            confidence_text = "Medium"
        else:
            confidence_emoji = "❌"
            confidence_text = "Low"
        
        results_text = f"""
✨ ANALYSIS COMPLETE

Method: Cross-Correlation AI
Detected Offset: {result.offset_seconds:.3f} seconds
Confidence: {result.confidence:.2%} {confidence_emoji} ({confidence_text})

💡 Interpretation:
"""
        
        if result.offset_seconds > 0:
            results_text += f"   External audio starts {result.offset_seconds:.3f}s INTO the video\n"
        elif result.offset_seconds < 0:
            results_text += f"   External audio starts {abs(result.offset_seconds):.3f}s BEFORE the video\n"
        else:
            results_text += "   Audio and video are already aligned\n"
        
        self.results_text.setPlainText(results_text)
        self.status_label.setText(f"✨ Ready to export! Confidence: {result.confidence:.2%}")
    
    def sync_error(self, error_msg: str):
        """Handle sync analysis error"""
        self.sync_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("❌ Error occurred")
        
        QMessageBox.critical(self, "Synchronization Error",
                           f"An error occurred:\n\n{error_msg}")
    
    def export_video(self):
        """Export video with synced audio"""
        default_name = Path(self.video_path).stem + "_synced." + self.format_combo.currentText()
        output_path, _ = QFileDialog.getSaveFileName(
            self, "Save Synced Video", default_name,
            f"{self.format_combo.currentText().upper()} Video (*.{self.format_combo.currentText()});;All Files (*)"
        )
        
        if not output_path:
            return
        
        # Update export settings
        self.export_settings.format = self.format_combo.currentText()
        self.export_settings.resolution = self.resolution_combo.currentText().split()[0] if self.resolution_combo.currentIndex() > 0 else 'original'
        self.export_settings.preset = self.preset_combo.currentText()
        self.export_settings.video_bitrate = self.vbitrate_combo.currentText()
        self.export_settings.audio_bitrate = self.abitrate_combo.currentText()
        
        final_offset = self.offset_adjust.value()
        mute_original = self.mute_original.isChecked()
        
        self.export_btn.setEnabled(False)
        self.sync_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        self.process_worker = VideoProcessWorker(
            self.video_path, self.audio_path, output_path,
            final_offset, mute_original, self.export_settings
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
        self.status_label.setText("🎉 Export complete!")
        
        QMessageBox.information(self, "Export Complete",
                              f"✅ Video successfully exported to:\n{output_path}")
    
    def export_error(self, error_msg: str):
        """Handle export error"""
        self.export_btn.setEnabled(True)
        self.sync_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("❌ Export failed")
        
        QMessageBox.critical(self, "Export Error",
                           f"An error occurred during export:\n\n{error_msg}")


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    
    # Set application-wide font
    app.setFont(QFont("Segoe UI", 10))
    
    window = VideoAudioSyncApp()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
