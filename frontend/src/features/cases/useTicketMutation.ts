import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { Ticket } from '../../shared/api/tickets'

/** Any call that returns the updated ticket: put it in the cache, refresh every ticket list. */
export function useTicketMutation<A>(fn: (args: A) => Promise<Ticket>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (t) => {
      qc.setQueryData(['tickets', t.id], t)
      return qc.invalidateQueries({ queryKey: ['tickets'], exact: true })
    },
  })
}
