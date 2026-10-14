#pragma once
void ui_event_center_init();
void ui_event_center_update();
void ui_event_center_show();
bool ui_event_center_is_active();
unsigned ui_event_center_unread();
void ui_event_center_quota(const char* source,bool critical);
