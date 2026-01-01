import { useEffect, useState } from "react";

export default function TradesPanel({ setLiveSubTab, cancelOpenOrder ,selected,liveTrades,liveTradesError,liveSubTab,liveTradesLoading,liveOpenOrders,liveOrdersError,setLiveRefreshKey, closeTrade, deleteTrade, closeAllTrades, historyTrades, historyLoading, historyError, historyDetails, loadTradeDetails, resetDryrunTrades, historyResetting, perfByPair, profitSummary, balance, balanceLoading, balanceError, periodRows}: {
  setLiveSubTab: (tab: 'trades' | 'orders' | 'closed') => void;
    liveTrades?: any[];
    liveTradesError?: string| null;
    liveSubTab: 'trades' | 'orders' | 'closed';
    liveTradesLoading: boolean;
    liveOpenOrders: any[] | null;
    liveOrdersError?: string | null;
    setLiveRefreshKey: React.Dispatch<React.SetStateAction<number>>;
    cancelOpenOrder: (botId: number, orderId: number | string) => void;
    selected: any | null;
    closeTrade: (botId: number, tradeId: number | string, mode: 'market' | 'limit') => void;
    deleteTrade: (botId: number, tradeId: number | string) => void;
    closeAllTrades: (botId: number, mode: 'market' | 'limit') => void;
    historyTrades: any[];
    historyLoading: boolean;
    historyError?: string | null;
    historyDetails: Record<string | number, any>;
    loadTradeDetails: (botId: number, tradeId: number | string) => void;
    resetDryrunTrades: (botId: number) => void;
    historyResetting: boolean;
    perfByPair: any[];
    profitSummary: any | null;
    balance: any | null;
    balanceLoading: boolean;
    balanceError?: string | null;
    periodRows: Array<{ day: string; profit: number; trades: number; inCount: number }>;
}) {

  useEffect(() => { setLiveRefreshKey(k => k + 1) }, [selected]);

  const [expandedOpenId, setExpandedOpenId] = useState<string | number | null>(null)
  const [expandedClosedId, setExpandedClosedId] = useState<string | number | null>(null)

  const getVal = (obj: any, keys: Array<string>, def: any = '-') => {
    for (const k of keys) {
      const v = obj?.[k]
      if (v != null) return v
    }
    return def
  }

  const formatTs = (ts: any) => {
    if (!ts) return '-'
    try {
      if (typeof ts === 'string' && ts.endsWith('Z')) return new Date(ts).toLocaleString()
      const n = Number(ts)
      if (isNaN(n)) return String(ts)
      const date = new Date(n > 1e12 ? n : n * 1000)
      return date.toLocaleString()
    } catch { return String(ts) }
  }

  const renderDetails = (detail: any) => {
    const id = getVal(detail, ['trade_id','id','tradeId'])
    const pair = getVal(detail, ['pair'])
    const openDate = formatTs(getVal(detail, ['open_date','open_time','date_open']))
    const stake = Number(getVal(detail, ['stake_amount','stake','stake_usdt','stake_value'], 0))
    const amount = Number(getVal(detail, ['amount','amount_filled'], 0))
    const openRate = Number(getVal(detail, ['open_rate','open_price'], 0))
    const currentRate = Number(getVal(detail, ['current_rate','rate_current','price_current'], 0))
    const profitAbs = Number(getVal(detail, ['profit_abs','close_profit_abs','realized_profit'], 0))
    const profitRatio = Number(getVal(detail, ['profit_ratio','close_profit','profit_percent'], 0))

    const stoploss = getVal(detail, ['stoploss','stop_loss','sl'])
    const initialStoploss = getVal(detail, ['initial_stoploss','stoploss_initial'])
    const curSlDist = getVal(detail, ['current_stoploss_dist','stoploss_current_dist'])

    const direction = getVal(detail, ['direction','side'])
    const fundingFees = getVal(detail, ['funding_fees','funding','funding_fee'], 0)
    const interestRate = getVal(detail, ['interest_rate','interest','borrow_rate'], 0)
    const liqPrice = getVal(detail, ['liquidation_price','liq_price','liquidation'], '-')

    const orders = Array.isArray(detail?.orders) ? detail.orders : []

    const red = { color: '#dc2626' }
    const green = { color: '#16a34a' }

    return (
      <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 10, background: '#f9fafb' }}>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap: 12 }}>
          <div>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>General</div>
            <div style={{ display:'grid', gridTemplateColumns:'160px 1fr', rowGap: 6 }}>
              <div>Trade Id</div><div>{id}</div>
              <div>Pair</div><div>{pair}</div>
              <div>Open date</div><div>{openDate}</div>
              <div>Stake</div><div>{stake ? `${stake} USDT` : '-'}</div>
              <div>Amount</div><div>{amount || '-'}</div>
              <div>Open rate</div><div>{openRate || '-'}</div>
              <div>Current rate</div><div>{currentRate || '-'}</div>
              <div>Total Profit</div><div style={profitAbs < 0 ? red : green}>{`${(profitRatio*100).toFixed(2)}% (${profitAbs.toFixed(3)})`}</div>
              <div>Current Profit</div><div style={profitAbs < 0 ? red : green}>{`${(profitRatio*100).toFixed(2)}% (${profitAbs.toFixed(3)})`}</div>
            </div>
          </div>
          <div>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Stoploss</div>
            <div style={{ display:'grid', gridTemplateColumns:'180px 1fr', rowGap: 6 }}>
              <div>Stoploss</div><div>{stoploss ?? '-'}</div>
              <div>Initial Stoploss</div><div>{initialStoploss ?? '-'}</div>
              <div>Current stoploss dist</div><div>{curSlDist ?? '-'}</div>
            </div>
            <div style={{ fontWeight: 600, marginTop: 12, marginBottom: 6 }}>Futures/Margin</div>
            <div style={{ display:'grid', gridTemplateColumns:'180px 1fr', rowGap: 6 }}>
              <div>Direction</div><div>{direction ?? '-'}</div>
              <div>Funding fees</div><div>{fundingFees ?? 0}</div>
              <div>Interest rate</div><div>{interestRate ?? 0}</div>
              <div>Liquidation Price</div><div>{liqPrice ?? '-'}</div>
            </div>
          </div>
        </div>
        <div style={{ marginTop: 8 }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Orders [{orders.length}]</div>
          {orders.length ? (
            <div style={{ maxHeight: 180, overflow:'auto', border:'1px solid #e5e7eb', borderRadius:6 }}>
              <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
                <thead>
                  <tr>
                    <th style={{ textAlign:'left', padding:6, borderBottom:'1px solid #e5e7eb' }}>Side</th>
                    <th style={{ textAlign:'right', padding:6, borderBottom:'1px solid #e5e7eb' }}>Amount</th>
                    <th style={{ textAlign:'right', padding:6, borderBottom:'1px solid #e5e7eb' }}>Price</th>
                    <th style={{ textAlign:'left', padding:6, borderBottom:'1px solid #e5e7eb' }}>Type</th>
                    <th style={{ textAlign:'left', padding:6, borderBottom:'1px solid #e5e7eb' }}>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((o: any, idx: number) => (
                    <tr key={idx}>
                      <td style={{ padding:6, borderBottom:'1px solid #f3f4f6' }}>{o?.ft_order_side || o?.side || o?.action || '-'}</td>
                      <td style={{ padding:6, textAlign:'right', borderBottom:'1px solid #f3f4f6' }}>{o?.amount ?? o?.amount_filled ?? '-'}</td>
                      <td style={{ padding:6, textAlign:'right', borderBottom:'1px solid #f3f4f6' }}>{o?.price ?? o?.safe_price ?? '-'}</td>
                      <td style={{ padding:6, borderBottom:'1px solid #f3f4f6' }}>{o?.order_type || o?.type || '-'}</td>
                      <td style={{ padding:6, borderBottom:'1px solid #f3f4f6' }}>{formatTs(o?.order_timestamp ?? o?.timestamp ?? o?.created_ts)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ fontSize:12, color:'#6b7280' }}>No orders.</div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div>
      <div style={{ marginTop: 12 }}>
        <div style={{ display:'flex', gap:8, borderBottom:'1px solid #e5e7eb', marginBottom:8, flexWrap:'wrap' }}>
          <button onClick={()=>setLiveSubTab('trades')} style={{ padding:'4px 8px', borderRadius:'6px 6px 0 0', border:'1px solid #e5e7eb', borderBottom: liveSubTab==='trades' ? '2px solid #3b82f6' : '1px solid #e5e7eb', background: liveSubTab==='trades' ? '#f0f7ff' : '#fff' }}>Open Trades ({liveTrades && liveTrades.length})</button>
          <button onClick={()=>{ setLiveSubTab('orders'); }} style={{ padding:'4px 8px', borderRadius:'6px 6px 0 0', border:'1px solid #e5e7eb', borderBottom: liveSubTab==='orders' ? '2px solid #3b82f6' : '1px solid #e5e7eb', background: liveSubTab==='orders' ? '#f0f7ff' : '#fff' }}>Open Orders ({liveOpenOrders && liveOpenOrders.length})</button>
          <button onClick={()=>setLiveSubTab('closed')} style={{ padding:'4px 8px', borderRadius:'6px 6px 0 0', border:'1px solid #e5e7eb', borderBottom: liveSubTab==='closed' ? '2px solid #3b82f6' : '1px solid #e5e7eb', background: liveSubTab==='closed' ? '#f0f7ff' : '#fff' }}>Closed Trades</button>
        </div>

        {liveSubTab === 'closed' && (
          <>
            {historyError && <div style={{ color: '#dc2626', marginBottom: 6 }}>{historyError}</div>}
            {historyLoading && <div style={{ fontSize: 12, color: '#6b7280' }}>Loading history…</div>}
            {!historyLoading && (!historyTrades || historyTrades.length === 0) && <div style={{ fontSize: 12, color: '#6b7280' }}>No closed trades.</div>}
            {!!historyTrades?.length && (
              <div style={{ maxHeight: 300, overflow: 'auto', border: '1px solid #e5e7eb', borderRadius: 6 }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: 'left', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Pair</th>
                      <th style={{ textAlign: 'right', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Open</th>
                      <th style={{ textAlign: 'right', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Close</th>
                      <th style={{ textAlign: 'right', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Profit</th>
                      <th style={{ textAlign: 'left', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Reason</th>
                      <th style={{ padding: 6, borderBottom: '1px solid #e5e7eb' }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {historyTrades.filter((t:any)=> t.close_date || String(t.status||'').toLowerCase()==='closed').map((t: any, idx: number) => {
                      const tradeId = t?.trade_id ?? t?.id ?? t?.tradeId
                      const opened = t.open_date ? new Date(t.open_date).toLocaleString() : '-'
                      const closed = t.close_date ? new Date(t.close_date).toLocaleString() : '-'
                      const pa = Number((t.profit_abs ?? t.close_profit_abs ?? t.realized_profit ?? 0))
                      const pr = Number((t.profit_ratio ?? t.close_profit ?? 0))
                      const prStr = `${pr.toFixed(2)} (${pa.toFixed(4)})`
                      return (
                        <>
                          <tr key={idx}>
                            <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>{t.pair || '-'}</td>
                            <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #f3f4f6' }}>{opened}</td>
                            <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #f3f4f6' }}>{closed}</td>
                            <td style={pa < 0 ? {fontWeight:'700',color:'red', padding:6, textAlign:'right'} : {color:'green', padding:6, textAlign:'right'}}>{prStr}</td>
                            <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>{t.sell_reason || '-'}</td>
                            <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>
                              <button onClick={() => { setExpandedClosedId(prev => prev === tradeId ? null : tradeId); if (tradeId != null && selected) loadTradeDetails(selected.id, tradeId) }} style={{ padding:'4px 8px', borderRadius:6, border:'1px solid #6b7280', background:'#fff', color:'#374151' }}>Details</button>
                            </td>
                          </tr>
                          {expandedClosedId === tradeId && (
                            <tr>
                              <td colSpan={6} style={{ padding:8 }}>
                                {renderDetails(historyDetails[tradeId] || t)}
                              </td>
                            </tr>
                          )}
                        </>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {liveSubTab === 'trades' && (
          <>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:6 }}>
              <h5 style={{ margin: 0 }}>Open Trades ({liveTrades && liveTrades.length})</h5>
              <div style={{ display:'inline-flex', gap:8 }}>
                <button onClick={() => selected && closeAllTrades(selected.id, 'market')} style={{ padding:'4px 8px', borderRadius:6, border:'1px solid #ef4444', background:'#fff', color:'#ef4444' }}>Close All (Market)</button>
                <button onClick={() => selected && closeAllTrades(selected.id, 'limit')} style={{ padding:'4px 8px', borderRadius:6, border:'1px solid #6b7280', background:'#fff', color:'#374151' }}>Close All (Limit)</button>
              </div>
            </div>
            {liveTradesError && <div style={{ color: '#dc2626', marginBottom: 6 }}>{liveTradesError}</div>}
            {liveTrades&&liveTrades.length === 0 && !liveTradesLoading && <div style={{ fontSize: 12, color: '#6b7280' }}>No open trades.</div>}
            {liveTrades&&liveTrades.length > 0 && (
              <div style={{ maxHeight: 260, overflow: 'auto', border: '1px solid #e5e7eb', borderRadius: 6 }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign:'left', padding:6, borderBottom:'1px solid #e5e7eb' }}>ID</th>
                      <th style={{ textAlign:'left', padding:6, borderBottom:'1px solid #e5e7eb' }}>Pair</th>
                      <th style={{ textAlign:'right', padding:6, borderBottom:'1px solid #e5e7eb' }}>Amount</th>
                      <th style={{ textAlign:'right', padding:6, borderBottom:'1px solid #e5e7eb' }}>Stake amount</th>
                      <th style={{ textAlign:'right', padding:6, borderBottom:'1px solid #e5e7eb' }}>Open rate</th>
                      <th style={{ textAlign:'right', padding:6, borderBottom:'1px solid #e5e7eb' }}>Current rate</th>
                      <th style={{ textAlign:'right', padding:6, borderBottom:'1px solid #e5e7eb' }}>Current profit %</th>
                      <th style={{ textAlign:'left', padding:6, borderBottom:'1px solid #e5e7eb' }}>Open date</th>
                      <th style={{ textAlign:'left', padding:6, borderBottom:'1px solid #e5e7eb' }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {liveTrades.map((t, idx) => {
                      const tradeId = t?.trade_id ?? t?.id ?? t?.tradeId
                      const amount = Number((t as any)?.amount || 0)
                      const stakeAmount = Number((t as any)?.stake_amount ?? (t as any)?.stake ?? 0)
                      const openRate = Number((t as any)?.open_rate ?? (t as any)?.open_price ?? 0)
                      const currentRate = Number((t as any)?.current_rate ?? (t as any)?.price_current ?? 0)
                      const pr = Number((t as any)?.profit_ratio ?? 0)
                      const openedStr = t.open_date ? new Date(t.open_date).toLocaleString() : '-'
                      const prPct = (pr*100).toFixed(2)
                      const isRed = pr < 0
                      return (
                        <>
                          <tr key={`row-${idx}`} onClick={() => {
                            setExpandedOpenId(prev => prev === tradeId ? null : tradeId)
                            if (tradeId != null && selected) loadTradeDetails(selected.id, tradeId)
                          }} style={{ cursor:'pointer' }}>
                            <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>{tradeId ?? '-'}</td>
                            <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>{t.pair || '-'}</td>
                            <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #f3f4f6' }}>{amount || '-'}</td>
                            <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #f3f4f6' }}>{stakeAmount || '-'}</td>
                            <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #f3f4f6' }}>{openRate || '-'}</td>
                            <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #f3f4f6' }}>{currentRate || '-'}</td>
                            <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6', color: isRed ? '#dc2626' : '#16a34a', textAlign: 'right' as any, fontWeight: isRed ? 700 : undefined }}>{prPct}%</td>
                            <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>{openedStr}</td>
                            <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>
                              {(() => {
                                const disabled = tradeId == null || !selected
                                return (
                                  <div style={{ display:'inline-flex', gap:6, flexWrap:'wrap' }}>
                                    <button onClick={(e) => {e.stopPropagation(); !disabled && closeTrade(selected!.id, tradeId!, 'market')}} disabled={disabled} style={{ padding:'4px 8px', borderRadius:6, border:'1px solid #ef4444', background: disabled ? '#f3f4f6' : '#fff', color:'#ef4444' }}>Close (Market)</button>
                                    <button onClick={(e) => {e.stopPropagation(); !disabled && closeTrade(selected!.id, tradeId!, 'limit')}} disabled={disabled} style={{ padding:'4px 8px', borderRadius:6, border:'1px solid #6b7280', background: disabled ? '#f3f4f6' : '#fff', color:'#374151' }}>Close (Limit)</button>
                                    <button onClick={(e) => {e.stopPropagation(); !disabled && deleteTrade(selected!.id, tradeId!)}} disabled={disabled} style={{ padding:'4px 8px', borderRadius:6, border:'1px solid #6b7280', background: disabled ? '#f3f4f6' : '#fff', color:'#374151' }}>Delete</button>
                                  </div>
                                )
                              })()}
                            </td>
                          </tr>
                          {expandedOpenId === tradeId && (
                            <tr key={`detail-${idx}`}>
                              <td colSpan={9} style={{ padding: 8, background:'#fff' }}>
                                {renderDetails(historyDetails[tradeId] || t)}
                              </td>
                            </tr>
                          )}
                        </>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {liveSubTab === 'orders' && (
          <>
            {liveOrdersError && <div style={{ color: '#dc2626', marginBottom: 6 }}>{liveOrdersError}</div>}
            <div style={{ display:'flex', gap:8, alignItems:'center', marginBottom:6 }}>
              <button onClick={()=>setLiveRefreshKey(k=>k+1)} style={{ padding:'4px 8px', borderRadius:6, border:'1px solid #e5e7eb', background:'#fff' }}>Refresh Snapshot</button>
            </div>
            {!liveOpenOrders || liveOpenOrders.length === 0 ? (
              <div style={{ fontSize: 12, color: '#6b7280' }}>No open orders.</div>
            ) : (
              <div style={{ maxHeight: 260, overflow: 'auto', border: '1px solid #e5e7eb', borderRadius: 6 }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: 'left', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Pair</th>
                      <th style={{ textAlign: 'left', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Side</th>
                      <th style={{ textAlign: 'right', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Amount</th>
                      <th style={{ textAlign: 'right', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Price</th>
                      <th style={{ textAlign: 'left', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Type</th>
                      <th style={{ textAlign: 'left', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Created</th>
                      <th style={{ padding: 6, borderBottom: '1px solid #e5e7eb' }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {liveOpenOrders.map((o, idx) => {
                      const tradeId = o.trade_id ?? o.tradeId ?? o.trade ?? null
                      const createdTs = o.order_timestamp ?? o.timestamp ?? o.created_ts
                      const createdStr = createdTs ? new Date((Number(createdTs) > 1e12 ? Number(createdTs) : Number(createdTs) * 1000)).toLocaleString() : (o.created_at || o.created || '-')
                      return (
                        <tr key={idx}>
                          <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>{o.pair || '-'}</td>
                          <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>{o.ft_order_side || o.side || o.action || '-'}</td>
                          <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #f3f4f6' }}>{o.amount ?? o.amount_filled ?? '-'}</td>
                          <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #f3f4f6' }}>{o.price ?? o.safe_price ?? '-'}</td>
                          <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>{o.order_type || o.type || '-'}</td>
                          <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>{createdStr}</td>
                          <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>
                            <button
                              onClick={() => tradeId != null && selected ? cancelOpenOrder(selected.id, tradeId) : void 0}
                              disabled={tradeId == null}
                              style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid #ef4444', background: tradeId == null ? '#f3f4f6' : '#fff', color: '#ef4444' }}
                            >
                              Cancel
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
