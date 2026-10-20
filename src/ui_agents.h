#pragma once
void ui_agents_init();
void ui_agents_show();
void ui_agents_update();
// The Agents screen lists every waiting request itself, so alert banners stay off it.
bool ui_agents_is_active();
