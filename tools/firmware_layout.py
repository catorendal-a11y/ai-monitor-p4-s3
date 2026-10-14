"""Validate boot capacity and partitions, not just a successful flash write."""
import hashlib
import struct


def validate_factory(factory, application, board):
    header = factory[board.bootloader_offset:board.bootloader_offset + 24]
    if len(header) != 24 or header[0] != 0xe9 or struct.unpack_from('<H', header, 12)[0] != board.image_chip_id:
        raise ValueError('Factory bootloader does not match the selected chip')
    size_code = header[3] >> 4
    if size_code > 7 or (1024 * 1024 << size_code) != board.flash_bytes:
        raise ValueError('Factory bootloader flash capacity does not match the board')
    if factory[0x10000:0x10000 + len(application)] != application:
        raise ValueError('Factory and application images do not match')
    table = factory[0x8000:0x9000]
    if len(table) != 4096:
        raise ValueError('Factory partition table is missing')
    partitions = []
    digest_found = False
    for position in range(0, len(table), 32):
        entry = table[position:position + 32]
        if entry[:2] == b'\xeb\xeb':
            if entry[2:16] != b'\xff' * 14 or hashlib.md5(table[:position], usedforsecurity=False).digest() != entry[16:]:
                raise ValueError('Partition table checksum is invalid')
            digest_found = True
            break
        if entry == b'\xff' * 32:
            break
        if entry[:2] != b'\xaa\x50':
            raise ValueError('Invalid partition entry')
        _, kind, subtype, offset, size, _, _ = struct.unpack('<HBBII16sI', entry)
        if kind not in (0, 1) or not size or offset < 0x9000 or offset + size > board.flash_bytes:
            raise ValueError('Partition exceeds the board flash capacity')
        if offset % 4096 or (kind == 0 and offset % 65536):
            raise ValueError('Partition alignment is invalid')
        if any(offset < end and start < offset + size for _, _, start, end in partitions):
            raise ValueError('Partitions overlap')
        partitions.append((kind, subtype, offset, offset + size))
    if not digest_found or not partitions:
        raise ValueError('A verified partition table is required')
    if not any(kind == 0 and start == 0x10000 and end - start >= len(application)
               for kind, _, start, end in partitions):
        raise ValueError('Application does not fit its boot partition')
