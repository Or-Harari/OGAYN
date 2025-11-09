import AnalyticsChart from '@/components/chart/AnalyticsChart'
import { OrdersTable } from '@/components/OrdersTable'
export function Dashboard() {
  return (
    <div style={{display:'grid', gridTemplateRows:'auto auto 1fr', gap:12}}>
      <OrdersTable />
    </div>
  )
}
