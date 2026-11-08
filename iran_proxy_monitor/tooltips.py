"""Small, keyboard-independent, non-intrusive Tk tooltip helper.

Tooltips explain controls; they never contain node credentials or share URLs.
"""
from __future__ import annotations
import tkinter as tk


class Tooltips:
    def __init__(self, root, delay_ms=600):
        self.root = root
        self.delay_ms = delay_ms
        self.pending = None
        self.popup = None
        self.active_key = None
        self.last_text = ''

    def hide(self, event=None):
        if self.pending is not None:
            try: self.root.after_cancel(self.pending)
            except tk.TclError: pass
            self.pending = None
        if self.popup is not None:
            try: self.popup.destroy()
            except tk.TclError: pass
            self.popup = None
        self.active_key = None

    def _schedule(self, widget, text, key=None):
        if not text: self.hide(); return
        key = key if key is not None else widget
        if self.active_key == key:
            return
        self.hide()
        self.active_key = key
        self.last_text = text
        self.pending = self.root.after(self.delay_ms, lambda: self._show(widget, text, key))

    def _show(self, widget, text, key):
        self.pending = None
        if self.active_key != key:
            return
        try:
            if not widget.winfo_exists(): return
            x = widget.winfo_pointerx() + 15
            y = widget.winfo_pointery() + 20
            display_w = self.root.winfo_screenwidth()
            display_h = self.root.winfo_screenheight()
            popup = tk.Toplevel(self.root)
            popup.wm_overrideredirect(True)
            popup.attributes('-topmost', True)
            label = tk.Label(popup, text=text, justify='left', wraplength=350,
                             background='#f5f7fa', foreground='#152033',
                             borderwidth=1, relief='solid', font=('Segoe UI', 9),
                             padx=10, pady=7)
            label.pack()
            popup.update_idletasks()
            x = max(0, min(x, display_w - popup.winfo_reqwidth() - 8))
            y = max(0, min(y, display_h - popup.winfo_reqheight() - 8))
            popup.wm_geometry(f'+{x}+{y}')
            self.popup = popup
        except tk.TclError:
            return

    def attach(self, widget, text):
        widget.bind('<Enter>', lambda e, w=widget, t=text: self._schedule(w, t), add='+')
        widget.bind('<Leave>', self.hide, add='+')
        widget.bind('<ButtonPress>', self.hide, add='+')
        return widget

    def tree_headings(self, tree, mapping):
        """Heading tooltips work even though Tk headings are not widgets."""
        def moved(event):
            region = tree.identify_region(event.x, event.y)
            col = tree.identify_column(event.x) if region == 'heading' else ''
            if col.startswith('#'):
                try: index = int(col[1:]) - 1
                except ValueError: index = -1
                text = mapping[index] if 0 <= index < len(mapping) else ''
            else: text = ''
            self._schedule(tree, text, ('heading', col)) if text else self.hide()
        tree.bind('<Motion>', moved, add='+')
        tree.bind('<Leave>', self.hide, add='+')
        tree.bind('<ButtonPress>', self.hide, add='+')
