"""Application-wide visual system for the CampPhoto AI desktop UI."""

SIDEBAR_BG = "#0F172A"
SIDEBAR_HOVER = "#1E293B"
SIDEBAR_ACTIVE = "#2563EB"
CONTENT_BG = "#F4F7FB"
CARD_BG = "#FFFFFF"
BORDER = "#DCE3EC"
BORDER_STRONG = "#CBD5E1"
TEXT_PRIMARY = "#0F172A"
TEXT_SECONDARY = "#334155"
TEXT_MUTED = "#64748B"
ACCENT = "#2563EB"
ACCENT_HOVER = "#1D4ED8"
ACCENT_SOFT = "#EFF6FF"
SUCCESS = "#15803D"
SUCCESS_SOFT = "#F0FDF4"
WARNING = "#B45309"
WARNING_SOFT = "#FFFBEB"
DANGER = "#B91C1C"
DANGER_HOVER = "#991B1B"
DANGER_SOFT = "#FEF2F2"

STYLESHEET = f"""
QWidget {{
    background: {CONTENT_BG};
    color: {TEXT_PRIMARY};
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}}

QMainWindow, QStackedWidget {{
    background: {CONTENT_BG};
}}

QToolTip {{
    color: white;
    background: {SIDEBAR_BG};
    border: 1px solid {SIDEBAR_HOVER};
    padding: 6px 8px;
}}

#sidebar {{
    background: {SIDEBAR_BG};
    border: none;
}}

#brandBlock {{
    background: transparent;
    border: none;
}}

#sidebarTitle {{
    background: transparent;
    color: white;
    font-size: 19px;
    font-weight: 700;
}}

#sidebarSubtitle {{
    background: transparent;
    color: #94A3B8;
    font-size: 11px;
}}

QPushButton#sidebarToggle {{
    min-width: 34px;
    max-width: 34px;
    min-height: 34px;
    max-height: 34px;
    padding: 0;
    border: 1px solid #334155;
    border-radius: 8px;
    background: #172033;
    color: #CBD5E1;
    font-size: 16px;
}}
QPushButton#sidebarToggle:hover {{
    background: {SIDEBAR_HOVER};
    color: white;
    border-color: #475569;
}}

QPushButton#navButton {{
    min-height: 40px;
    text-align: left;
    padding: 0 14px;
    border: none;
    background: transparent;
    color: #CBD5E1;
    font-size: 13px;
    border-radius: 8px;
}}
QPushButton#navButton:hover {{
    background: {SIDEBAR_HOVER};
    color: white;
}}
QPushButton#navButton:checked {{
    background: {SIDEBAR_ACTIVE};
    color: white;
    font-weight: 600;
}}

#sidebarFooter {{
    background: transparent;
    color: #94A3B8;
    font-size: 10px;
}}

#pageTitle {{
    font-size: 24px;
    font-weight: 700;
    color: {TEXT_PRIMARY};
}}

#pageSubtitle {{
    font-size: 12px;
    color: {TEXT_MUTED};
}}

#sectionLabel {{
    font-size: 13px;
    font-weight: 700;
    color: {TEXT_SECONDARY};
}}

#card {{
    background: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}

#cardTitle {{
    background: transparent;
    font-size: 14px;
    font-weight: 700;
    color: {TEXT_PRIMARY};
}}

#cardHint {{
    background: transparent;
    font-size: 12px;
    color: {TEXT_MUTED};
}}

#statTile {{
    background: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
#statTile:hover {{
    border-color: #BFDBFE;
}}
#statValue {{
    background: transparent;
    font-size: 27px;
    font-weight: 700;
    color: {TEXT_PRIMARY};
}}
#statCaption {{
    background: transparent;
    font-size: 11px;
    color: {TEXT_MUTED};
}}

QPushButton {{
    min-height: 36px;
    background: white;
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER_STRONG};
    border-radius: 8px;
    padding: 0 14px;
    font-weight: 500;
}}
QPushButton:hover {{
    border-color: #93C5FD;
    background: #F8FBFF;
}}
QPushButton:pressed {{
    background: #EFF6FF;
}}
QPushButton:disabled {{
    color: #94A3B8;
    background: #F1F5F9;
    border-color: {BORDER};
}}

QPushButton#primaryButton {{
    background: {ACCENT};
    color: white;
    border: 1px solid {ACCENT};
    font-weight: 600;
}}
QPushButton#primaryButton:hover {{
    background: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}

QPushButton#secondaryButton {{
    background: {ACCENT_SOFT};
    color: {ACCENT_HOVER};
    border: 1px solid #BFDBFE;
    font-weight: 600;
}}

QPushButton#ghostButton {{
    background: transparent;
    color: {TEXT_SECONDARY};
    border: 1px solid transparent;
}}
QPushButton#ghostButton:hover {{
    background: #EEF2F7;
    border-color: #E2E8F0;
}}

QPushButton#dangerButton {{
    background: white;
    color: {DANGER};
    border: 1px solid #FCA5A5;
    font-weight: 600;
}}
QPushButton#dangerButton:hover {{
    background: {DANGER};
    color: white;
    border-color: {DANGER};
}}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    min-height: 36px;
    background: white;
    border: 1px solid {BORDER_STRONG};
    border-radius: 8px;
    padding: 0 10px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {ACCENT};
}}
QLineEdit:disabled {{
    background: #F1F5F9;
    color: {TEXT_MUTED};
}}

QComboBox::drop-down {{
    width: 28px;
    border: none;
}}

QCheckBox {{
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 17px;
    height: 17px;
}}

QListWidget, QTextEdit {{
    background: white;
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 4px;
}}
QListWidget::item {{
    border-radius: 7px;
    padding: 9px 8px;
    margin: 2px;
}}
QListWidget::item:hover {{
    background: #F1F5F9;
}}
QListWidget::item:selected {{
    color: {TEXT_PRIMARY};
    background: #DBEAFE;
}}

QTextEdit {{
    padding: 8px;
}}

QProgressBar {{
    min-height: 14px;
    max-height: 14px;
    border: none;
    border-radius: 7px;
    text-align: center;
    background: #E2E8F0;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 7px;
}}

#reviewPreview, #cameraPreview {{
    background: #F8FAFC;
    border: 1px dashed {BORDER_STRONG};
    border-radius: 10px;
    color: {TEXT_MUTED};
}}

#hintLabel {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}

#statusLabel {{
    color: {TEXT_SECONDARY};
    font-weight: 500;
}}

#successBanner {{
    background: {SUCCESS_SOFT};
    color: {SUCCESS};
    border: 1px solid #BBF7D0;
    border-radius: 8px;
    padding: 10px 12px;
}}

#warningBanner {{
    background: {WARNING_SOFT};
    color: {WARNING};
    border: 1px solid #FDE68A;
    border-radius: 8px;
    padding: 10px 12px;
}}

#errorBanner {{
    background: {DANGER_SOFT};
    color: {DANGER};
    border: 1px solid #FECACA;
    border-radius: 8px;
    padding: 10px 12px;
}}

#infoBanner {{
    background: {ACCENT_SOFT};
    color: {ACCENT_HOVER};
    border: 1px solid #BFDBFE;
    border-radius: 8px;
    padding: 10px 12px;
}}

#emptyState {{
    background: #F8FAFC;
    border: 1px dashed {BORDER_STRONG};
    border-radius: 10px;
}}

#emptyTitle {{
    background: transparent;
    font-size: 14px;
    font-weight: 700;
    color: {TEXT_SECONDARY};
}}

#emptyBody {{
    background: transparent;
    font-size: 12px;
    color: {TEXT_MUTED};
}}

QScrollArea {{
    border: none;
    background: transparent;
}}

QScrollArea > QWidget > QWidget {{
    background: {CONTENT_BG};
}}

QStatusBar {{
    background: white;
    color: {TEXT_MUTED};
    border-top: 1px solid {BORDER};
    font-size: 11px;
}}
QStatusBar::item {{
    border: none;
}}

QFrame[divider="true"] {{
    color: {BORDER};
}}

QMessageBox {{
    background: {CARD_BG};
}}
"""