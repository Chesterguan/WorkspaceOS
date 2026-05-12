import useSWR from 'swr';
import { config } from '@/lib/api';
import type { DomainConfig } from '@/lib/types';

// Domain config only changes on backend restart, so cache it aggressively —
// 5-minute dedup, no revalidate on focus or reconnect. Components that mount
// after the first fetch get the cached payload immediately.
export function useDomainConfig() {
  return useSWR<DomainConfig>('/config/domain', () => config.domain(), {
    revalidateOnFocus: false,
    revalidateOnReconnect: false,
    dedupingInterval: 1000 * 60 * 5,
  });
}
