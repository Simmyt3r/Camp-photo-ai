"""QSS stylesheet for the desktop app -- a clean, intentional look rather
than raw OS-default widget styling (section 17: "Build a professional
PySide6 desktop interface"). No CampPhoto AI brand palette exists yet, so
this uses a neutral slate + blue scheme common to professional tools;
swap these constants if/when Silabs wants specific brand colors applied."""

SIDEBAR_BG = "#1E293B"
SIDEBAR_HOVER = "#334155"
SIDEBAR_ACTIVE = "#3B82F6"
CONTENT_BG = "#F8FAFC"
CARD_BG = "#FFFFFF"
BORDER = "#E2E8F0"
TEXT_PRIMARY = "#0F172A"
TEXT_MUTED = "#64748B"
ACCENT = "#3B82F6"
ACCENT_HOVER = "#2563EB"

STYLESHEET = f"""
QWidget {{
    background: {CONTENT_BG};
    color: {TEXT_PRIMARY};
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}}

#sidebar {{ background: {SIDEBAR_BG}; }}

#sidebarTitle {{
    color: white;
    font-size: 18px;
    font-weight: 600;
    padding: 0 20px;
}}

QPushButton#navButton {{
    text-align: left;
    padding: 12px 20px;
    border: none;
    background: transparent;
    color: #CBD5E1;
    font-size: 13px;
    border-radius: 0;
}}
QPushButton#navButton:hover {{ background: {SIDEBAR_HOVER}; color: white; }}
QPushButton#navButton:checked {{ background: {SIDEBAR_ACTIVE}; color: white; font-weight: 600; }}

#pageTitle {{ font-size: 22px; font-weight: 700; color: {TEXT_PRIMARY}; }}

#sectionLabel {{ font-size: 14px; font-weight: 600; color: {TEXT_MUTED}; margin-top: 8px; }}

#statTile {{ background: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 10px; }}
#statValue {{ font-size: 26px; font-weight: 700; color: {TEXT_PRIMARY}; }}
#statCaption {{ font-size: 12px; color: {TEXT_MUTED}; }}

QPushButton#primaryButton {{
    background: {ACCENT};
    color: white;
    border: none;
    border-radius: 6px;
    padding: 10px 18px;
    font-weight: 600;
}}
QPushButton#primaryButton:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#primaryButton:disabled {{ background: #94A3B8; }}

QPushButton#disabledButton {{
    background: #E2E8F0;
    color: {TEXT_MUTED};
    border: none;
    border-radius: 6px;
    padding: 10px 18px;
}}

QPushButton {{
    background: white;
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 14px;
}}
QPushButton:hover {{ border-color: {ACCENT}; }}

QLineEdit, QComboBox {{
    background: white;
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 10px;
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}

#reviewPreview, #cameraPreview {{
    background: white;
    border: 1px dashed {BORDER};
    border-radius: 8px;
    color: {TEXT_MUTED};
}}

QListWidget, QTextEdit {{
    background: white;
    border: 1px solid {BORDER};
    border-radius: 8px;
}}

QProgressBar {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    text-align: center;
    background: white;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 6px; }}

#hintLabel {{ color: {TEXT_MUTED}; font-size: 12px; }}
#statusLabel {{ font-weight: 500; }}
"""
