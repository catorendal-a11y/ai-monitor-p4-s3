"""Present a validated connection snapshot; no port, provider or process operations."""
from hardware_baseline import validate_hardware


def mib(value):
    return f'{value / (1024 * 1024):.2f} MiB'


def hardware_text(health):
    if not health or health.get('state')!='connected':
        return 'Connect the host to read device memory. No estimated hardware values are shown.'
    if 'hardware' not in health:
        return 'Device telemetry not received. This feature requires firmware with hardware diagnostics.'
    try:
        data=validate_hardware(health['hardware'],health.get('board'))
    except ValueError:
        return 'Device telemetry unavailable. Reconnect the host to request a fresh snapshot.'
    flash=data['flash']; heap=data['internalHeap']; ram=data['psram']; display=data['display']
    lines=[f'CONNECTION SNAPSHOT / {data["firmwareVersion"]}',
        f'CPU {data["cpuMHz"]} MHz • chip revision (SDK) {data["chipRevision"]} • SDK {data["sdkVersion"]}',
        f'Flash {mib(flash["bytes"])} • app {mib(flash["applicationBytes"])} • free app space {mib(flash["freeApplicationBytes"])}',
        f'PSRAM {mib(ram["sizeBytes"])} • free {mib(ram["free"])} • largest block {mib(ram["largestFreeBlock"])}',
        f'Internal heap free {mib(heap["free"])} • largest block {mib(heap["largestFreeBlock"])}',
        f'Draw buffers {mib(display["drawBytes"])} • rotation {mib(display["rotationBytes"])} • framebuffers {mib(display["framebufferBytes"])}',
        'PPA: supported, inactive' if data['ppa']['supported'] else 'PPA: unsupported',
        f'ESP-Hosted {data["hosted"]["hostVersion"]}: compiled, coprocessor version unknown' if data['hosted']['compiled'] else 'ESP-Hosted: not compiled',
        'C6 and SD: not probed by production firmware']
    for stage in data.get('startupMemory',[]):
        if stage['captured']:
            lines.append(f'{stage["stage"]}: heap free {mib(stage["internalHeap"]["free"])} / PSRAM free {mib(stage["psram"]["free"])}')
    lines.append('Values were sampled at connection. Reconnect to sample again; this is not continuous telemetry.')
    return '\n'.join(lines)
