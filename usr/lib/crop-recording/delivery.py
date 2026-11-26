"""Save a finished recording or offer it on the desktop clipboard."""
import errno
import os
from pathlib import Path
import shutil
import tempfile

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk


MAX_INLINE_VIDEO = 32 * 1024 * 1024


class FileClipboard:
    def __init__(self):
        self.widget = Gtk.Invisible()
        self.widget.realize()
        self.selection = Gdk.SELECTION_CLIPBOARD
        self.path = None
        self.widget.connect("selection-get", self.provide)

    def copy(self, path):
        if not path.is_file():
            raise FileNotFoundError(f"Video not found: {path}")
        # Confined browsers cannot read the host's /tmp or hidden home folders.
        folder = Path.home() / "Crop Recording Clipboard"
        folder.mkdir(mode=0o700, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=f"{path.stem}-", suffix=".mp4", dir=folder)
        destination = Path(name)
        try:
            with os.fdopen(fd, "wb") as output, path.open("rb") as source:
                shutil.copyfileobj(source, output)
            targets = [
                Gtk.TargetEntry.new("text/uri-list", 0, 1),
                Gtk.TargetEntry.new("x-special/gnome-copied-files", 0, 2),
            ]
            # GTK buffers binary selection data in memory. The attachment
            # format still supplies the entire file for larger recordings.
            if destination.stat().st_size <= MAX_INLINE_VIDEO:
                targets.append(Gtk.TargetEntry.new("video/mp4", 0, 3))
            if not Gtk.selection_owner_set(self.widget, self.selection, Gdk.CURRENT_TIME):
                raise RuntimeError("Could not access the clipboard.")
            Gtk.selection_clear_targets(self.widget, self.selection)
            Gtk.selection_add_targets(self.widget, self.selection, targets)
            self.path = destination
        except (OSError, RuntimeError):
            destination.unlink(missing_ok=True)
            raise
        try:
            path.unlink()
            path.parent.rmdir()
        except OSError:
            pass
        return destination

    def provide(self, _widget, data, target, _timestamp):
        if self.path is None:
            return
        if target == 1:
            data.set_uris([self.path.as_uri()])
        elif target == 2:
            data.set(data.get_target(), 8, f"copy\n{self.path.as_uri()}".encode())
        elif target == 3:
            try:
                with self.path.open("rb") as source:
                    video = source.read(MAX_INLINE_VIDEO + 1)
                if len(video) <= MAX_INLINE_VIDEO:
                    data.set(data.get_target(), 8, video)
            except OSError:
                pass


def save_recording(source, destination):
    if source == destination:
        return
    try:
        source.replace(destination)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        fd, name = tempfile.mkstemp(prefix=".crop-recording-", dir=destination.parent)
        os.close(fd)
        partial = Path(name)
        try:
            shutil.copyfile(source, partial)
            partial.replace(destination)
        finally:
            partial.unlink(missing_ok=True)
        try:
            source.unlink(missing_ok=True)
        except OSError:
            pass
    try:
        source.parent.rmdir()
    except OSError:
        pass


class RecordingDialog:
    def __init__(self, path, clipboard, finished, timestamp):
        self.path = path
        self.clipboard = clipboard
        self.finished = finished
        self.chooser = None
        self.dialog = Gtk.MessageDialog(
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text="Recording finished",
        )
        self.dialog.set_title("Crop Recording — Recording finished")
        self.dialog.set_property("secondary-text", "Save the video or copy it to paste as an attachment.")
        self.dialog.set_keep_above(True)
        self.dialog.add_button("Close", Gtk.ResponseType.CLOSE)
        self.dialog.add_button("Copy Video", Gtk.ResponseType.APPLY)
        self.dialog.add_button("Save to Folder…", Gtk.ResponseType.ACCEPT)
        self.dialog.connect("response", self.on_response)
        self.dialog.present_with_time(timestamp)

    def on_response(self, _dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            self.chooser = Gtk.FileChooserNative.new(
                "Save Recording", self.dialog, Gtk.FileChooserAction.SAVE, "Save", "Cancel",
            )
            self.chooser.set_modal(True)
            self.chooser.set_local_only(True)
            self.chooser.set_do_overwrite_confirmation(True)
            videos = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_VIDEOS)
            folder = Path(videos) if videos and Path(videos).is_dir() else Path.home()
            self.chooser.set_current_folder(str(folder))
            self.chooser.set_current_name(self.path.name)
            self.chooser.connect("response", self.on_save)
            self.dialog.set_sensitive(False)
            self.chooser.show()
        elif response == Gtk.ResponseType.APPLY:
            try:
                copied = self.clipboard.copy(self.path)
            except (OSError, RuntimeError) as exc:
                self.dialog.set_property("secondary-text", str(exc))
                return
            self.close(copied, "Video copied to the clipboard.")
        else:
            self.close(self.path)

    def on_save(self, chooser, response):
        filename = chooser.get_filename() if response == Gtk.ResponseType.ACCEPT else None
        chooser.destroy()
        self.chooser = None
        self.dialog.set_sensitive(True)
        if not filename:
            self.dialog.present()
            return
        destination = Path(filename)
        try:
            save_recording(self.path, destination)
        except OSError as exc:
            self.dialog.set_property("secondary-text", f"Could not save the video: {exc}")
            self.dialog.present()
            return
        self.close(destination, f"Video saved to {destination.parent}.")

    def close(self, path, message=None):
        if self.chooser:
            self.chooser.destroy()
            self.chooser = None
        self.dialog.destroy()
        self.finished(path, message)
