# Choose your display board

One repository and one Windows package contain two separate firmware builds. Open **Setup** in the desktop app and choose the exact board before choosing AI providers, then save settings. New installations have no board or AI provider preselected. Existing configurations without a `board` field retain the original P4 target.

| Board | Status | Screen | Host connection | Build environment |
| --- | --- | --- | --- | --- |
| GUITION JC4880P433 ESP32-P4 | Existing supported target | ST7701S MIPI DSI, rotated to 800 × 480 | Espressif USB data port | `esp32p4-release` |
| Original Waveshare ESP32-S3-Touch-LCD-4.3 | **Experimental; physical hardware unverified** | ST7262 RGB, 800 × 480 | **USB TO UART** connector, CH343 bridge | `esp32s3-waveshare-43-release` |

The S3 build targets the **original CH422G board with 16 MB flash and 8 MB OPI PSRAM**. It does not support the B, C or other similarly named variants. Verify the model on the board and its manufacturer's documentation before installing.

Both builds use LVGL 9.6 and the same dashboard, provider choices, NOVA/ORBIT artwork, themes, warnings and saved settings. They have independent display drivers and firmware identities. The PC app chooses the corresponding image and esptool chip, verifies file sizes, SHA-256, image chip headers and factory/application consistency, and checks the board identity during the host handshake. USB vendor IDs identify candidate ports only; they are not proof of a board's identity. Select an explicit port when several candidates appear.

## Waveshare S3 setup

1. Connect a data cable to **USB TO UART**. Use this connector for both firmware installation and everyday host operation. The board's native USB connector is not the AI Monitor transport in this build.
2. Open Setup, choose **Waveshare ESP32-S3 4.3" (experimental)**, select your AI providers and the UART COM port, then save settings. Install the manufacturer's CH343 driver if Windows does not list the bridge.
3. Open Install / update firmware and check the selected board again. Use **First installation** when replacing the manufacturer's demo or another project's firmware. Type `FLASH` only after checking the board and port.
4. Start the host. If normal flashing cannot connect, follow Waveshare's BOOT/RESET recovery instructions for this exact model. Stop the host and close serial monitors before flashing.

Never apply an application-only update to a board using a different partition layout. Both targets use this project's 16 MB layout, with the application at `0x10000`. Their bootloaders differ: S3 at `0x0`, P4 at `0x2000`; factory images are flashed at `0x0`.

## Brightness and performance

P4 retains hardware PWM backlight dimming. The original S3 board exposes its backlight through CH422G EXIO2 as an **on/off switch**. Its brightness presets, fades and night schedule therefore attenuate the rendered image with a black overlay; setting zero switches the LEDs off. Intermediate brightness values do not reduce LED power like PWM does. The overlay passes touch events through and stays above dashboard, settings and alert overlays.

The S3 backend uses one PSRAM framebuffer, two 10-line RGB bounce buffers and one 20-line LVGL draw buffer to fit the 8 MB PSRAM board. It pins Arduino 3.2.0 and Espressif's matching high-performance SDK with PSRAM XIP; a compile-time guard rejects a build without that cache configuration. The P4 SDK remains independent. A single RGB framebuffer can show tearing during updates. Smoothness, touch alignment, cold boot, USB reconnect, long operation and persistence while RGB is scanning still require a physical S3 test. Passing native UI tests or compiling firmware does not establish those hardware results.

## References

- [Waveshare original board documentation](https://docs.waveshare.com/ESP32-S3-Touch-LCD-4.3) and [FAQ](https://docs.waveshare.com/ESP32-S3-Touch-LCD-4.3/FAQ).
- [Official board pin/timing profile, ESP32 Display Panel v1.0.4](https://github.com/esp-arduino-libs/ESP32_Display_Panel/blob/v1.0.4/src/board/supported/waveshare/BOARD_WAVESHARE_ESP32_S3_TOUCH_LCD_4_3.h).
- [WCH CH422 datasheet](https://files.waveshare.com/wiki/common/CH422DS1_EN.pdf): system address `0x24`, output bank `0x38` in 7-bit I2C form; EXIO1 touch reset, EXIO2 backlight, EXIO3 LCD reset, EXIO5 USB/CAN selection.
- [Espressif RGB LCD driver and bounce buffer cache considerations](https://docs.espressif.com/projects/esp-idf/en/v5.5.2/esp32s3/api-reference/peripherals/lcd/rgb_lcd.html).
- [Official matching high-performance Arduino SDK](https://github.com/esp-arduino-libs/arduino-esp32-sdk).
