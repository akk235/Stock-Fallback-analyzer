import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import queue
import os
import json
import time
from datetime import datetime
import requests
import pandas as pd
import numpy as np
import yfinance as yf
import websocket
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.dates import date2num, DateFormatter, AutoDateLocator
import matplotlib

matplotlib.use('TkAgg')


class StockRealtimePromptApp:
    def __init__(self, root):
        self.root = root
        self.root.title("股票分析器 Pro AI - Real-time Prompt Mode")
        self.root.geometry("1720x1140")
        self.root.configure(bg="#0f172a")

        self.colors = {
            'bg': '#0f172a',
            'panel': '#111827',
            'panel2': '#1f2937',
            'accent': '#2563eb',
            'text': '#38bdf8',
            'white': '#f8fafc',
            'muted': '#94a3b8',
            'bull': '#22c55e',
            'bear': '#ef4444',
            'neutral': '#f59e0b',
            'purple': '#a78bfa'
        }

        self.symbol_var = tk.StringVar(value='AAPL')
        self.period_var = tk.StringVar(value='5d')
        self.interval_var = tk.StringVar(value='10分鐘圖')
        self.status_var = tk.StringVar(value='輸入股票代號，然後按「啟動即時模式」')
        self.signal_var = tk.StringVar(value='訊號：等待中')
        self.market_var = tk.StringVar(value='市場狀態：N/A')
        self.data_source_var = tk.StringVar(value='資料來源：N/A')
        self.ws_var = tk.StringVar(value='實時連線：未連接')
        self.ai_mode_var = tk.StringVar(value='內建AI')
        self.live_mode_var = tk.StringVar(value='提示模式')
        self.refresh_var = tk.StringVar(value='輪詢:15秒')
        self.volume_ratio_var = tk.StringVar(value='成交量高度：標準')
        self.intraday_span_var = tk.StringVar(value='顯示根數：90')

        self.df = pd.DataFrame()
        self.info = {}
        self.news_items = []
        self.signal_result = {}
        self.trade_marks = []
        self.tick_queue = queue.Queue()
        self.ws_app = None
        self.ws_thread = None
        self.live_running = False
        self.poll_job = None
        self.ui_job = None
        self.current_symbol = ''
        self.last_price = None
        self.last_tick_time = None
        self.current_interval = '10m'

        self.create_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def create_ui(self):
        container = tk.Frame(self.root, bg=self.colors['bg'])
        container.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(container, bg=self.colors['bg'], highlightthickness=0)
        self.canvas.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(container, orient='vertical', command=self.canvas.yview)
        scrollbar.pack(side='right', fill='y')
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.main_frame = tk.Frame(self.canvas, bg=self.colors['bg'])
        self.canvas_window = self.canvas.create_window((0, 0), window=self.main_frame, anchor='nw')
        self.main_frame.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))
        self.canvas.bind_all('<MouseWheel>', lambda e: self.canvas.yview_scroll(int(-1 * (e.delta / 120)), 'units'))

        header = tk.Frame(self.main_frame, bg=self.colors['panel'], pady=14)
        header.pack(fill='x', padx=12, pady=(10, 6))
        tk.Label(header, text='股票分析器 Pro AI - Real-time Prompt Mode', fg=self.colors['text'], bg=self.colors['panel'], font=('Arial', 24, 'bold')).pack(anchor='w')
        tk.Label(header, text='A模式：實時決策提示，不自動落單', fg=self.colors['white'], bg=self.colors['panel'], font=('Arial', 11)).pack(anchor='w', pady=(4, 0))

        ctrl = tk.Frame(self.main_frame, bg=self.colors['panel'])
        ctrl.pack(fill='x', padx=12, pady=6)
        tk.Label(ctrl, text='股票代號', fg=self.colors['white'], bg=self.colors['panel']).grid(row=0, column=0, padx=5, pady=8)
        tk.Entry(ctrl, textvariable=self.symbol_var, width=14, font=('Arial', 11), bg=self.colors['panel2'], fg=self.colors['white'], insertbackground=self.colors['white']).grid(row=0, column=1, padx=5)
        tk.Label(ctrl, text='時間範圍', fg=self.colors['white'], bg=self.colors['panel']).grid(row=0, column=2, padx=5)
        ttk.Combobox(ctrl, textvariable=self.period_var, values=['5d', '1mo'], width=8, state='readonly').grid(row=0, column=3, padx=5)
        tk.Label(ctrl, text='圖表級別', fg=self.colors['white'], bg=self.colors['panel']).grid(row=0, column=4, padx=5)
        ttk.Combobox(ctrl, textvariable=self.interval_var, values=['10分鐘圖', '日圖'], width=10, state='readonly').grid(row=0, column=5, padx=5)
        tk.Button(ctrl, text='啟動即時模式', command=self.start_live_mode, width=14, font=('Arial', 10, 'bold'), bg=self.colors['accent'], fg='white', relief='flat').grid(row=0, column=6, padx=8)
        tk.Button(ctrl, text='停止', command=self.stop_live_mode, width=10, font=('Arial', 10, 'bold'), bg='#475569', fg='white', relief='flat').grid(row=0, column=7, padx=8)
        tk.Button(ctrl, text='AI 決策', command=self.manual_ai_refresh, width=10, font=('Arial', 10, 'bold'), bg=self.colors['purple'], fg='white', relief='flat').grid(row=0, column=8, padx=8)
        tk.Button(ctrl, text='刷新新聞', command=self.refresh_news_only, width=10, font=('Arial', 10, 'bold'), bg='#0ea5e9', fg='white', relief='flat').grid(row=0, column=9, padx=8)

        tk.Label(ctrl, text='更新', fg=self.colors['white'], bg=self.colors['panel']).grid(row=1, column=0, padx=5, pady=8)
        ttk.Combobox(ctrl, textvariable=self.refresh_var, values=['輪詢:15秒', '輪詢:30秒', '輪詢:60秒'], width=12, state='readonly').grid(row=1, column=1, padx=5)
        tk.Label(ctrl, text='AI模式', fg=self.colors['white'], bg=self.colors['panel']).grid(row=1, column=2, padx=5)
        ttk.Combobox(ctrl, textvariable=self.ai_mode_var, values=['內建AI', 'OpenAI API'], width=12, state='readonly').grid(row=1, column=3, padx=5)
        tk.Label(ctrl, text='成交量高度', fg=self.colors['white'], bg=self.colors['panel']).grid(row=1, column=4, padx=5)
        vol_combo = ttk.Combobox(ctrl, textvariable=self.volume_ratio_var, values=['成交量高度：細', '成交量高度：標準', '成交量高度：大'], width=12, state='readonly')
        vol_combo.grid(row=1, column=5, padx=5)
        vol_combo.bind('<<ComboboxSelected>>', lambda e: self.redraw_chart_only())
        tk.Label(ctrl, text='10分鐘根數', fg=self.colors['white'], bg=self.colors['panel']).grid(row=1, column=6, padx=5)
        span_combo = ttk.Combobox(ctrl, textvariable=self.intraday_span_var, values=['顯示根數：60', '顯示根數：90', '顯示根數：120'], width=12, state='readonly')
        span_combo.grid(row=1, column=7, padx=5)
        span_combo.bind('<<ComboboxSelected>>', lambda e: self.redraw_chart_only())
        tk.Label(ctrl, textvariable=self.status_var, fg=self.colors['neutral'], bg=self.colors['panel'], font=('Arial', 10)).grid(row=1, column=8, columnspan=6, sticky='w', padx=10)

        signal_bar = tk.Frame(self.main_frame, bg=self.colors['panel2'])
        signal_bar.pack(fill='x', padx=12, pady=6)
        tk.Label(signal_bar, textvariable=self.signal_var, fg=self.colors['white'], bg=self.colors['panel2'], font=('Arial', 12, 'bold')).pack(side='left', padx=12, pady=8)
        tk.Label(signal_bar, textvariable=self.market_var, fg=self.colors['muted'], bg=self.colors['panel2'], font=('Arial', 11)).pack(side='left', padx=18)
        tk.Label(signal_bar, textvariable=self.data_source_var, fg=self.colors['muted'], bg=self.colors['panel2'], font=('Arial', 11)).pack(side='left', padx=18)
        tk.Label(signal_bar, textvariable=self.ws_var, fg=self.colors['muted'], bg=self.colors['panel2'], font=('Arial', 11)).pack(side='left', padx=18)

        chart_frame = tk.Frame(self.main_frame, bg=self.colors['panel'], bd=1, relief='solid', height=470)
        chart_frame.pack(fill='x', padx=12, pady=6)
        chart_frame.pack_propagate(False)
        tk.Label(chart_frame, text='K 線圖 + 即時決策提示 + 成交量 + EMA/VWAP', fg=self.colors['white'], bg=self.colors['panel'], font=('Arial', 12, 'bold')).pack(fill='x', pady=6)
        self.chart_area = tk.Frame(chart_frame, bg=self.colors['bg'])
        self.chart_area.pack(fill='both', expand=True, padx=8, pady=8)

        metrics_wrap = tk.Frame(self.main_frame, bg=self.colors['bg'])
        metrics_wrap.pack(fill='x', padx=12, pady=6)
        left_metrics = tk.Frame(metrics_wrap, bg=self.colors['panel'])
        left_metrics.pack(side='left', fill='x', expand=True, padx=(0, 6))
        right_metrics = tk.Frame(metrics_wrap, bg=self.colors['panel'])
        right_metrics.pack(side='left', fill='x', expand=True, padx=(6, 0))
        tk.Label(left_metrics, text='核心指標', fg=self.colors['white'], bg=self.colors['panel'], font=('Arial', 11, 'bold')).pack(fill='x', pady=5)
        tk.Label(right_metrics, text='決策提示', fg=self.colors['white'], bg=self.colors['panel'], font=('Arial', 11, 'bold')).pack(fill='x', pady=5)
        self.card_grid_top = tk.Frame(left_metrics, bg=self.colors['panel'])
        self.card_grid_top.pack(fill='x', padx=6, pady=(0, 6))
        self.card_grid_bottom = tk.Frame(right_metrics, bg=self.colors['panel'])
        self.card_grid_bottom.pack(fill='x', padx=6, pady=(0, 6))

        self.cards = {}
        top_cards = [('現價', 'price'), ('EMA9', 'ema9'), ('EMA20', 'ema20'), ('VWAP', 'vwap'), ('RSI', 'rsi'), ('MACD', 'macd'), ('ADX', 'adx'), ('量比', 'vr')]
        bottom_cards = [('Bias', 'bias'), ('Setup', 'setup'), ('Entry', 'entry'), ('Stop', 'stop'), ('Target', 'target'), ('RR', 'rr'), ('信心', 'confidence'), ('狀態', 'state')]
        self._build_cards(self.card_grid_top, top_cards)
        self._build_cards(self.card_grid_bottom, bottom_cards)

        notebook_wrap = tk.Frame(self.main_frame, bg=self.colors['bg'])
        notebook_wrap.pack(fill='both', expand=True, padx=12, pady=(4, 12))
        notebook = ttk.Notebook(notebook_wrap)
        notebook.pack(fill='both', expand=True)
        tab_strategy = tk.Frame(notebook, bg=self.colors['panel'])
        tab_ai = tk.Frame(notebook, bg=self.colors['panel'])
        tab_news = tk.Frame(notebook, bg=self.colors['panel'])
        tab_log = tk.Frame(notebook, bg=self.colors['panel'])
        notebook.add(tab_strategy, text='策略分析')
        notebook.add(tab_ai, text='AI 決策')
        notebook.add(tab_news, text='新聞')
        notebook.add(tab_log, text='實時日誌')
        self.result = scrolledtext.ScrolledText(tab_strategy, wrap='word', bg=self.colors['bg'], fg=self.colors['white'], insertbackground=self.colors['white'], font=('Consolas', 10), padx=14, pady=14)
        self.result.pack(fill='both', expand=True, padx=8, pady=8)
        self.ai_box = scrolledtext.ScrolledText(tab_ai, wrap='word', bg=self.colors['bg'], fg=self.colors['white'], insertbackground=self.colors['white'], font=('Consolas', 10), padx=14, pady=14)
        self.ai_box.pack(fill='both', expand=True, padx=8, pady=8)
        self.news_box = scrolledtext.ScrolledText(tab_news, wrap='word', bg=self.colors['bg'], fg=self.colors['white'], insertbackground=self.colors['white'], font=('Arial', 10), padx=14, pady=14)
        self.news_box.pack(fill='both', expand=True, padx=8, pady=8)
        self.log_box = scrolledtext.ScrolledText(tab_log, wrap='word', bg=self.colors['bg'], fg=self.colors['white'], insertbackground=self.colors['white'], font=('Consolas', 10), padx=14, pady=14)
        self.log_box.pack(fill='both', expand=True, padx=8, pady=8)

    def _build_cards(self, parent, card_names):
        for i, (name, key) in enumerate(card_names):
            card = tk.Frame(parent, bg=self.colors['panel2'], width=110, height=72, bd=1, relief='solid')
            card.grid(row=0, column=i, padx=4, pady=4)
            card.pack_propagate(False)
            tk.Label(card, text=name, fg=self.colors['muted'], bg=self.colors['panel2'], font=('Arial', 9)).pack(pady=(8, 2))
            val = tk.Label(card, text='N/A', fg=self.colors['white'], bg=self.colors['panel2'], font=('Arial', 10, 'bold'))
            val.pack(pady=(2, 8))
            self.cards[key] = val

    def log(self, text):
        stamp = datetime.now().strftime('%H:%M:%S')
        self.log_box.insert(tk.END, f'[{stamp}] {text}\n')
        self.log_box.see(tk.END)

    def normalize_symbol(self, symbol):
        symbol = (symbol or '').strip().upper().replace(' ', '')
        if symbol.isdigit() and 1 <= len(symbol) <= 5:
            return symbol.zfill(4) + '.HK'
        return symbol

    def finnhub_symbol(self, symbol):
        if symbol.endswith('.HK') and symbol[:-3].isdigit():
            return symbol[:-3].lstrip('0') + '.HK'
        return symbol

    def get_poll_ms(self):
        text = self.refresh_var.get()
        if '30秒' in text:
            return 30000
        if '60秒' in text:
            return 60000
        return 15000

    def start_live_mode(self):
        self.stop_live_mode(silent=True)
        symbol = self.normalize_symbol(self.symbol_var.get())
        self.symbol_var.set(symbol)
        if not symbol:
            messagebox.showerror('錯誤', '請輸入股票代號')
            return
        self.current_symbol = symbol
        self.live_running = True
        self.status_var.set('啟動中...')
        self.current_interval = '10m' if self.interval_var.get() == '10分鐘圖' else '1d'
        self.log(f'啟動即時模式：{symbol}')
        self.initial_load()
        self.start_websocket()
        self.schedule_polling()
        self.schedule_queue_drain()

    def stop_live_mode(self, silent=False):
        self.live_running = False
        if self.poll_job:
            self.root.after_cancel(self.poll_job)
            self.poll_job = None
        if self.ui_job:
            self.root.after_cancel(self.ui_job)
            self.ui_job = None
        if self.ws_app:
            try:
                self.ws_app.close()
            except Exception:
                pass
        self.ws_app = None
        self.ws_thread = None
        self.ws_var.set('實時連線：未連接')
        if not silent:
            self.status_var.set('已停止')
            self.log('已停止即時模式')

    def initial_load(self):
        def worker():
            try:
                used_symbol, df, info, source = self.get_history_with_fallback(self.current_symbol, self.period_var.get(), self.current_interval)
                self.df = self.calculate_indicators(df.copy())
                self.info = info
                self.news_items = self.fetch_news(used_symbol, info)
                self.signal_result = self.generate_trade_setup(self.df, info, self.news_items)
                self.trade_marks = self.generate_trade_marks(self.df)
                ai_text = self.generate_ai_decision(self.df, self.signal_result, self.info, self.news_items)
                self.root.after(0, lambda: self.finish_ui_update(source, ai_text, '初始載入完成'))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror('錯誤', str(e)))
                self.root.after(0, lambda: self.status_var.set('初始載入失敗'))
        threading.Thread(target=worker, daemon=True).start()

    def schedule_polling(self):
        if not self.live_running:
            return
        self.poll_job = self.root.after(self.get_poll_ms(), self.poll_refresh)

    def poll_refresh(self):
        if not self.live_running:
            return
        def worker():
            try:
                _, df, info, source = self.get_history_with_fallback(self.current_symbol, self.period_var.get(), self.current_interval)
                self.df = self.calculate_indicators(df.copy())
                self.info = info or self.info
                self.signal_result = self.generate_trade_setup(self.df, self.info, self.news_items)
                self.trade_marks = self.generate_trade_marks(self.df)
                ai_text = self.generate_ai_decision(self.df, self.signal_result, self.info, self.news_items)
                self.root.after(0, lambda: self.finish_ui_update(source, ai_text, '輪詢更新完成'))
            except Exception as e:
                self.root.after(0, lambda: self.log(f'輪詢更新失敗：{e}'))
            finally:
                self.root.after(0, self.schedule_polling)
        threading.Thread(target=worker, daemon=True).start()

    def schedule_queue_drain(self):
        if not self.live_running:
            return
        self.drain_tick_queue()
        self.ui_job = self.root.after(1000, self.schedule_queue_drain)

    def drain_tick_queue(self):
        changed = False
        while not self.tick_queue.empty():
            tick = self.tick_queue.get()
            price = tick.get('price')
            ts = tick.get('ts')
            if price:
                self.last_price = price
                self.last_tick_time = ts
                changed = True
        if changed and self.df is not None and not self.df.empty:
            self.update_last_bar_from_tick(self.last_price)
            self.signal_result = self.generate_trade_setup(self.df, self.info, self.news_items)
            self.trade_marks = self.generate_trade_marks(self.df)
            ai_text = self.generate_ai_decision(self.df, self.signal_result, self.info, self.news_items)
            self.finish_ui_update(self.data_source_var.get().replace('資料來源：', '') or 'WebSocket', ai_text, '即時 tick 更新')

    def update_last_bar_from_tick(self, price):
        if self.df.empty:
            return
        idx = self.df.index[-1]
        self.df.at[idx, 'Close'] = price
        self.df.at[idx, 'High'] = max(float(self.df.at[idx, 'High']), float(price))
        self.df.at[idx, 'Low'] = min(float(self.df.at[idx, 'Low']), float(price))
        self.df = self.calculate_indicators(self.df[['Open', 'High', 'Low', 'Close', 'Volume']].copy())

    def start_websocket(self):
        token = os.getenv('FINNHUB_API_KEY', '').strip()
        if not token:
            self.ws_var.set('實時連線：未設 FINNHUB_API_KEY，改用輪詢')
            self.log('未設 FINNHUB_API_KEY，使用輪詢模式')
            return
        symbol = self.finnhub_symbol(self.current_symbol)

        def on_message(ws, message):
            try:
                data = json.loads(message)
                if data.get('type') == 'trade':
                    for item in data.get('data', []):
                        p = item.get('p')
                        t = item.get('t')
                        if p:
                            self.tick_queue.put({'price': float(p), 'ts': t})
            except Exception:
                pass

        def on_open(ws):
            self.ws_var.set('實時連線：已連接')
            self.log(f'WebSocket 已連接：{symbol}')
            ws.send(json.dumps({'type': 'subscribe', 'symbol': symbol}))

        def on_error(ws, error):
            self.ws_var.set('實時連線：錯誤，改用輪詢')
            self.log(f'WebSocket 錯誤：{error}')

        def on_close(ws, code, msg):
            self.ws_var.set('實時連線：已關閉')
            self.log('WebSocket 已關閉')

        self.ws_app = websocket.WebSocketApp(
            f'wss://ws.finnhub.io?token={token}',
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        self.ws_thread = threading.Thread(target=self.ws_app.run_forever, daemon=True)
        self.ws_thread.start()

    def get_history_with_fallback(self, symbol, period, interval):
        candidates = [symbol]
        if symbol.endswith('.HK') and symbol[:-3].isdigit():
            digits = symbol[:-3].zfill(4)
            candidates.extend([digits, digits.lstrip('0')])
        elif symbol.isdigit() and 1 <= len(symbol) <= 5:
            digits = symbol.zfill(4)
            candidates.extend([digits + '.HK', digits])

        if interval == '10m':
            interval_candidates = [('10m', period), ('5m', period), ('15m', period), ('30m', period), ('60m', '1mo')]
        else:
            interval_candidates = [('1d', period)]

        for sym in dict.fromkeys([c for c in candidates if c]):
            for yf_interval, yf_period in interval_candidates:
                for ap in [False, True]:
                    try:
                        stock = yf.Ticker(sym)
                        df = stock.history(period=yf_period, interval=yf_interval, auto_adjust=ap, prepost=False)
                        info = {}
                        try:
                            info = stock.info or {}
                        except Exception:
                            pass
                        if df is not None and not df.empty:
                            df = self.normalize_history_df(df)
                            return sym, df, info, f'Yahoo Finance {yf_interval}'
                    except Exception:
                        pass
        raise ValueError('搵唔到價格資料，請檢查代號')

    def normalize_history_df(self, df):
        df = df.copy()
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.set_index('Date')
        else:
            df.index = pd.to_datetime(df.index)
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if col not in df.columns:
                df[col] = np.nan if col != 'Volume' else 0
        return df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna(subset=['Close']).sort_index()

    def calculate_indicators(self, df):
        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']
        df['EMA9'] = close.ewm(span=9, adjust=False).mean()
        df['EMA20'] = close.ewm(span=20, adjust=False).mean()
        df['EMA50'] = close.ewm(span=50, adjust=False).mean()
        df['EMA12'] = close.ewm(span=12, adjust=False).mean()
        df['EMA26'] = close.ewm(span=26, adjust=False).mean()
        df['MACD'] = df['EMA12'] - df['EMA26']
        df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        delta = close.diff()
        up = delta.clip(lower=0)
        down = -delta.clip(upper=0)
        roll_up = up.ewm(com=13, adjust=False).mean()
        roll_down = down.ewm(com=13, adjust=False).mean()
        rs = roll_up / roll_down.replace(0, np.nan)
        df['RSI'] = 100 - (100 / (1 + rs))
        high_low = high - low
        high_close = (high - close.shift()).abs()
        low_close = (low - close.shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['ATR'] = tr.rolling(14).mean()
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
        atr14 = tr.rolling(14).mean()
        plus_di = 100 * (plus_dm.rolling(14).sum() / atr14.replace(0, np.nan))
        minus_di = 100 * (minus_dm.rolling(14).sum() / atr14.replace(0, np.nan))
        dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
        df['ADX'] = dx.rolling(14).mean()
        typical = (high + low + close) / 3
        df['VWAP'] = (typical * volume).cumsum() / volume.cumsum().replace(0, np.nan)
        df['Volume_MA20'] = volume.rolling(20).mean()
        df['Volume_Ratio'] = volume / df['Volume_MA20'].replace(0, np.nan)
        return df

    def classify_market_state(self, last):
        if pd.notna(last['ADX']) and last['ADX'] >= 25:
            if last['Close'] > last['EMA20'] > last['EMA50']:
                return 'Trend Up'
            if last['Close'] < last['EMA20'] < last['EMA50']:
                return 'Trend Down'
        return 'Range'

    def generate_trade_setup(self, df, info, news_items):
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last
        news_score = sum(x.get('sentiment_score', 0) for x in news_items)
        market_state = self.classify_market_state(last)
        long_points, short_points = 0, 0
        reasons = []
        setup_name = 'NO TRADE'
        bias = 'NEUTRAL'

        if last['Close'] > last['EMA9'] > last['EMA20'] > last['EMA50']:
            long_points += 3
            reasons.append('多頭 EMA 排列')
        elif last['Close'] < last['EMA9'] < last['EMA20'] < last['EMA50']:
            short_points += 3
            reasons.append('空頭 EMA 排列')
        if pd.notna(last['VWAP']):
            if last['Close'] > last['VWAP']:
                long_points += 1
                reasons.append('價格高於 VWAP')
            else:
                short_points += 1
                reasons.append('價格低於 VWAP')
        if pd.notna(last['RSI']):
            if 52 <= last['RSI'] <= 68:
                long_points += 1
                reasons.append('RSI 偏強')
            elif 32 <= last['RSI'] <= 48:
                short_points += 1
                reasons.append('RSI 偏弱')
            elif last['RSI'] > 75:
                reasons.append('RSI 過熱')
            elif last['RSI'] < 25:
                reasons.append('RSI 過低')
        if last['MACD'] > last['MACD_signal']:
            long_points += 1
            reasons.append('MACD 在上方')
        else:
            short_points += 1
            reasons.append('MACD 在下方')

        vol_ratio = float(last['Volume_Ratio']) if pd.notna(last['Volume_Ratio']) else 1.0
        if vol_ratio >= 1.2 and last['Close'] > prev['Close']:
            long_points += 1
            reasons.append('價升量增')
        elif vol_ratio >= 1.2 and last['Close'] < prev['Close']:
            short_points += 1
            reasons.append('價跌量增')

        atr = float(last['ATR']) if pd.notna(last['ATR']) and last['ATR'] > 0 else max(float(last['Close']) * 0.01, 0.01)
        breakout_high = float(df['High'].tail(10).iloc[:-1].max()) if len(df) > 10 else float(df['High'].max())
        breakdown_low = float(df['Low'].tail(10).iloc[:-1].min()) if len(df) > 10 else float(df['Low'].min())

        if last['Close'] > breakout_high and vol_ratio >= 1.2:
            long_points += 2
            setup_name = 'BUY READY'
            reasons.append('突破近10根高位')
        elif abs(last['Close'] - last['EMA20']) <= atr * 0.35 and last['Close'] > last['EMA20'] and market_state == 'Trend Up':
            long_points += 2
            setup_name = 'BUY READY'
            reasons.append('回踩 EMA20 成功')

        if last['Close'] < breakdown_low and vol_ratio >= 1.2:
            short_points += 2
            setup_name = 'SELL READY'
            reasons.append('跌穿近10根低位')
        elif abs(last['Close'] - last['EMA20']) <= atr * 0.35 and last['Close'] < last['EMA20'] and market_state == 'Trend Down':
            short_points += 2
            setup_name = 'SELL READY'
            reasons.append('反彈至 EMA20 受阻')

        if news_score >= 2:
            long_points += 1
            reasons.append('新聞偏正面')
        elif news_score <= -2:
            short_points += 1
            reasons.append('新聞偏負面')

        if long_points >= short_points + 2 and long_points >= 6:
            bias = 'BULLISH'
            entry = max(float(last['Close']), breakout_high if setup_name == 'BUY READY' else float(last['Close']))
            stop = entry - max(atr * 1.2, entry * 0.008)
            target = entry + (entry - stop) * 1.8
            setup_name = 'BUY READY'
        elif short_points >= long_points + 2 and short_points >= 6:
            bias = 'BEARISH'
            entry = min(float(last['Close']), breakdown_low if setup_name == 'SELL READY' else float(last['Close']))
            stop = entry + max(atr * 1.2, entry * 0.008)
            target = entry - (stop - entry) * 1.8
            setup_name = 'SELL READY'
        else:
            bias = 'NEUTRAL'
            setup_name = 'NO TRADE'
            entry = float(last['Close'])
            stop = entry - atr
            target = entry + atr
            reasons.append('條件未夠集中')

        rr = abs((target - entry) / (entry - stop)) if entry != stop else 0
        confidence = min(92, 45 + max(long_points, short_points) * 6)
        if bias == 'NEUTRAL':
            confidence = min(confidence, 58)
        return {
            'bias': bias,
            'setup': setup_name,
            'entry': round(entry, 2),
            'stop': round(stop, 2),
            'target': round(target, 2),
            'rr': round(rr, 2),
            'confidence': int(confidence),
            'market_state': market_state,
            'news_score': int(news_score),
            'reasons': reasons[:10],
            'price': round(float(last['Close']), 2),
            'vol_ratio': round(vol_ratio, 2)
        }

    def generate_trade_marks(self, df):
        marks = []
        if len(df) < 15:
            return marks
        for i in range(3, len(df)):
            close = df['Close'].iloc[i]
            ema9 = df['EMA9'].iloc[i]
            ema20 = df['EMA20'].iloc[i]
            macd = df['MACD'].iloc[i]
            macd_sig = df['MACD_signal'].iloc[i]
            vr = df['Volume_Ratio'].iloc[i] if pd.notna(df['Volume_Ratio'].iloc[i]) else 1.0
            if close > ema9 > ema20 and macd > macd_sig and vr >= 1.2:
                marks.append({'idx': i, 'type': 'buy', 'price': float(close)})
            elif close < ema9 < ema20 and macd < macd_sig and vr >= 1.2:
                marks.append({'idx': i, 'type': 'sell', 'price': float(close)})
        return marks[-25:]

    def fetch_news(self, symbol, info):
        queries = [symbol]
        short = info.get('shortName') or info.get('longName') or info.get('name')
        if short:
            queries.append(short)
        headers = {'User-Agent': 'Mozilla/5.0'}
        items, seen = [], set()
        for q in queries[:2]:
            url = f"https://news.google.com/rss/search?q={requests.utils.quote(q + ' stock')}&hl=en-US&gl=US&ceid=US:en"
            try:
                r = requests.get(url, headers=headers, timeout=10)
                text = r.text
                parts = text.split('<item>')[1:7]
                for p in parts:
                    title = self._extract_between(p, '<title>', '</title>').replace('&amp;', '&')
                    link = self._extract_between(p, '<link>', '</link>')
                    pub = self._extract_between(p, '<pubDate>', '</pubDate>')
                    if title and title not in seen:
                        seen.add(title)
                        items.append({'title': title, 'link': link, 'pubDate': pub})
            except Exception:
                pass
            if len(items) >= 8:
                break
        for item in items:
            item['sentiment_score'] = self.score_news_title(item['title'])
        return items[:8]

    def _extract_between(self, text, start, end):
        try:
            s = text.index(start) + len(start)
            e = text.index(end, s)
            return text[s:e].strip()
        except ValueError:
            return ''

    def score_news_title(self, title):
        t = title.lower()
        positive = ['beat', 'surge', 'growth', 'record', 'strong', 'upgrade', 'profit', 'bullish', 'gain', 'rally', 'buyback', 'partnership', 'expands']
        negative = ['miss', 'drop', 'fall', 'lawsuit', 'probe', 'cut', 'downgrade', 'loss', 'bearish', 'decline', 'weak', 'warning', 'slump']
        score = 0
        for w in positive:
            if w in t:
                score += 1
        for w in negative:
            if w in t:
                score -= 1
        return score

    def generate_builtin_ai_text(self, df, setup, news_items):
        last = df.iloc[-1]
        text = []
        text.append('================ AI 即時決策 ================')
        text.append(f"時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        text.append(f"訊號：{setup['setup']}")
        text.append(f"Bias：{setup['bias']}")
        text.append(f"市場狀態：{setup['market_state']}")
        text.append(f"現價：{setup['price']} | Entry：{setup['entry']} | Stop：{setup['stop']} | Target：{setup['target']} | RR：{setup['rr']}")
        text.append(f"RSI：{last['RSI']:.2f} | MACD：{last['MACD']:.2f} | ADX：{last['ADX']:.2f} | 量比：{setup['vol_ratio']}")
        text.append('')
        text.append('【判讀】')
        if setup['setup'] == 'BUY READY':
            text.append('目前條件接近或已經符合做多 setup，但只屬提示，不代表保證升。')
        elif setup['setup'] == 'SELL READY':
            text.append('目前條件接近或已經符合做淡 / 減倉 setup，但只屬提示，不代表一定跌。')
        else:
            text.append('目前未見高質素 setup，最合理仍然係觀望。')
        text.append('')
        text.append('【原因】')
        for i, reason in enumerate(setup['reasons'], 1):
            text.append(f'{i}. {reason}')
        text.append('')
        text.append('【風險】')
        if setup['rr'] < 1.5:
            text.append('- RR 偏低。')
        if setup['market_state'] == 'Range':
            text.append('- 市場處於震盪，假突破風險較高。')
        if pd.notna(last['RSI']) and last['RSI'] > 72:
            text.append('- RSI 過熱，唔適宜太激進追價。')
        if pd.notna(last['RSI']) and last['RSI'] < 28:
            text.append('- RSI 過低，小心先反抽再落。')
        if setup['news_score'] <= -2:
            text.append('- 新聞偏負面，波動可能突然加劇。')
        return '\n'.join(text)

    def call_openai_ai(self, payload):
        api_key = os.getenv('OPENAI_API_KEY', '').strip()
        if not api_key:
            return None
        try:
            body = {
                'model': 'gpt-4o-mini',
                'messages': [
                    {'role': 'system', 'content': '你係審慎嘅短線交易輔助 AI，只可基於提供數據做提示，不可聲稱保證準確。'},
                    {'role': 'user', 'content': '請用繁體中文簡短分析呢個即時 setup，輸出：訊號、理由、風險、失效條件。\n' + json.dumps(payload, ensure_ascii=False)}
                ],
                'temperature': 0.2
            }
            r = requests.post('https://api.openai.com/v1/chat/completions', headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}, json=body, timeout=25)
            data = r.json() if r.ok else {}
            return data['choices'][0]['message']['content'] if isinstance(data, dict) and data.get('choices') else None
        except Exception:
            return None

    def generate_ai_decision(self, df, setup, info, news_items):
        last = df.iloc[-1]
        payload = {
            'symbol': self.current_symbol,
            'timeframe': self.current_interval,
            'price': float(last['Close']),
            'ema9': float(last['EMA9']) if pd.notna(last['EMA9']) else None,
            'ema20': float(last['EMA20']) if pd.notna(last['EMA20']) else None,
            'ema50': float(last['EMA50']) if pd.notna(last['EMA50']) else None,
            'vwap': float(last['VWAP']) if pd.notna(last['VWAP']) else None,
            'rsi': float(last['RSI']) if pd.notna(last['RSI']) else None,
            'macd': float(last['MACD']) if pd.notna(last['MACD']) else None,
            'macd_signal': float(last['MACD_signal']) if pd.notna(last['MACD_signal']) else None,
            'adx': float(last['ADX']) if pd.notna(last['ADX']) else None,
            'setup': setup,
            'news_titles': [x['title'] for x in news_items[:5]],
        }
        if self.ai_mode_var.get() == 'OpenAI API':
            external = self.call_openai_ai(payload)
            if external:
                return external
        return self.generate_builtin_ai_text(df, setup, news_items)

    def finish_ui_update(self, source, ai_text, status_text):
        self.data_source_var.set(f'資料來源：{source}')
        self.status_var.set(status_text)
        self.signal_var.set(f"訊號：{self.signal_result.get('setup', 'N/A')} | Bias：{self.signal_result.get('bias', 'N/A')} | RR：{self.signal_result.get('rr', 'N/A')} | 信心：{self.signal_result.get('confidence', 'N/A')}%")
        self.market_var.set(f"市場狀態：{self.signal_result.get('market_state', 'N/A')} | 新聞分數：{self.signal_result.get('news_score', 0)}")
        self.update_cards()
        self.draw_chart()
        self.write_summary()
        self.render_news()
        self.ai_box.delete('1.0', tk.END)
        self.ai_box.insert(tk.END, ai_text)
        self.log(status_text)

    def update_cards(self):
        if self.df is None or self.df.empty:
            return
        last = self.df.iloc[-1]
        s = self.signal_result or {}
        self.cards['price'].config(text=f"${last['Close']:.2f}")
        self.cards['ema9'].config(text=f"${last['EMA9']:.2f}" if pd.notna(last['EMA9']) else 'N/A')
        self.cards['ema20'].config(text=f"${last['EMA20']:.2f}" if pd.notna(last['EMA20']) else 'N/A')
        self.cards['vwap'].config(text=f"${last['VWAP']:.2f}" if pd.notna(last['VWAP']) else 'N/A')
        self.cards['rsi'].config(text=f"{last['RSI']:.1f}" if pd.notna(last['RSI']) else 'N/A')
        self.cards['macd'].config(text=f"{last['MACD']:.2f}" if pd.notna(last['MACD']) else 'N/A')
        self.cards['adx'].config(text=f"{last['ADX']:.1f}" if pd.notna(last['ADX']) else 'N/A')
        self.cards['vr'].config(text=str(s.get('vol_ratio', 'N/A')))
        self.cards['bias'].config(text=s.get('bias', 'N/A'))
        self.cards['setup'].config(text=s.get('setup', 'N/A'))
        self.cards['entry'].config(text=str(s.get('entry', 'N/A')))
        self.cards['stop'].config(text=str(s.get('stop', 'N/A')))
        self.cards['target'].config(text=str(s.get('target', 'N/A')))
        self.cards['rr'].config(text=str(s.get('rr', 'N/A')))
        self.cards['confidence'].config(text=f"{s.get('confidence', 'N/A')}%")
        self.cards['state'].config(text=s.get('market_state', 'N/A'))

    def get_display_df(self):
        if self.df is None or self.df.empty:
            return None
        df = self.df.copy()
        if self.current_interval == '10m':
            text = self.intraday_span_var.get()
            span = 90
            if '60' in text:
                span = 60
            elif '120' in text:
                span = 120
            df = df.tail(span)
        return df

    def get_volume_height_ratio(self):
        text = self.volume_ratio_var.get()
        if '細' in text:
            return 0.75
        if '大' in text:
            return 1.8
        return 1.2

    def redraw_chart_only(self):
        if self.df is not None and not self.df.empty:
            self.draw_chart()

    def draw_chart(self):
        for w in self.chart_area.winfo_children():
            w.destroy()
        display_df = self.get_display_df()
        if display_df is None or display_df.empty:
            return
        df = display_df.reset_index()
        date_col = 'Date' if 'Date' in df.columns else df.columns[0]
        df['Num'] = df[date_col].map(date2num)

        fig = Figure(figsize=(13, 5.6), dpi=100, facecolor=self.colors['bg'])
        ratio = self.get_volume_height_ratio()
        ax1 = fig.add_subplot(2, 1, 1)
        ax2 = fig.add_subplot(2, 1, 2, sharex=ax1)
        fig.subplots_adjust(hspace=0.05)
        ax1.set_position([0.06, 0.33, 0.90, 0.58])
        ax2.set_position([0.06, 0.11, 0.90, 0.14 * ratio])
        ax1.set_facecolor(self.colors['bg'])
        ax2.set_facecolor(self.colors['bg'])
        candle_width = 0.0035 if self.current_interval == '10m' else 0.6

        for i in range(len(df)):
            x = df['Num'].iloc[i]
            o = df['Open'].iloc[i]
            h = df['High'].iloc[i]
            l = df['Low'].iloc[i]
            c = df['Close'].iloc[i]
            color = self.colors['bull'] if c >= o else self.colors['bear']
            ax1.vlines(x, l, h, color=color, linewidth=1.0, zorder=2)
            ax1.bar(x, max(abs(c - o), 0.01), width=candle_width, bottom=min(o, c), color=color, edgecolor=color, alpha=0.95, zorder=3)

        ax1.plot(df['Num'], df['EMA9'], color='#60a5fa', linewidth=1.2, label='EMA9')
        ax1.plot(df['Num'], df['EMA20'], color='#22c55e', linewidth=1.4, label='EMA20')
        ax1.plot(df['Num'], df['EMA50'], color='#f59e0b', linewidth=1.4, label='EMA50')
        ax1.plot(df['Num'], df['VWAP'], color='#a78bfa', linewidth=1.1, linestyle='--', label='VWAP')

        setup = self.signal_result or {}
        if setup:
            for key, color, style in [('entry', '#38bdf8', '--'), ('stop', '#ef4444', ':'), ('target', '#22c55e', ':')]:
                val = setup.get(key)
                if val:
                    ax1.axhline(val, color=color, linestyle=style, linewidth=1.0, alpha=0.8)

        if self.trade_marks:
            base_offset = len(self.df) - len(display_df)
            for m in self.trade_marks:
                local_idx = m['idx'] - base_offset
                if 0 <= local_idx < len(df):
                    x = df['Num'].iloc[local_idx]
                    y = m['price']
                    if m['type'] == 'buy':
                        ax1.scatter([x], [y], marker='^', s=90, color='#22c55e', edgecolors='white', linewidths=0.8, zorder=6)
                    else:
                        ax1.scatter([x], [y], marker='v', s=90, color='#ef4444', edgecolors='white', linewidths=0.8, zorder=6)

        vol_colors = [self.colors['bull'] if c >= o else self.colors['bear'] for c, o in zip(df['Close'], df['Open'])]
        ax2.bar(df['Num'], df['Volume'], color=vol_colors, alpha=0.85, width=candle_width)
        ax1.legend(facecolor=self.colors['bg'], labelcolor='white', fontsize=9)
        locator = AutoDateLocator()
        formatter = DateFormatter('%m-%d %H:%M') if self.current_interval == '10m' else DateFormatter('%Y-%m-%d')
        ax2.xaxis.set_major_locator(locator)
        ax2.xaxis.set_major_formatter(formatter)
        latest = df.iloc[-1]
        info_line = f"O:{latest['Open']:.2f} H:{latest['High']:.2f} L:{latest['Low']:.2f} C:{latest['Close']:.2f}"
        ax1.text(0.01, 0.98, info_line, transform=ax1.transAxes, va='top', ha='left', color='white', fontsize=10, bbox=dict(facecolor='#0b1220', edgecolor='#334155', boxstyle='round,pad=0.3', alpha=0.85))
        for ax in (ax1, ax2):
            ax.grid(color='#334155', alpha=0.3)
            ax.tick_params(colors='#cbd5e1')
        for label in ax2.get_xticklabels():
            label.set_rotation(35)
            label.set_horizontalalignment('right')
        ax1.set_title(f"{self.current_symbol} 即時決策提示圖", color='white', fontsize=12)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=self.chart_area)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True)

        cross_v = ax1.axvline(df['Num'].iloc[-1], color='#94a3b8', linewidth=0.8, linestyle='--', alpha=0.5, visible=False)
        annot = ax1.annotate('', xy=(0, 0), xytext=(15, 15), textcoords='offset points', bbox=dict(boxstyle='round,pad=0.35', fc='#0b1220', ec='#475569', alpha=0.95), color='white', fontsize=9)
        annot.set_visible(False)
        pan = {'active': False, 'x': None, 'xlim': None}

        def on_zoom(event):
            if event.inaxes not in (ax1, ax2) or event.xdata is None:
                return
            cur_xlim = ax1.get_xlim()
            xdata = event.xdata
            scale = 0.8 if event.button == 'up' else 1.25
            new_width = (cur_xlim[1] - cur_xlim[0]) * scale
            relx = (cur_xlim[1] - xdata) / (cur_xlim[1] - cur_xlim[0])
            left = xdata - new_width * (1 - relx)
            right = xdata + new_width * relx
            ax1.set_xlim(left, right)
            ax2.set_xlim(left, right)
            fig.canvas.draw_idle()

        def on_press(event):
            if event.inaxes not in (ax1, ax2) or event.xdata is None:
                return
            pan['active'] = True
            pan['x'] = event.xdata
            pan['xlim'] = ax1.get_xlim()

        def on_release(event):
            pan['active'] = False
            pan['x'] = None
            pan['xlim'] = None

        def on_motion(event):
            if event.inaxes not in (ax1, ax2) or event.xdata is None:
                cross_v.set_visible(False)
                annot.set_visible(False)
                fig.canvas.draw_idle()
                return
            if pan['active'] and pan['x'] is not None:
                dx = event.xdata - pan['x']
                left = pan['xlim'][0] - dx
                right = pan['xlim'][1] - dx
                ax1.set_xlim(left, right)
                ax2.set_xlim(left, right)
                fig.canvas.draw_idle()
                return
            xs = df['Num'].to_numpy()
            idx = int(np.argmin(np.abs(xs - event.xdata)))
            row = df.iloc[idx]
            x = row['Num']
            y = row['Close']
            dt_text = pd.to_datetime(row[date_col]).strftime('%Y-%m-%d %H:%M' if self.current_interval == '10m' else '%Y-%m-%d')
            txt = f"{dt_text}\nO:{row['Open']:.2f}\nH:{row['High']:.2f}\nL:{row['Low']:.2f}\nC:{row['Close']:.2f}\nVol:{row['Volume']:.0f}"
            cross_v.set_xdata([x, x])
            cross_v.set_visible(True)
            annot.xy = (x, y)
            annot.set_text(txt)
            annot.set_visible(True)
            fig.canvas.draw_idle()

        fig.canvas.mpl_connect('scroll_event', on_zoom)
        fig.canvas.mpl_connect('button_press_event', on_press)
        fig.canvas.mpl_connect('button_release_event', on_release)
        fig.canvas.mpl_connect('motion_notify_event', on_motion)

    def write_summary(self):
        self.result.delete('1.0', tk.END)
        if self.df is None or self.df.empty or not self.signal_result:
            return
        s = self.signal_result
        last = self.df.iloc[-1]
        text = f"""
============================================================
實時決策提示
============================================================
股票代號：{self.current_symbol}
分析時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
模式：提示模式（不自動落單）

【即時訊號】
訊號：{s['setup']}
Bias：{s['bias']}
市場狀態：{s['market_state']}
信心：{s['confidence']}%

【交易計劃】
現價：{s['price']}
入場：{s['entry']}
止蝕：{s['stop']}
目標：{s['target']}
RR：{s['rr']}

【技術面】
EMA9：{last['EMA9']:.2f}
EMA20：{last['EMA20']:.2f}
EMA50：{last['EMA50']:.2f}
VWAP：{last['VWAP']:.2f}
RSI：{last['RSI']:.2f}
MACD：{last['MACD']:.2f} / {last['MACD_signal']:.2f}
ADX：{last['ADX']:.2f}
量比：{s['vol_ratio']}
新聞分數：{s['news_score']}

【理由】
"""
        for i, reason in enumerate(s['reasons'], 1):
            text += f"{i}. {reason}\n"
        text += """
【提醒】
1. 呢個版本只做提示，不會自動買賣。
2. 只有當 setup 夠集中先會顯示 BUY READY / SELL READY。
3. 真正落單前，記得再睇 spread、流動性同消息風險。
============================================================
"""
        self.result.insert(tk.END, text)

    def render_news(self):
        self.news_box.delete('1.0', tk.END)
        if not self.news_items:
            self.news_box.insert(tk.END, '未找到最新新聞資料。\n')
            return
        for i, item in enumerate(self.news_items, 1):
            score = item.get('sentiment_score', 0)
            label = '正面' if score > 0 else '負面' if score < 0 else '中性'
            self.news_box.insert(tk.END, f"[{i}] {item.get('title', '')}\n情緒：{label} ({score})\n日期：{item.get('pubDate', 'N/A')}\n連結：{item.get('link', '')}\n\n")

    def refresh_news_only(self):
        symbol = self.current_symbol or self.normalize_symbol(self.symbol_var.get())
        if not symbol:
            messagebox.showerror('錯誤', '請先輸入股票代號')
            return
        def worker():
            try:
                self.news_items = self.fetch_news(symbol, self.info if self.info else {})
                if self.df is not None and not self.df.empty:
                    self.signal_result = self.generate_trade_setup(self.df, self.info, self.news_items)
                    ai_text = self.generate_ai_decision(self.df, self.signal_result, self.info, self.news_items)
                    self.root.after(0, lambda: self.finish_ui_update(self.data_source_var.get().replace('資料來源：', ''), ai_text, '新聞已刷新'))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror('錯誤', str(e)))
        threading.Thread(target=worker, daemon=True).start()

    def manual_ai_refresh(self):
        if self.df is None or self.df.empty:
            messagebox.showinfo('提示', '請先啟動即時模式')
            return
        ai_text = self.generate_ai_decision(self.df, self.signal_result, self.info, self.news_items)
        self.ai_box.delete('1.0', tk.END)
        self.ai_box.insert(tk.END, ai_text)
        self.log('手動刷新 AI 決策')

    def on_close(self):
        self.stop_live_mode(silent=True)
        self.root.destroy()


if __name__ == '__main__':
    root = tk.Tk()
    app = StockRealtimePromptApp(root)
    root.mainloop()