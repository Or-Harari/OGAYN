// AnalyticsChart.tsx
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  createChart,
  IChartApi,
  SeriesMarker,
  UTCTimestamp,
  ColorType,
} from "lightweight-charts";

type CandleRow = { date: number | string; open: number; high: number; low: number; close: number; volume?: number };
type Indicators = Record<string, (number | null | undefined)[]>;
type Signals = Record<string, any>;
type Trade = Record<string, any>;

const palette = ["#2563eb","#16a34a","#f97316","#9333ea","#059669","#dc2626","#0ea5e9","#a16207"];
const isOscillator = (name: string) => /rsi|stoch|cci|mfi|macd|ao|awesome|osc/i.test(name);

function normalizeCandles(input: any): CandleRow[] {
  try {
    const hasDataObj = input && typeof input === "object" && "data" in input;
    const cols: string[] | undefined = hasDataObj
      ? (Array.isArray((input as any).columns) ? (input as any).columns
        : Array.isArray((input as any).all_columns) ? (input as any).all_columns
        : undefined)
      : undefined;
    const colsL = cols?.map((c) => String(c).toLowerCase());

    let rows = hasDataObj ? (input as any).data : input;
    if (!Array.isArray(rows) || rows.length === 0) return [];

    const parseDateMs = (d: any): number => {
      if (typeof d === "number") return d > 1e12 ? d : d * 1000;
      const ms = Date.parse(String(d));
      return Number.isFinite(ms) ? ms : NaN;
    };

    // objects
    if (typeof rows[0] === "object" && !Array.isArray(rows[0])) {
      return rows
        .map((r: any) => {
          const ms = parseDateMs(r?.date);
          const vol = r?.volume != null ? Number(r.volume) : undefined;
          return { date: ms, open: Number(r.open), high: Number(r.high), low: Number(r.low), close: Number(r.close), volume: vol };
        })
        .filter((x) => Number.isFinite(x.date));
    }

    // arrays (use columns mapping when available)
    if (Array.isArray(rows[0])) {
      const idxOf = (names: string[] | string, fallback: number): number => {
        if (!colsL) return fallback;
        const arr = Array.isArray(names) ? names : [names];
        for (const n of arr) {
          const i = colsL.findIndex((c) => c === n);
          if (i >= 0) return i;
        }
        return fallback;
      };
      const di = idxOf(["date", "timestamp", "time"], 0);
      const oi = idxOf("open", 1);
      const hi = idxOf("high", 2);
      const li = idxOf("low", 3);
      const ci = idxOf("close", 4);
      const vi = idxOf("volume", 5);

      return rows
        .map((r: any[]) => {
          const d0 = r?.[di];
          const ms = parseDateMs(d0);
          const vol = vi != null && vi >= 0 ? (r?.[vi] != null ? Number(r?.[vi]) : undefined) : undefined;
          return { date: ms, open: Number(r?.[oi]), high: Number(r?.[hi]), low: Number(r?.[li]), close: Number(r?.[ci]), volume: vol };
        })
        .filter((x) => Number.isFinite(x.date));
    }

    return [];
  } catch {
    return [];
  }
}

type Marker = SeriesMarker<UTCTimestamp>;

const buildSignalMarkers = (signals: Signals, times: UTCTimestamp[]): Marker[] => {
  const n = times.length;
  const toBool = (v: any) => v === true || v === 1 || v === "1" || v === "true";
  const buyArr  = Array.isArray(signals?.enter_long) ? signals.enter_long
                : Array.isArray(signals?.buy)        ? signals.buy : [];
  const sellArr = Array.isArray(signals?.exit_long)  ? signals.exit_long
                : Array.isArray(signals?.sell)       ? signals.sell : [];

  const buys  = Array.from({ length: n }, (_, i) => toBool(buyArr?.[i]));
  const sells = Array.from({ length: n }, (_, i) => toBool(sellArr?.[i]));

  const markers: Marker[] = [];
  for (let i = 0; i < n; i++) {
    const t = times[i];
    if (sells[i]) markers.push({ time: t, position: "aboveBar", color: "#ef4444", shape: "arrowDown", text: "SELL" });
    if (buys[i])  markers.push({ time: t, position: "belowBar", color: "#16a34a", shape: "arrowUp",   text: "BUY"  });
  }
  return markers;
};

const buildTradeMarkers = (trades: Trade[], times: UTCTimestamp[]): Marker[] => {
  const arr = times as number[];
  const tset = new Set<number>(arr);
  const toSec = (v: any): number | undefined => {
    if (v == null) return undefined;
    if (typeof v === "number") return v > 1e12 ? Math.floor(v / 1000) : Math.floor(v);
    const ms = Date.parse(v); return Number.isFinite(ms) ? Math.floor(ms / 1000) : undefined;
  };
  const nearest = (x: number): UTCTimestamp => {
    let lo = 0, hi = arr.length - 1;
    if (x <= arr[lo]) return arr[lo] as UTCTimestamp;
    if (x >= arr[hi]) return arr[hi] as UTCTimestamp;
    while (lo <= hi) {
      const m = (lo + hi) >> 1, v = arr[m];
      if (v === x) return v as UTCTimestamp;
      if (v < x) lo = m + 1; else hi = m - 1;
    }
    const a = arr[hi], b = arr[lo];
    return (x - a <= b - x ? a : b) as UTCTimestamp;
  };
  const snap = (sec?: number) =>
    sec == null ? undefined : (tset.has(sec) ? (sec as unknown as UTCTimestamp) : nearest(sec));

  const markers: Marker[] = [];
  for (const tr of trades || []) {
    const isShort = !!tr?.is_short;
    const entrySec = toSec(tr?.open_timestamp) ?? toSec(tr?.open_date);
    const exitSec  = toSec(tr?.close_timestamp) ?? toSec(tr?.close_date);
    const pr = typeof tr?.profit_ratio === "number"
      ? tr.profit_ratio
      : (tr?.profit_ratio != null ? parseFloat(tr.profit_ratio) : undefined);

    const et = snap(entrySec);
    if (et) {
      markers.push({
        time: et,
        position: isShort ? "aboveBar" : "belowBar",
        shape: isShort ? "arrowDown" : "arrowUp",
        color: isShort ? "#ef4444" : "#16a34a",
        text: `ENTRY${tr?.pair ? " " + tr.pair : ""}${tr?.open_rate ? ` @ ${tr.open_rate}` : ""}`,
      });
    }
    if (exitSec != null) {
      const xt = snap(exitSec);
      if (xt) {
        const color = typeof pr === "number" ? (pr >= 0 ? "#16a34a" : "#ef4444") : "#9ca3af";
        const pct = typeof pr === "number" ? ` ${(pr * 100).toFixed(2)}%` : "";
        markers.push({
          time: xt,
          position: "aboveBar",
          shape: "circle",
          color,
          text: `EXIT${pct}${tr?.close_rate ? ` @ ${tr.close_rate}` : ""}`,
        });
      }
    }
  }
  return markers;
};

// Try to derive indicators and signals when candles carry extended columns
function deriveFromExtendedCandles(candles: any): { indicators: Indicators; signals: Signals } {
  try {
    const baseCols = new Set(["date", "open", "high", "low", "close", "volume"]) as Set<string>;
    const signalCols = new Set(["enter_long", "exit_long", "buy", "sell"]) as Set<string>;
    const indicators: Indicators = {};
    const signals: Signals = {};

    if (!candles || typeof candles !== "object") return { indicators: {}, signals: {} };
    const cols: string[] = Array.isArray(candles.columns) ? candles.columns : Array.isArray(candles.all_columns) ? candles.all_columns : [];
    const rows: any[] = Array.isArray(candles.data) ? candles.data : [];
    if (!cols.length || !rows.length) return { indicators: {}, signals: {} };

    // Build lookup for array-row format
    const idx: Record<string, number> = {};
    cols.forEach((c, i) => (idx[c] = i));

    const addSeries = (name: string, vals: any[]) => {
      if (!vals || vals.length === 0) return;
      if (signalCols.has(name)) {
        signals[name] = vals.map(v => v === true || v === 1 || v === "1" || v === "true");
      } else if (!baseCols.has(name) && !name.startsWith("_")) {
        indicators[name] = vals.map((v) => {
          if (v == null) return null;
          const n = Number(v);
          return Number.isFinite(n) ? n : null;
        });
      }
    };

    if (rows.length && Array.isArray(rows[0])) {
      // Array-of-arrays shape
      cols.forEach((name) => {
        const colIdx = idx[name];
        if (typeof colIdx !== "number") return;
        const vals = rows.map(r => r?.[colIdx]);
        addSeries(name, vals);
      });
    } else if (rows.length && typeof rows[0] === "object") {
      // Array-of-objects shape
      cols.forEach((name) => {
        const vals = rows.map(r => (r ? r[name] : undefined));
        addSeries(name, vals);
      });
    }
    return { indicators, signals };
  } catch {
    return { indicators: {}, signals: {} };
  }
}

export type AnalyticsChartProps = {
  candles: any;
  indicators?: Indicators;
  signals?: Signals;
  trades?: Trade[];
  // initial visibility for indicator panes (by group name)
  initialVisibleIndicators?: Record<string, boolean>;
  showOscPane?: boolean;
  height?: number;
  oscHeight?: number;
  onReady?: (api: IChartApi) => void;
  fitContent?: boolean;
};

export default function AnalyticsChart({
  candles,
  indicators = {},
  signals = {},
  trades = [],
  initialVisibleIndicators,
  showOscPane = false,
  height = 420,
  oscHeight = 160,
  onReady,
  fitContent = true,
}: AnalyticsChartProps) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const oscWrapRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ReturnType<IChartApi["addCandlestickSeries"]> | null>(null);
  const volumeRef = useRef<ReturnType<IChartApi["addHistogramSeries"]> | null>(null);
  const indicatorSeriesRef = useRef<Map<string, ReturnType<IChartApi["addLineSeries"]>>>(new Map());
  const oscChartRef = useRef<IChartApi | null>(null);
  const oscSeriesRef = useRef<Map<string, ReturnType<IChartApi["addLineSeries"]>>>(new Map());
  const lastTimesRef = useRef<UTCTimestamp[]>([]);
  const lastCandlesRef = useRef<{ time: UTCTimestamp; open: number; close: number; vol?: number }[]>([]);

  // Indicator grouping and per-pane UI
  type IndicatorGroup = {
    name: string;
    keys: string[];
    kind: "macd" | "default";
  };

  const groupIndicators = (inds: Indicators): IndicatorGroup[] => {
    const names = Object.keys(inds || {});
    const used = new Set<string>();
    const groups: IndicatorGroup[] = [];
    // MACD special grouping
    const macdKeys = names.filter((k) => /macd/i.test(k));
    if (macdKeys.length) {
      const members = names.filter((k) => /macd|signal|hist/i.test(k));
      members.forEach((k) => used.add(k));
      if (members.length) groups.push({ name: "MACD", keys: members, kind: "macd" });
    }
    // Remaining: one pane per remaining indicator key (grouped by base token before underscore if variations)
    for (const k of names) {
      if (used.has(k)) continue;
      groups.push({ name: k, keys: [k], kind: "default" });
      used.add(k);
    }
    return groups;
  };

  const derived = React.useMemo(() => deriveFromExtendedCandles(candles), [candles]);
  const useIndicators = (indicators && Object.keys(indicators).length > 0) ? indicators : derived.indicators;
  const useSignals = (signals && Object.keys(signals).length > 0) ? signals : derived.signals;
  const indicatorGroups = useMemo(() => groupIndicators(useIndicators), [useIndicators]);
  const [visibleGroups, setVisibleGroups] = useState<Record<string, boolean>>(() => {
    const vis: Record<string, boolean> = {};
    for (const g of indicatorGroups) vis[g.name] = initialVisibleIndicators?.[g.name] ?? true;
    return vis;
  });
  useEffect(() => {
    // keep visibility keys in sync when groups change
    setVisibleGroups((prev) => {
      const next: Record<string, boolean> = {};
      for (const g of indicatorGroups) next[g.name] = prev[g.name] ?? initialVisibleIndicators?.[g.name] ?? true;
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [indicatorGroups.length]);

  // init charts
  useEffect(() => {
    if (!wrapRef.current) return;
    const el = wrapRef.current;

    const chart = createChart(el, { height });
    chart.applyOptions({
      watermark: { visible: false } as any,
      layout: { background: { type: ColorType.Solid, color: "transparent" } } as any,
      rightPriceScale: { visible: true },
    });
    const series = chart.addCandlestickSeries({
      upColor: "#26a69a",
      downColor: "#ef5350",
      borderVisible: false,
      wickUpColor: "#26a69a",
      wickDownColor: "#ef5350",
    });
    // Volume overlay on the same pane (separate scale margins at bottom)
    const vol = chart.addHistogramSeries({
      color: "#94a3b8",
      priceFormat: { type: "volume" as any },
      priceScaleId: "vol",
      scaleMargins: { top: 0.8, bottom: 0 },
    } as any);
    chartRef.current = chart;
    seriesRef.current = series;
    volumeRef.current = vol;
    onReady?.(chart);

    // optional second pane
    let osc: IChartApi | null = null;
    if (showOscPane && oscWrapRef.current) {
      osc = createChart(oscWrapRef.current, { height: oscHeight });
      osc.applyOptions({ watermark: { visible: false } as any });
      oscChartRef.current = osc;
    }

    // initial width (even if parent not fully laid out)
    const measureWidth = () => {
      const rect = (el as any).getBoundingClientRect ? (el as any).getBoundingClientRect() : null;
      const w = Math.max(100, Math.floor(rect?.width || el.clientWidth || el.offsetWidth || 0));
      return w > 0 ? w : 600;
    };
    try { chart.resize(measureWidth(), height); } catch {}
    if (oscChartRef.current) {
      try { oscChartRef.current.resize(measureWidth(), oscHeight); } catch {}
    }

    // keep width in sync
    let ro: ResizeObserver | null = null;
    try {
      if ("ResizeObserver" in window) {
        ro = new ResizeObserver((entries) => {
          const w = Math.max(100, Math.floor(entries[0]?.contentRect?.width || el.clientWidth || 0));
          if (w > 0) {
            try { chart.resize(w, height); } catch {}
            if (oscChartRef.current) {
              try { oscChartRef.current.resize(w, oscHeight); } catch {}
            }
          }
        });
        ro.observe(el);
      }
    } catch {}

    // if mounted while hidden tab, refit once it becomes visible
    const onVis = () => {
      if (document.visibilityState === "visible") {
        try {
          const w = measureWidth();
          chart.resize(w, height);
          chart.timeScale().fitContent();
          if (oscChartRef.current) oscChartRef.current.resize(w, oscHeight);
        } catch {}
      }
    };
    document.addEventListener("visibilitychange", onVis);

    return () => {
      document.removeEventListener("visibilitychange", onVis);
      try { ro?.disconnect(); } catch {}
      try { chart.remove(); } catch {}
      try { osc?.remove(); } catch {}
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // set candles
  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;

    const rows = normalizeCandles(candles);
    const data = rows.map((c) => {
      const ms = typeof c.date === "number" ? c.date : Date.parse(String(c.date));
      const t = Math.floor(ms / 1000) as UTCTimestamp;
      return { time: t, open: c.open, high: c.high, low: c.low, close: c.close };
    });

    series.setData(data);
    lastTimesRef.current = data.map((d) => d.time);
    lastCandlesRef.current = data.map((d, i) => ({ time: d.time, open: rows[i]?.open, close: rows[i]?.close, vol: rows[i]?.volume }))
      .filter((x) => x.time != null) as any;
    // set volume data
    const vol = volumeRef.current;
    if (vol && lastCandlesRef.current.length) {
      const vdata = lastCandlesRef.current.map((r) => ({
        time: r.time,
        value: r.vol ?? 0,
        color: (r.close ?? 0) >= (r.open ?? 0) ? "#16a34a" : "#ef4444",
      }));
      try { vol.setData(vdata as any); } catch {}
    }
    if (fitContent && data.length > 0) {
      try { chartRef.current?.timeScale().fitContent(); } catch {}
    }
  }, [candles, fitContent]);

  // helpers
  const ensureLineSeries = (name: string, idx: number) => {
    const useOsc = showOscPane && isOscillator(name);
    const targetChart = useOsc ? oscChartRef.current : chartRef.current;
    if (!targetChart) return null;
    const map = useOsc ? oscSeriesRef.current : indicatorSeriesRef.current;
    let s = map.get(name);
    if (!s) {
      s = targetChart.addLineSeries({ color: palette[idx % palette.length], lineWidth: 2 });
      map.set(name, s);
    }
    return s;
  };

  // set indicators
  useEffect(() => {
    const times = lastTimesRef.current;
    if (!chartRef.current || times.length === 0) return;

    // Remove any old indicator series from main and osc panes (legacy behavior)
    for (const s of indicatorSeriesRef.current.values()) {
      try { chartRef.current?.removeSeries(s); } catch {}
    }
    indicatorSeriesRef.current.clear();
    if (oscChartRef.current) {
      for (const s of oscSeriesRef.current.values()) {
        try { oscChartRef.current?.removeSeries(s); } catch {}
      }
      oscSeriesRef.current.clear();
    }
  }, [useIndicators, showOscPane]);

  // panes per indicator group
  const paneRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const paneCharts = useRef<Record<string, IChartApi | null>>({});
  const paneSeries = useRef<Record<string, any[]>>({});

  // helper to (re)build a group pane
  const rebuildGroupPane = (g: IndicatorGroup) => {
    const container = paneRefs.current[g.name];
    if (!container) return;
    // cleanup previous
    const prevChart = paneCharts.current[g.name];
    if (prevChart) {
      try { prevChart.remove(); } catch {}
      paneCharts.current[g.name] = null;
      paneSeries.current[g.name] = [];
    }
    // create chart
    const chart = createChart(container, { height: 160 });
    chart.applyOptions({ watermark: { visible: false } as any, layout: { background: { type: ColorType.Solid, color: "transparent" } } as any });
    paneCharts.current[g.name] = chart;
    const times = lastTimesRef.current;
    // build series for this group
    const keys = g.keys;
    const added: any[] = [];
    if (g.kind === "macd") {
      // Detect sub-series
      const pick = (regex: RegExp) => keys.find((k) => regex.test(k)) || keys.find((k) => regex.test(k.replace(/_/g, "")));
      const keyMacd = pick(/(^macd$|macd(?!.*(signal|hist)))/i) || keys.find(k => /macd/i.test(k) && !/signal|hist/i.test(k));
      const keySignal = pick(/signal/i);
      const keyHist = pick(/hist/i);
      // zero line
      const zero = chart.addLineSeries({ color: "#94a3b8", lineWidth: 1, lineStyle: 1 } as any);
      const zdata = times.map((t) => ({ time: t, value: 0 }));
      try { zero.setData(zdata as any); } catch {}
      added.push(zero);
      if (keyMacd && (useIndicators as any)[keyMacd]) {
        const macdS = chart.addLineSeries({ color: "#2563eb", lineWidth: 2 });
        const arr = (useIndicators as any)[keyMacd] as any[];
        const d = times.map((t, i) => {
          const v = arr?.[i];
          const n = v == null ? null : Number(v);
          return n == null || !Number.isFinite(n) ? null : { time: t, value: n };
        }).filter(Boolean) as any[];
        try { macdS.setData(d); } catch {}
        added.push(macdS);
      }
      if (keySignal && (useIndicators as any)[keySignal]) {
        const sigS = chart.addLineSeries({ color: "#ef4444", lineWidth: 2 });
        const arr = (useIndicators as any)[keySignal] as any[];
        const d = times.map((t, i) => {
          const v = arr?.[i];
          const n = v == null ? null : Number(v);
          return n == null || !Number.isFinite(n) ? null : { time: t, value: n };
        }).filter(Boolean) as any[];
        try { sigS.setData(d); } catch {}
        added.push(sigS);
      }
      if (keyHist && (useIndicators as any)[keyHist]) {
        const histS = chart.addHistogramSeries({ priceScaleId: "hist", color: "#94a3b8", scaleMargins: { top: 0.2, bottom: 0.1 } } as any);
        const arr = (useIndicators as any)[keyHist] as any[];
        const d = times.map((t, i) => {
          const v = arr?.[i];
          const n = v == null ? 0 : Number(v);
          const color = n >= 0 ? "#16a34a" : "#ef4444";
          return { time: t, value: n || 0, color };
        });
        try { histS.setData(d as any); } catch {}
        added.push(histS);
      }
    } else {
      // default: line per key
      keys.forEach((k, idx) => {
        const s = chart.addLineSeries({ color: palette[idx % palette.length], lineWidth: 2 });
        const arr = (useIndicators as any)[k] as any[];
        const d = times.map((t, i) => {
          const v = arr?.[i];
          const n = v == null ? null : Number(v);
          return n == null || !Number.isFinite(n) ? null : { time: t, value: n };
        }).filter(Boolean) as any[];
        try { s.setData(d); } catch {}
        added.push(s);
      });
    }
    paneSeries.current[g.name] = added;
  };

  // Rebuild panes on visibility or data change
  useEffect(() => {
    // remove panes that are no longer visible
    for (const [name, ch] of Object.entries(paneCharts.current)) {
      if (!visibleGroups[name]) {
        try { ch?.remove?.(); } catch {}
        delete paneCharts.current[name];
        delete paneSeries.current[name];
      }
    }
    // build/update visible panes
    for (const g of indicatorGroups) {
      if (!visibleGroups[g.name]) continue;
      rebuildGroupPane(g);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleGroups, indicatorGroups, useIndicators, candles]);

  // set markers (signals + trades)
  useEffect(() => {
    const series = seriesRef.current;
    const times = lastTimesRef.current;
    if (!series || times.length === 0) return;

    const sig = buildSignalMarkers(useSignals || {}, times);
    const trd = buildTradeMarkers((trades || []) as Trade[], times);

    const orderWeight = (m: Marker) => {
      const isCircle = m.shape === "circle";
      const above = m.position === "aboveBar";
      if (!above && m.shape === "arrowUp" && (m.text?.startsWith("ENTRY") ?? false)) return 0;
      if (!above && m.shape === "arrowUp") return 1;
      if (above && m.shape === "arrowDown") return 2;
      if (above && isCircle) return 3;
      return 5;
    };

    const all = [...sig, ...trd].sort(
      (a, b) => (a.time as number) - (b.time as number) || orderWeight(a) - orderWeight(b)
    );

    try { series.setMarkers(all); } catch {}
  }, [useSignals, trades]);

  return (
    <div>
      {/* Controls */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
        {indicatorGroups.map((g) => (
          <label key={g.name} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13 }}>
            <input
              type="checkbox"
              checked={!!visibleGroups[g.name]}
              onChange={(e) => setVisibleGroups((prev) => ({ ...prev, [g.name]: e.target.checked }))}
            />
            <span>{g.name}</span>
          </label>
        ))}
      </div>

      {/* Main price pane */}
      <div ref={wrapRef} style={{ width: "100%", minHeight: height }} />

      {/* Optional legacy osc pane (kept for backwards compat). */}
      {showOscPane && <div ref={oscWrapRef} style={{ width: "100%", minHeight: oscHeight, marginTop: 8 }} />}

      {/* Indicator panes */}
      <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
        {indicatorGroups
          .filter((g) => !!visibleGroups[g.name])
          .map((g) => (
            <div key={g.name}>
              <div style={{ fontSize: 12, color: "#64748b", marginBottom: 2 }}>{g.name}</div>
              <div
                ref={(el) => {
                  paneRefs.current[g.name] = el;
                }}
                style={{ width: "100%", minHeight: 160 }}
              />
            </div>
          ))}
      </div>
    </div>
  );
}
