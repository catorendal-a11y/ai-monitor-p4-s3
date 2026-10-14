"""Create the factory image absent from the pinned S3 platform's normal build."""
Import('env')
from pathlib import Path
import subprocess
import sys


def factory_image(source, target, env):
    application = Path(env.subst('$BUILD_DIR/${PROGNAME}.bin'))
    factory = application.with_suffix('.factory.bin')
    offset = env.subst('$ESP32_APP_OFFSET')
    if int(offset, 0) != 0x10000:
        raise RuntimeError('Unexpected S3 application partition offset')
    command = [sys.executable, env.subst('$OBJCOPY').strip('"'), '--chip', 'esp32s3',
               'merge_bin', '-o', str(factory)]
    for address, image in env.get('FLASH_EXTRA_IMAGES', []):
        command.extend([str(address), env.subst(image)])
    command.extend([offset, str(application)])
    subprocess.run(command, check=True)


env.AddPostAction('$BUILD_DIR/${PROGNAME}.bin', factory_image)
