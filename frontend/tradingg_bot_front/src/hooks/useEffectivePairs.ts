import { useEffect, useState } from 'react'
import { api } from '@/lib/api'

/**
 * Hook to get effective pairs for a bot config.
 * If RemotePairList is configured, fetches live pairs from scanner.
 * Otherwise returns static pairs from config.
 */
export function useEffectivePairs(config: any, userId?: number): string[] {
  const [pairs, setPairs] = useState<string[]>([])

  useEffect(() => {
    const staticPairs = Array.isArray(config?.pair_whitelist) 
      ? config.pair_whitelist 
      : Array.isArray(config?.pairs) 
      ? config.pairs 
      : []

    // Check if RemotePairList is configured
    const pairlists = config?.pairlists || []
    const remotePairlist = pairlists.find((pl: any) => pl.method === 'RemotePairList')

    if (!remotePairlist || !remotePairlist.scanner_id || !userId) {
      // No RemotePairList or missing scanner_id - use static pairs
      setPairs(staticPairs)
      return
    }

    // Fetch live pairs from scanner
    let cancelled = false
    const fetchLivePairs = async () => {
      try {
        const scannerId = remotePairlist.scanner_id
        const res = await api.get(`/scanners/users/${userId}/scanners/${scannerId}/pairlist`)
        const remotePairs = Array.isArray(res.data) ? res.data : []
        
        if (!cancelled) {
          setPairs(remotePairs.length > 0 ? remotePairs : staticPairs)
        }
      } catch (err) {
        console.warn('Failed to fetch remote pairlist, using static pairs:', err)
        if (!cancelled) {
          setPairs(staticPairs)
        }
      }
    }

    fetchLivePairs()
    return () => { cancelled = true }
  }, [config, userId])

  return pairs
}
