#pragma once
// AI Monitor P4 - full-screen dashboard (800x480 landscape, dark industrial).
// Created and updated from the UI task only (all lv_* calls stay there).

void dashboard_init();
void dashboard_show();
void dashboard_update();  // call every ~40 ms from the UI task loop
