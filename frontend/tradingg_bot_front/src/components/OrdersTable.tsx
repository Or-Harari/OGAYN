import * as React from 'react'
import { useQuery } from '@tanstack/react-query'
import { createColumnHelper, flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table'
import { api } from '@/lib/api'

interface OrderRow {
  id: string
  pair: string
  side: string
  price: number
  amount: number
  filled: number
  status: string
  created_at?: string
}

async function fetchOpenOrders(): Promise<OrderRow[]> {
  // Example: use the proxy to Freqtrade or your own endpoint summarizing orders
  const userId = 1
  const botId = 1
  const res = await api.get(`/users/${userId}/bots/${botId}/proxy/freqtrade/open_orders`)
  const raw = res.data || []
  // Map to view model as needed
  return (raw || []).map((o: any) => ({
     id: String(o.order_id || o.id || Math.random()),
     pair: o.pair,
     side: o.side || o.type,
     price: Number(o.price || o.rate || 0),
     amount: Number(o.amount || 0),
     filled: Number(o.filled || 0),
     status: o.status || 'open',
     created_at: o.order_date || o.date || undefined,
  }))
}

const columnHelper = createColumnHelper<OrderRow>()
const columns = [
  columnHelper.accessor('pair', { header: 'Pair' }),
  columnHelper.accessor('side', { header: 'Side' }),
  columnHelper.accessor('price', { header: 'Price', cell: info => info.getValue().toFixed(4) }),
  columnHelper.accessor('amount', { header: 'Amount', cell: info => info.getValue().toFixed(4) }),
  columnHelper.accessor('filled', { header: 'Filled', cell: info => info.getValue().toFixed(4) }),
  columnHelper.accessor('status', { header: 'Status' }),
  columnHelper.accessor('created_at', { header: 'Created' }),
]

export function OrdersTable() {
  const { data = [], isLoading, error } = useQuery({
    queryKey: ['open-orders'],
    queryFn: fetchOpenOrders,
    refetchInterval: 5_000,
  })

  const table = useReactTable({ data, columns, getCoreRowModel: getCoreRowModel() })

  if (isLoading) return <div>Loading orders…</div>
  if (error) return <div>Error loading orders.</div>

  return (
    <div>
      <h3>Open Orders</h3>
      <table className="table">
        <thead>
          {table.getHeaderGroups().map(hg => (
            <tr key={hg.id}>
              {hg.headers.map(h => (
                <th key={h.id} colSpan={h.colSpan}>
                  {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map(row => (
            <tr key={row.id}>
              {row.getVisibleCells().map(cell => (
                <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
