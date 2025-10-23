import { OrdersTable } from '@/components/OrdersTable'
import { ChartPanel } from '@/components/chart/ChartPanel'

export function Dashboard() {
  return (
    <div style={{display:'grid', gridTemplateRows:'auto auto 1fr', gap:12}}>
      <ChartPanel />
      <OrdersTable />
    </div>
  )
}
