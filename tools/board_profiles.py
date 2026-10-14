"""Allowlisted display targets; remote data cannot choose flash commands."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Board:
    id: str
    name: str
    chip: str
    image_chip_id: int
    bootloader_offset: int
    environment: str
    usb_vids: tuple
    experimental: bool = False
    flash_bytes: int = 16 * 1024 * 1024


BOARDS = {
    'guition-p4': Board('guition-p4', 'GUITION JC4880P433 ESP32-P4', 'esp32p4', 18, 0x2000,
                        'esp32p4-release', (0x303a,)),
    'waveshare-s3-43': Board('waveshare-s3-43', 'Waveshare ESP32-S3-Touch-LCD-4.3', 'esp32s3', 9, 0,
                            'esp32s3-waveshare-43-release', (0x1a86,), True),
}


def get_board(identifier):
    if not isinstance(identifier, str) or identifier not in BOARDS:
        raise ValueError('Choose a supported display board in First-time setup')
    return BOARDS[identifier]


def configured_board(config, legacy=True):
    identifier = config.get('board', 'guition-p4' if legacy else '')
    if identifier != '': get_board(identifier)
    return identifier


def matches_info(board, info):
    if not isinstance(info, dict): return False
    if 'boardId' in info:
        return info['boardId'] == board.id and info.get('chip') == board.chip
    # Older public firmware only existed for this exact P4 display.
    return board.id == 'guition-p4' and info.get('display') == 'jc4880p433' and info.get('panelId') == 'esp32p4-mipi-dsi'
