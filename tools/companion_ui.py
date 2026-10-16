"""Explicit data-only companion library actions; decoding and disk work stay off Qt."""
from pathlib import Path
from itertools import islice
import time
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,QFileDialog
import companion_packages as packages


class CompanionView(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner;self.worker=None;self.selected_id=None
        layout=QVBoxLayout(self)
        heading=QLabel('External companion packs');heading.setWordWrap(True);layout.addWidget(heading)
        note=QLabel('Import a version-2 animation ZIP and use it on a supported P4. '
            'The verified pack stays on this PC and is restored over USB after the display restarts. '
            'An incomplete replacement keeps the previous companion. No card formatting is needed.')
        note.setWordWrap(True);layout.addWidget(note)
        self.choices=QComboBox();self.choices.setAccessibleName('Installed companion packs');layout.addWidget(self.choices)
        row=QHBoxLayout()
        self.import_button=QPushButton('Import and use pack…');self.use_button=QPushButton('Use selected pack')
        self.builtin_button=QPushButton('Use built-in NOVA / ORBIT');self.refresh_button=QPushButton('Refresh library')
        self.remove_button=QPushButton('Remove unused pack')
        self.buttons=(self.import_button,self.use_button,self.builtin_button,self.refresh_button,self.remove_button)
        for button in self.buttons:button.setMinimumHeight(44)
        for button in (self.import_button,self.use_button,self.refresh_button):row.addWidget(button)
        layout.addLayout(row)
        second_row=QHBoxLayout();second_row.addWidget(self.builtin_button);second_row.addWidget(self.remove_button)
        layout.addLayout(second_row)
        self.status=QLabel('Loading companion library…');self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.status)
        self.device_status=QLabel('Display activation is confirmed by the running host.');self.device_status.setWordWrap(True)
        self.device_status.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.device_status)
        layout.addStretch()
        self.import_button.clicked.connect(self.choose_file);self.use_button.clicked.connect(self.use_selected)
        self.builtin_button.clicked.connect(self.use_builtin);self.refresh_button.clicked.connect(self.refresh)
        self.remove_button.clicked.connect(self.remove_selected)
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh_device);self.timer.start(1000)
        self.refresh()

    def run(self,operation,success):
        if self.worker is not None or self.owner.closed or self.owner.busy:return
        from desktop_window import ReadWorker
        for button in self.buttons:button.setEnabled(False)
        self.status.setText('Checking companion data…')
        def perform():
            operation()
            folder=packages.directory(self.owner.root,create=False);rows=[];bad=0
            entries=list(islice(folder.glob('*.pack'),17))
            if len(entries)>16:raise ValueError('Companion library exceeds its capacity')
            for path in sorted(entries):
                try:pack=packages.load(self.owner.root,path.stem);rows.append((pack.name,pack.id))
                except (OSError,ValueError):bad+=1
            return rows,packages.selected(self.owner.root),success,bad
        self.worker=ReadWorker(perform)
        self.worker.signals.finished.connect(self.finished,Qt.ConnectionType.QueuedConnection)
        self.owner.status_pool.start(self.worker)

    def finished(self,result):
        self.worker=None
        if self.owner.closed:return
        for button in self.buttons:button.setEnabled(True)
        if result is None:
            self.status.setText('Pack rejected or local library unavailable. Refresh to check the saved selection.');return
        rows,selected,caption,bad=result
        self.selected_id=selected
        self.choices.clear()
        for name,identifier in rows:self.choices.addItem(name,identifier)
        index=self.choices.findData(selected)
        if index>=0:self.choices.setCurrentIndex(index)
        self.status.setText(caption+(' Damaged packs were omitted.' if bad else ''))
        self.refresh_device()

    def refresh(self):self.run(lambda:None,'Library checked. Choose a pack or the built-in companions.')

    def choose_file(self):
        if self.worker is not None:return
        path,_=QFileDialog.getOpenFileName(self,'Import companion pack',str(self.owner.root/'companion-packs'),'Companion packs (*.zip *.aimcompanion)')
        if path:self.import_path(path)

    def import_path(self,path):
        def install():
            pack=packages.install(self.owner.root,Path(path));packages.select(self.owner.root,pack.id)
        self.run(install,'Pack verified and selected. Check display activation below.')

    def use_selected(self):
        identifier=self.choices.currentData()
        if identifier:self.run(lambda:packages.select(self.owner.root,identifier),'Pack selected. Check display activation below.')

    def use_builtin(self):
        self.run(lambda:packages.select(self.owner.root,''),'Built-in companions selected. Check display activation below.')

    def remove_selected(self):
        identifier=self.choices.currentData()
        if identifier:self.run(lambda:packages.remove(self.owner.root,identifier),'Unused library pack removed; original import file was retained.')

    def refresh_device(self):
        health=self.owner.cached_health or {};value=health.get('companion',{})
        stamp=health.get('updated_at')
        current=type(stamp) in (int,float) and 0<=time.time()-stamp<=45
        if health.get('state')!='connected' or not current:caption='Display: start the host and connect the P4.'
        elif value.get('state') in ('active','builtin') and value.get('id')!=self.selected_id:
            caption='Display: the selected companion has not been confirmed yet.'
        else:
            caption={'builtin':'Display: built-in companions confirmed.','active':'Display: external pack activated.',
                'installing':'Display: transferring and verifying the selected pack…',
                'error':'Display: installation failed; previous companion retained. Select the pack again to retry.',
                'overridden':'Display: built-in companion selected on the screen. Use selected pack to restore it.',
                'unsupported':'Display: update to firmware with external companion support.'}.get(value.get('state'),'Display: waiting for confirmation.')
        self.device_status.setText(caption)
