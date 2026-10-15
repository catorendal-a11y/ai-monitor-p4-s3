"""Bounded local insights views; observations run outside the Qt UI thread."""
import csv
import time
from datetime import datetime, timezone
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtCore import QSignalBlocker
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QLabel,
    QHBoxLayout, QVBoxLayout, QWidget, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QPlainTextEdit)
from provider_catalog import PROVIDERS


class SetupReportDialog(QDialog):
    def __init__(self, results, parent=None):
        super().__init__(parent)
        self.results=results
        self.closed=False; self.test_worker=None; self.test_generation=0
        self.test_active=False; self.observed=set(); self.reporter=None
        self.setWindowTitle('AI connection checklist')
        self.resize(900,580)
        layout=QVBoxLayout(self)
        intro=QLabel('Activity, account quota and USB delivery are separate checks. '
                    'Readable records do not prove a new token increase. This check sends no model request.')
        intro.setWordWrap(True); intro.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(intro)
        self.table=QTableWidget(len(results),5)
        self.table.setHorizontalHeaderLabels(['AI','Local activity','Account quota','Display','Session events'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        captions={'verified':'received by host','failed':'last request failed','pending-running':'not reported yet',
                  'pending-stopped':'start host to verify','unsupported':'not supported','missing':'use client / link source',
                  'readable':'source readable','unconfirmed':'not confirmed','connected':'USB connected',
                  'source-echoed':'source echoed by display'}
        for row,item in enumerate(results):
            for col,key in enumerate(('provider','activity','quota','display','sessions')):
                value=PROVIDERS[item[key]][0] if key=='provider' else captions.get(item[key],item[key])
                self.table.setItem(row,col,QTableWidgetItem(value))
            self.table.setRowHeight(row,55)
        layout.addWidget(self.table,1)
        self.test_button=QPushButton('Observe token activity for 60 seconds')
        self.test_button.setFixedHeight(44); self.test_button.setEnabled(bool(results))
        self.test_button.clicked.connect(self.start_test); layout.addWidget(self.test_button)
        self.test_notice=QLabel('Use your AI normally during the test. New sessions may need a second completed turn after the baseline.')
        self.test_notice.setWordWrap(True); layout.addWidget(self.test_notice)
        self.test_timer=QTimer(self); self.test_timer.setInterval(2000)
        self.test_timer.timeout.connect(self._sample)
        self.detail=QPlainTextEdit(); self.detail.setReadOnly(True); self.detail.setFixedHeight(110)
        self.detail.setAccessibleName('Selected AI next setup step')
        layout.addWidget(self.detail)
        self.guide=QPushButton('Open selected AI setup')
        self.guide.setFixedHeight(44); self.guide.setEnabled(bool(results))
        self.guide.clicked.connect(self.accept)
        layout.addWidget(self.guide)
        close=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject); layout.addWidget(close)
        self.table.currentCellChanged.connect(self._selected)
        if results: self.table.setCurrentCell(0,0)
        else: self.detail.setPlainText('Choose and save your AI providers before checking setup.')

    def _selected(self,row,*unused):
        if 0<=row<len(self.results):
            item=self.results[row]
            self.detail.setPlainText('Event setup: '+item.get('events','not checked')+'\n'+
                item.get('live_usb','Agent USB: not checked')+'\n'+item['next_step'])

    def provider(self):
        row=self.table.currentRow()
        return self.results[row]['provider'] if 0<=row<len(self.results) else None

    def start_test(self):
        if not self.results: return
        from token_activity import TokenSampler
        owner=self.parent()
        providers=[r['provider'] for r in self.results]
        if owner.live_sampler is None:
            owner.live_sampler=TokenSampler(providers=providers,activity_dir=owner.root/'tools/activity')
        else: owner.live_sampler.configure(providers)
        self.test_generation+=1; self.test_active=True; self.observed=set()
        for row in range(len(self.results)):
            self.table.item(row,1).setText('baseline pending')
            self.table.item(row,3).setText('not confirmed')
        self.deadline=time.monotonic()+60
        self.test_button.setEnabled(False)
        self.test_notice.setText('Watching local numeric counters. Use the selected AI tools normally; no model request is generated by this test.')
        self.test_timer.start(); self._sample()

    def _sample(self):
        if self.closed or not self.test_active: return
        if time.monotonic()>=self.deadline:
            self.test_active=False; self.test_timer.stop(); self.test_button.setEnabled(True)
            self.test_notice.setText(f'Test finished: new token increases observed for {len(self.observed)} of {len(self.results)} selected AIs. '
                'No observed increase does not prove a broken integration; the client may save records later.')
            return
        sample=self.parent().live_sampler.poll()
        self._sample_finished((self.test_generation,sample,sample.get('deltas',{}) if sample else {},self.parent().cached_health))

    def _sample_finished(self,result):
        self.test_worker=None
        if self.closed or not self.test_active: return
        if result is None:
            self.test_notice.setText('A local observation failed. Retrying without modifying the AI client.'); return
        generation,sample,deltas,health=result
        if generation!=self.test_generation: return
        for row,item in enumerate(self.results):
            key=item['provider']
            self.table.item(row,3).setText('not confirmed')
            if sample and deltas.get(key,0)>0:
                self.observed.add(key); self.table.item(row,1).setText('new increase observed')
            elif sample and key not in self.observed:
                self.table.item(row,1).setText('baseline established' if sample.get('sources',0)&PROVIDERS[key][1] else 'source unavailable')
            if health and health['state']=='connected' and health.get('board')==self.parent().config.get('board') and self.parent().config['port'] in ('auto',health.get('port')):
                self.table.item(row,3).setText('USB connected')
                mask,stamp=health.get('display_sources'),health.get('display_sources_at')
                if type(mask) is int and type(stamp) in (int,float) and 0<=time.time()-stamp<=35 and mask & PROVIDERS[key][1]:
                    self.table.item(row,3).setText('source echoed by display')
        self.test_notice.setText(f'Watching / {max(0,int(self.deadline-time.monotonic()))} seconds left. '
                                 f'{len(self.observed)} of {len(self.results)} AIs have a new recorded increase.')

    def done(self,result):
        self.closed=True; self.test_active=False; self.test_timer.stop()
        super().done(result)


class HistoryChart(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.rows=[]
        self.quota=[]
        self.quota_mode=False
        self.setMinimumHeight(155)
        self.setAccessibleName('Daily observed token increases; UTC dates, gaps mean no observations')

    def set_rows(self,rows):
        self.rows=rows[:31]; self.quota=[]; self.quota_mode=False; self.update()

    def set_quota(self,rows):
        self.rows=[]; self.quota=sorted(rows,key=lambda r:r['minute'])[:256]; self.quota_mode=True; self.update()

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.fillRect(self.rect(),QColor('#101b22'))
        painter.setPen(QColor('#b3c4cd'))
        if self.quota:
            rows=self.quota; first,last=rows[0]['minute'],rows[-1]['minute']
            width,height=max(1,self.width()-24),max(1,self.height()-54)
            previous=None
            for row in rows:
                point=(12+(row['minute']-first)*width/max(1,last-first),18+(100-row['used'])*height/100)
                painter.setPen(QColor('#35c987'))
                if previous and row['reset']==previous[0]['reset'] and row['epoch']==previous[0]['epoch'] and row['used']>=previous[0]['used'] and row['minute']-previous[0]['minute']<=10:
                    painter.drawLine(int(previous[1][0]),int(previous[1][1]),int(point[0]),int(point[1]))
                painter.drawEllipse(int(point[0])-2,int(point[1])-2,4,4)
                previous=(row,point)
            painter.setPen(QColor('#b3c4cd'))
            painter.drawText(12,14,'Quota used % / 0—100; dots are recorded observations')
            start=datetime.fromtimestamp(first*60,timezone.utc).strftime('%d %b %H:%M')
            end=datetime.fromtimestamp(last*60,timezone.utc).strftime('%H:%M UTC')
            painter.drawText(12,self.height()-8,start+' — '+end)
            painter.end(); return
        if not self.rows:
            painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'No quota observations yet' if self.quota_mode else 'No observed token history yet')
            painter.end(); return
        first,last=self.rows[0]['day'],self.rows[-1]['day']
        count=max(1,last-first+1); maximum=max(r['total'] for r in self.rows) or 1
        left,top,width,height=12,18,max(1,self.width()-24),max(1,self.height()-54)
        painter.drawText(left,14,f'{maximum:,} tokens (highest observed day)')
        for row in self.rows:
            x=left+(row['day']-first)*width/count
            bar=max(1,row['total']/maximum*height)
            painter.fillRect(int(x),int(top+height-bar),max(1,int(width/count)-3),int(bar),QColor('#35c987'))
        painter.setPen(QColor('#b3c4cd'))
        start=datetime.fromtimestamp(first*86400,timezone.utc).strftime('%d %b')
        finish=datetime.fromtimestamp(last*86400,timezone.utc).strftime('%d %b')
        painter.drawText(left,self.height()-8,start+' — '+finish+' UTC; gaps have no observations')
        painter.end()


class HistoryView(QWidget):
    def __init__(self,owner):
        super().__init__()
        self.owner=owner; self.worker=None; self.data=None; self.generation=0
        layout=QVBoxLayout(self)
        row=QHBoxLayout()
        self.provider=QComboBox(); self.provider.setAccessibleName('History AI provider')
        for key,(name,_,_) in PROVIDERS.items(): self.provider.addItem(name,key)
        self.provider.setCurrentIndex(-1); self.provider.setPlaceholderText('Choose an AI history')
        self.period=QComboBox(); self.period.addItem('7 days',7); self.period.addItem('30 days',30)
        self.period.setAccessibleName('History period')
        row.addWidget(self.provider,1); row.addWidget(self.period)
        self.refresh_button=QPushButton('Refresh history'); self.export_button=QPushButton('Export CSV…')
        for button in (self.refresh_button,self.export_button): button.setFixedHeight(44); row.addWidget(button)
        layout.addLayout(row)
        metrics=QHBoxLayout()
        self.metric_combo=QComboBox(); self.metric_combo.addItem('Observed tokens / day','tokens'); self.metric_combo.addItem('Quota snapshots','quota')
        self.metric_combo.setAccessibleName('History chart metric')
        self.quota_window=QComboBox(); self.quota_window.setAccessibleName('History quota window'); self.quota_window.setEnabled(False)
        metrics.addWidget(self.metric_combo,1); metrics.addWidget(self.quota_window,1); layout.addLayout(metrics)
        self.metric_combo.currentIndexChanged.connect(self._chart)
        self.quota_window.currentIndexChanged.connect(self._chart)
        self.summary=QLabel('Enable local numeric history in Host settings, save settings and start the host.')
        self.summary.setWordWrap(True); self.summary.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.summary)
        self.chart=HistoryChart(); layout.addWidget(self.chart)
        self.details=QPlainTextEdit(); self.details.setReadOnly(True)
        self.details.setAccessibleName('Quota observations and estimated consumption pace')
        layout.addWidget(self.details,1)
        notice=QLabel('Local history stores only observed token increases and numeric quota snapshots for up to 30 days. '
                     'The quota view/export contains the latest 256 observations per AI. '
                     'Missing periods are not zero usage. Predictions are estimates, not provider promises or billing.')
        notice.setWordWrap(True); notice.setTextFormat(Qt.TextFormat.PlainText); layout.addWidget(notice)
        self.refresh_button.clicked.connect(self.refresh)
        self.export_button.clicked.connect(self.export)
        self.provider.currentIndexChanged.connect(self.refresh)
        self.period.currentIndexChanged.connect(self.refresh)
        self.export_button.setEnabled(False)

    def refresh(self,*unused):
        if self.owner.closed: return
        self.generation+=1
        self.data=None; self.chart.set_rows([]); self.details.clear()
        self.export_button.setEnabled(False)
        if self.worker is not None: return
        from desktop_window import ReadWorker
        from usage_history import read_history
        key=self.provider.currentData(); days=self.period.currentData(); generation=self.generation
        if key not in PROVIDERS:
            self.summary.setText('Choose an AI to inspect its local numeric history.'); return
        root=self.owner.root
        self.refresh_button.setEnabled(False); self.export_button.setEnabled(False)
        def read():
            try: data=read_history(root/'tools/activity',[key],days)
            except Exception: data=None
            return generation,key,data
        self.worker=ReadWorker(read)
        self.worker.signals.finished.connect(self._finished,Qt.ConnectionType.QueuedConnection)
        self.owner.status_pool.start(self.worker)

    def _finished(self,result):
        self.worker=None
        if self.owner.closed: return
        self.refresh_button.setEnabled(True)
        if result is None:
            self.summary.setText('History could not be read. Existing data was preserved.'); return
        generation,key,data=result
        if generation!=self.generation:
            QTimer.singleShot(0,self.refresh); return
        if data is None:
            self.summary.setText('History could not be read. Existing data was preserved.'); return
        self.data=data
        rows=data['tokens']
        with QSignalBlocker(self.quota_window):
            selection=self.quota_window.currentData()
            selected=tuple(selection) if selection is not None else None
            self.quota_window.clear()
            windows=sorted({(r['window'],r['kind']) for r in data['quota']})
            for window,kind in windows:
                self.quota_window.addItem((f'{window/60:g} hours' if window else 'Provider window')+' / '+kind,(window,kind))
            if selected in windows: self.quota_window.setCurrentIndex(self.quota_window.findData(selected))
        self._chart()
        total=sum(r['total'] for r in rows)
        collection='Collection is off; saved history remains local.'
        if self.owner.config.get('usage_history'):
            health=self.owner.cached_health or {}
            current=(health.get('board')==self.owner.config.get('board') and
                     self.owner.config['port'] in ('auto',health.get('port')) and
                     0<=time.time()-health.get('updated_at',0)<=45)
            status=health.get('history',{}) if current else {}
            collection=(status.get('error') or 'Host collection is running.') if status.get('enabled') else 'Collection requested; start the host and check its status.'
        self.summary.setText(data['error'] or f'{PROVIDERS[key][0]}: {total:,} observed token increases in this period. '+collection)
        latest={}
        for sample in data['quota']:
            key=(sample['window'],sample['kind'])
            if key not in latest or sample['minute']>latest[key]['minute']: latest[key]=sample
        captions=[]
        for (window,kind),sample in latest.items():
            caption=f'{window/60:g} hours' if window else 'provider window'
            if kind=='tools': caption+=' / MCP tool calls'
            observed=datetime.fromtimestamp(sample['minute']*60,timezone.utc).strftime('%d %b %H:%M UTC')
            captions.append(f'{caption}: {sample["used"]:g}% used; observed {observed}')
        for forecast in data['forecasts']:
            reset=datetime.fromtimestamp(forecast['reset'],timezone.utc).strftime('%d %b %H:%M UTC')
            outcome=(f'{forecast["estimated_hours_to_limit"]:.1f} hours to limit before reset if this pace continues.'
                     if forecast['estimated_hours_to_limit'] is not None else 'This window resets before its limit at this pace.')
            captions.append(f'ESTIMATE / {forecast["window"]/60:g}h {forecast["kind"]}: '
                f'{forecast["percent_per_hour"]:.2f} percentage points/hour; '+outcome+' Reset: '+reset)
        if not data['forecasts']: captions.append('No reliable pace estimate yet: needs fresh increasing samples in the same reset window.')
        self.details.setPlainText('\n'.join(captions))
        self.export_button.setEnabled(bool(data['tokens'] or data['quota']))

    def _chart(self,*unused):
        quota=self.metric_combo.currentData()=='quota'
        self.quota_window.setEnabled(quota and self.quota_window.count()>0)
        if self.data is None:
            if quota: self.chart.set_quota([])
            else: self.chart.set_rows([])
            return
        if quota:
            selection=self.quota_window.currentData()
            self.chart.set_quota([r for r in self.data['quota'] if selection and (r['window'],r['kind'])==tuple(selection)])
        else: self.chart.set_rows(self.data['tokens'])

    def export(self):
        if not self.data: return
        data=self.data
        path,_=QFileDialog.getSaveFileName(self,'Export local numeric history','ai-monitor-history.csv','CSV files (*.csv)')
        if not path: return
        try:
            with Path(path).open('w',newline='',encoding='utf-8') as stream:
                writer=csv.writer(stream)
                writer.writerow(['metric','provider','observed_utc','value','window_minutes','kind','reset_epoch'])
                for row in data['tokens']:
                    day=datetime.fromtimestamp(row['day']*86400,timezone.utc).strftime('%Y-%m-%d')
                    writer.writerow(['observed_tokens',row['provider'],day,row['total'],'','',''])
                for row in data['quota']:
                    stamp=datetime.fromtimestamp(row['minute']*60,timezone.utc).isoformat()
                    writer.writerow(['quota_used_percent',row['provider'],stamp,row['used'],row['window'],row['kind'],row['reset']])
            self.summary.setText('Numeric history exported. No prompts, account identifiers or credentials were included.')
        except OSError: self.summary.setText('Export failed. Choose a writable local CSV file.')
