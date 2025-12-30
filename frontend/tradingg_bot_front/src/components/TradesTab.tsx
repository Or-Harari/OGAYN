import { useEffect } from "react";

export default function TradesTab({ setLiveSubTab, cancelOpenOrder ,selected,liveTrades,liveTradesError,liveSubTab,liveTradesLoading,liveOpenOrders,liveOrdersError,setLiveRefreshKey, closeTrade, deleteTrade, closeAllTrades, historyTrades, historyLoading, historyError, historyDetails, loadTradeDetails, resetDryrunTrades, historyResetting, perfByPair, profitSummary}: {
  setLiveSubTab: (tab: 'trades' | 'orders' | 'history' | 'performance') => void;
    liveTrades?: any[];
    liveTradesError?: string| null;
    liveSubTab: 'trades' | 'orders' | 'history' | 'performance';
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
}) {

  useEffect(() => {
      setLiveRefreshKey(k => k + 1)

  }, [selected]);

  return (
    <div>
          {/* Live Trades / Orders Tabs */}
                    <div style={{ marginTop: 12 }}>
                      <div style={{ display:'flex', gap:8, borderBottom:'1px solid #e5e7eb', marginBottom:8, flexWrap:'wrap' }}>
                        <button onClick={()=>setLiveSubTab('trades')} style={{ padding:'4px 8px', borderRadius:'6px 6px 0 0', border:'1px solid #e5e7eb', borderBottom: liveSubTab==='trades' ? '2px solid #3b82f6' : '1px solid #e5e7eb', background: liveSubTab==='trades' ? '#f0f7ff' : '#fff' }}>Open Trades ({liveTrades && liveTrades.length})</button>
                        <button onClick={()=>{ setLiveSubTab('orders'); /* open orders now derived from liveTrades */ }} style={{ padding:'4px 8px', borderRadius:'6px 6px 0 0', border:'1px solid #e5e7eb', borderBottom: liveSubTab==='orders' ? '2px solid #3b82f6' : '1px solid #e5e7eb', background: liveSubTab==='orders' ? '#f0f7ff' : '#fff' }}>Open Orders ({liveOpenOrders && liveOpenOrders.length})</button>
                        <button onClick={()=>setLiveSubTab('history')} style={{ padding:'4px 8px', borderRadius:'6px 6px 0 0', border:'1px solid #e5e7eb', borderBottom: liveSubTab==='history' ? '2px solid #3b82f6' : '1px solid #e5e7eb', background: liveSubTab==='history' ? '#f0f7ff' : '#fff' }}>Trades History</button>
                        <button onClick={()=>setLiveSubTab('performance')} style={{ padding:'4px 8px', borderRadius:'6px 6px 0 0', border:'1px solid #e5e7eb', borderBottom: liveSubTab==='performance' ? '2px solid #3b82f6' : '1px solid #e5e7eb', background: liveSubTab==='performance' ? '#f0f7ff' : '#fff' }}>Performance</button>
                      </div>
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
                                    <th style={{ textAlign: 'left', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Pair</th>
                                    <th style={{ textAlign: 'right', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Open Time</th>
                                    <th style={{ textAlign: 'right', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Profit Ratio</th>
                                    <th style={{ textAlign: 'right', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Profit Abs</th>
                                    <th style={{ textAlign: 'left', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Status</th>
                                    <th style={{ textAlign: 'left', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Action</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {liveTrades
                                    .map((t, idx) => (
                                      <tr key={idx}>
                                        <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>{t.pair || '-'}</td>
                                        <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #f3f4f6' }}>{t.open_date ? new Date(t.open_date).toLocaleString() : '-'}</td>
                                        <td  style={(Number(t.profit_ratio)) < 0?{fontWeight:'700',color:"red", padding: 6, textAlign: 'right'}: {color:"green", padding: 6, textAlign: 'right'}}>{(Number(t.profit_ratio || 0)).toFixed(1)}</td>
                                        <td style={(Number(t.profit_abs)) < 0?{fontWeight:'700',color:"red", padding: 6, textAlign: 'right'}: {color:"green", padding: 6, textAlign: 'right'}}>{(Number(t.profit_abs || 0)).toFixed(1)}</td>
                                        <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>{t.status || '-'}</td>
                                        <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>
                                          {(() => {
                                            const tradeId = t?.trade_id ?? t?.id ?? t?.tradeId
                                            const disabled = tradeId == null || !selected
                                            return (
                                              <div style={{ display:'inline-flex', gap:6, flexWrap:'wrap' }}>
                                                <button onClick={() => !disabled && closeTrade(selected!.id, tradeId, 'market')} disabled={disabled} style={{ padding:'4px 8px', borderRadius:6, border:'1px solid #ef4444', background: disabled ? '#f3f4f6' : '#fff', color:'#ef4444' }}>Close (Market)</button>
                                                <button onClick={() => !disabled && closeTrade(selected!.id, tradeId, 'limit')} disabled={disabled} style={{ padding:'4px 8px', borderRadius:6, border:'1px solid #6b7280', background: disabled ? '#f3f4f6' : '#fff', color:'#374151' }}>Close (Limit)</button>
                                                <button onClick={() => !disabled && deleteTrade(selected!.id, tradeId)} disabled={disabled} style={{ padding:'4px 8px', borderRadius:6, border:'1px solid #6b7280', background: disabled ? '#f3f4f6' : '#fff', color:'#374151' }}>Delete</button>
                                              </div>
                                            )
                                          })()}
                                        </td>
                                      </tr>
                                    ))}
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
                      {liveSubTab === 'history' && (
                        <>
                          {selected?.mode === 'dryrun' && (
                            <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:6 }}>
                              <button onClick={() => selected && !historyResetting && resetDryrunTrades(selected.id)} disabled={historyResetting} style={{ padding:'4px 8px', borderRadius:6, border:'1px solid #ef4444', background: historyResetting ? '#f3f4f6' : '#fff', color:'#ef4444' }}>
                                {historyResetting ? 'Resetting…' : 'Reset Dryrun Trades'}
                              </button>
                            </div>
                          )}
                          {historyError && <div style={{ color: '#dc2626', marginBottom: 6 }}>{historyError}</div>}
                          {historyLoading && <div style={{ fontSize: 12, color: '#6b7280' }}>Loading history…</div>}
                          {!historyLoading && (!historyTrades || historyTrades.length === 0) && <div style={{ fontSize: 12, color: '#6b7280' }}>No trade history.</div>}
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
                                  {historyTrades.map((t: any, idx: number) => {
                                    const tradeId = t?.trade_id ?? t?.id ?? t?.tradeId
                                    const opened = t.open_date ? new Date(t.open_date).toLocaleString() : '-'
                                    const closed = t.close_date ? new Date(t.close_date).toLocaleString() : '-'
                                    const pa = Number((t.profit_abs ?? t.close_profit_abs ?? t.realized_profit ?? 0))
                                    const pr = Number((t.profit_ratio ?? t.close_profit ?? 0))
                                    const prStr = `${pr.toFixed(2)} (${pa.toFixed(4)})`
                                    return (
                                      <tr key={idx}>
                                        <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>{t.pair || '-'}</td>
                                        <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #f3f4f6' }}>{opened}</td>
                                        <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #f3f4f6' }}>{closed}</td>
                                        <td style={pa < 0 ? {fontWeight:'700',color:'red', padding:6, textAlign:'right'} : {color:'green', padding:6, textAlign:'right'}}>{prStr}</td>
                                        <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>{t.sell_reason || '-'}</td>
                                        <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>
                                          <button onClick={() => tradeId != null && selected ? loadTradeDetails(selected.id, tradeId) : void 0} style={{ padding:'4px 8px', borderRadius:6, border:'1px solid #6b7280', background:'#fff', color:'#374151' }}>Details</button>
                                        </td>
                                      </tr>
                                    )
                                  })}
                                </tbody>
                              </table>
                            </div>
                          )}
                          {/* Simple details viewer */}
                          {historyDetails && Object.keys(historyDetails).length > 0 && (
                            <div style={{ marginTop: 8 }}>
                              <div style={{ fontWeight: 600, marginBottom: 4 }}>Trade Details</div>
                              <pre style={{ background:'#0b1020', color:'#d1d5db', padding:8, borderRadius:8, maxHeight:240, overflow:'auto' }}>{JSON.stringify(historyDetails, null, 2)}</pre>
                            </div>
                          )}
                        </>
                      )}
                      {liveSubTab === 'performance' && (
                        <>
                          {/* Overall summary */}
                          {profitSummary ? (
                            <div style={{ display:'grid', gridTemplateColumns:'200px 1fr', rowGap:6, marginBottom:8 }}>
                              <div><strong>Total Profit</strong></div><div>{Number(profitSummary?.profit_abs || 0).toFixed(4)} ({((profitSummary?.profit_ratio || 0) * 100).toFixed(2)}%)</div>
                              <div><strong>Closed Trades</strong></div><div>{profitSummary?.total_trades ?? '-'}</div>
                              <div><strong>Avg Profit Ratio</strong></div><div>{Number(profitSummary?.avg_profit_ratio || 0).toFixed(4)}</div>
                              <div><strong>Avg Duration</strong></div><div>{profitSummary?.avg_duration ?? '-'}</div>
                            </div>
                          ) : (
                            <div style={{ fontSize: 12, color:'#6b7280' }}>No profit summary.</div>
                          )}
                          {/* Performance by pair */}
                          {perfByPair && perfByPair.length > 0 ? (
                            <div style={{ maxHeight: 260, overflow:'auto', border:'1px solid #e5e7eb', borderRadius:6 }}>
                              <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
                                <thead>
                                  <tr>
                                    <th style={{ textAlign: 'left', padding:6, borderBottom:'1px solid #e5e7eb' }}>Pair</th>
                                    <th style={{ textAlign: 'right', padding:6, borderBottom:'1px solid #e5e7eb' }}>Profit Abs</th>
                                    <th style={{ textAlign: 'right', padding:6, borderBottom:'1px solid #e5e7eb' }}>Profit Ratio</th>
                                    <th style={{ textAlign: 'right', padding:6, borderBottom:'1px solid #e5e7eb' }}>Trades</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {perfByPair.map((p: any, idx: number) => (
                                    <tr key={idx}>
                                      <td style={{ padding:6, borderBottom:'1px solid #f3f4f6' }}>{p.pair || '-'}</td>
                                      <td style={{ padding:6, textAlign:'right', borderBottom:'1px solid #f3f4f6' }}>{Number(p.profit_abs || 0).toFixed(4)}</td>
                                      <td style={{ padding:6, textAlign:'right', borderBottom:'1px solid #f3f4f6' }}>{Number(p.profit_ratio || 0).toFixed(4)}</td>
                                      <td style={{ padding:6, textAlign:'right', borderBottom:'1px solid #f3f4f6' }}>{p.trades ?? p.count ?? '-'}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          ) : (
                            <div style={{ fontSize: 12, color:'#6b7280' }}>No performance data.</div>
                          )}
                        </>
                      )}
                    </div>
    </div>
  )
}   