// Simplified AnalyticsChart - candle-only, minimal logic (clean version)
import React, { useEffect, useMemo, useRef, useState, forwardRef, useImperativeHandle } from 'react';
import { Chart, CandlestickSeries, TimeScale, TimeScaleFitContentTrigger } from 'lightweight-charts-react-components';
import { UTCTimestamp } from 'lightweight-charts';

export type RawCandles = any;
export type NormalizedCandle = { time: UTCTimestamp; open: number; high: number; low: number; close: number };

function normalizeCandles(input: RawCandles): NormalizedCandle[] {
  try {
    const hasDataObj = input && typeof input === 'object' && 'data' in input;
    const cols: string[] | undefined = hasDataObj
      ? (Array.isArray(input.columns) ? input.columns : Array.isArray(input.all_columns) ? input.all_columns : undefined)
      : undefined;
    const colsL = cols?.map(c => String(c).toLowerCase());
    const rows: any[] = hasDataObj ? (input as any).data : (Array.isArray(input) ? input : []);
    if (!Array.isArray(rows) || rows.length === 0) return [];

    const parseDateMs = (d: any): number => {
      if (typeof d === 'number') return d > 1e12 ? d : d * 1000;
      const ms = Date.parse(String(d));
      return Number.isFinite(ms) ? ms : NaN;
    };

    if (typeof rows[0] === 'object' && !Array.isArray(rows[0])) {
      return rows
        .map((r: any) => {
          const ms = parseDateMs(r?.date ?? r?.time ?? r?.timestamp);
          return { time: Math.floor(ms / 1000) as UTCTimestamp, open: Number(r.open), high: Number(r.high), low: Number(r.low), close: Number(r.close) };
        })
        .filter(r => Number.isFinite(r.time as unknown as number));
    }

    if (Array.isArray(rows[0])) {
      const idxOf = (names: string[] | string, fallback: number): number => {
        if (!colsL) return fallback;
        const arr = Array.isArray(names) ? names : [names];
        for (const n of arr) { const i = colsL.indexOf(n); if (i >= 0) return i; }
        return fallback;
      };
      const di = idxOf(['date','timestamp','time'], 0);
      const oi = idxOf('open', 1);
      const hi = idxOf('high', 2);
      const li = idxOf('low', 3);
      const ci = idxOf('close', 4);
      return rows
        .map((r: any[]) => {
          const ms = parseDateMs(r?.[di]);
          return { time: Math.floor(ms / 1000) as UTCTimestamp, open: Number(r?.[oi]), high: Number(r?.[hi]), low: Number(r?.[li]), close: Number(r?.[ci]) };
        })
        .filter(r => Number.isFinite(r.time as unknown as number));
    }
    return [];
  } catch { return []; }
}

export interface AnalyticsChartProps {
  candles: RawCandles;
  seriesKey?: string;
  height?: number;
  fitContent?: boolean;
}

export interface AnalyticsChartHandle {
  setCandles: (bars: NormalizedCandle[]) => void;
  fit: () => void;
}

const AnalyticsChart = forwardRef<AnalyticsChartHandle, AnalyticsChartProps>(function AnalyticsChart({
  candles,
  seriesKey,
  height = 420,
  fitContent = true,
}: AnalyticsChartProps, ref) {
  const priceSeriesRef = useRef<any | null>(null);
  const [fitTriggerKey, setFitTriggerKey] = useState<number>(0);
  const didInitialFitRef = useRef(false);

  const processed = useMemo(() => {
    const rows = normalizeCandles(candles);
    const mapped = rows.map(r => ({ ...r })) as NormalizedCandle[];
    mapped.sort((a,b) => (a.time as number) - (b.time as number));
    const dedup: NormalizedCandle[] = [];
    let prev: number | null = null;
    for (const d of mapped) {
      const t = d.time as unknown as number;
      if (prev === t) continue;
      if (prev !== null && t <= prev) continue;
      dedup.push(d); prev = t;
    }
    return dedup;
  }, [candles, seriesKey]);

  const priceData = processed;
  const dataStamp = useMemo(() => `${priceData.length}-${priceData[priceData.length-1]?.time || 'na'}`, [processed]);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!priceSeriesRef.current) return;
    try { console.log(processed); (priceSeriesRef.current as any).setData?.(priceData); } catch {}
  }, [seriesKey, dataStamp,processed]);

  useEffect(() => {
    if (processed.length > 0 && !didInitialFitRef.current) {
      setFitTriggerKey(Date.now());
      didInitialFitRef.current = true;
      console.log(priceData);
    } else if (processed.length > 0 && seriesKey) {
      setFitTriggerKey(Date.now());
    }
  }, [processed, seriesKey]);

  // After chart creation, attempt to hide/remove the TradingView attribution logo (#tv-attr-logo)
  useEffect(() => {
    // Guard against SSR and missing DOM
    if (typeof document === 'undefined') return;

    let observer: MutationObserver | null = null;
    const styleTag = document.createElement('style');
    // As a fallback, hide globally (in case element is re-created)
    styleTag.setAttribute('data-analyticschart-tvlogo', '1');
    styleTag.textContent = `#tv-attr-logo { display: none !important; opacity: 0 !important; visibility: hidden !important; }`;
    document.head.appendChild(styleTag);

    const tryHide = (): boolean => {
      try {
        const scope = containerRef.current ?? document.body;
        const el = scope?.querySelector?.('#tv-attr-logo') || document.getElementById('tv-attr-logo');
        if (el) {
          // Prefer removal to ensure it doesn't intercept pointer events
          (el as HTMLElement).style.display = 'none';
          (el as HTMLElement).style.opacity = '0';
          (el as HTMLElement).style.visibility = 'hidden';
          // If safe, remove from DOM
          try { el.parentElement?.removeChild(el); } catch { /* ignore */ }
          return true;
        }
      } catch {}
      return false;
    };

    // First, attempt immediately and after short delays (some wrappers create DOM async)
    const t0 = setTimeout(tryHide, 0);
    const t1 = setTimeout(tryHide, 250);
    const t2 = setTimeout(tryHide, 750);

    // Observe mutations under the chart container to react when the element is injected later
    const root = containerRef.current ?? document.body;
    try {
      observer = new MutationObserver(() => {
        if (tryHide()) {
          observer?.disconnect();
          observer = null;
        }
      });
      observer.observe(root, { childList: true, subtree: true });
    } catch {}

    return () => {
      clearTimeout(t0 as any);
      clearTimeout(t1 as any);
      clearTimeout(t2 as any);
      try { observer?.disconnect(); } catch {}
      try {
        const s = document.head.querySelector('style[data-analyticschart-tvlogo="1"]');
        if (s) s.parentElement?.removeChild(s);
      } catch {}
    };
  }, [seriesKey, height]);

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <button type='button' onClick={() => setFitTriggerKey(Date.now())} style={{ fontSize: 12, padding: '4px 8px' }}>Fit</button>
      </div>
      <div ref={containerRef} style={{ width: '100%', height, position: 'relative' }}>
        {priceData.length > 1 ? priceData[0].open : null}
        <Chart options={{ height, layout: { background: { color: 'transparent' as any } }, timeScale: { timeVisible: true }, rightPriceScale: { autoScale: true } }}>
          <CandlestickSeries
            key={seriesKey}
            data={processed}
            options={{ upColor: '#26a69a', downColor: '#ef5350', borderVisible: false, wickUpColor: '#26a69a', wickDownColor: '#ef5350' }}
          />
          <TimeScale>
            {fitContent && fitTriggerKey !== 0 && <TimeScaleFitContentTrigger deps={[fitTriggerKey]} />}
          </TimeScale>
        </Chart>
        {processed.length === 0 && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#6b7280', fontSize: 13, pointerEvents: 'none' }}>
            No candle data to display
          </div>
        )}
      </div>
    </div>
  );
});

export default AnalyticsChart;
