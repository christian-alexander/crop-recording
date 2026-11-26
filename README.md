# Crop Recording

Crop Recording captures a selected area of your Linux desktop as a lossless MP4 at 30 fps without audio. It runs in the background and shows the elapsed time outside the recorded area.

## Install

Use an **X11 desktop session** such as **Ubuntu on Xorg**. To check your session, run `echo "$XDG_SESSION_TYPE"`. It should print `x11`.

Crop Recording was tested on Ubuntu 24.04 LTS. It requires Python 3.10 or newer and FFmpeg 5.1 or newer with X11 capture and the `libx264rgb` encoder.

Open a terminal in the directory containing the `.deb` and run:

```bash
sudo apt install ./crop-recording_1.2.4_all.deb
```

The installed service starts automatically when you log in to an X11 desktop.

## Record

1. Press **Ctrl+R** to open the area picker.
2. Drag to select the area. Press **Esc** to cancel.
3. Press **Ctrl+Enter** to start recording. Press **Ctrl+Enter** again to stop.
4. Select **Save to Folder** to choose a location, or **Copy Video** to paste the MP4 into an app that accepts file attachments.

To check whether the service is running, use `systemctl --user status crop-recording.service`.
