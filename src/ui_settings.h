#pragma once
// AI Monitor P4 - on-device settings screen (own LVGL screen, UI-task only).

void ui_settings_init();
void ui_settings_update();
void ui_settings_show();   // load the settings screen
void ui_settings_hide();   // return to the dashboard screen
bool ui_settings_is_active();
