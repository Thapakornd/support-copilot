import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../../shared/api/client'
import type { Ticket } from '../../shared/api/tickets'

/** What to tell the user when a case write fails. */
export function failureText(error: unknown) {
  const status = error instanceof ApiError ? error.status : 0
  if (status === 409 || status === 404) return 'This case changed before your update arrived. The latest version is shown.'
  if (status === 403) return 'You can’t change this case. Only support or the person who reported it can.'
  return 'Could not save the change. Try again.'
}

/** Any call that returns the updated ticket: put it in the cache, refresh every ticket list. */
export function useTicketMutation<A>(fn: (args: A) => Promise<Ticket>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    // a conflict means our copy is stale, so reload it
    onError: () => qc.invalidateQueries({ queryKey: ['tickets'] }),
    onSuccess: (t) => {
      qc.setQueryData(['tickets', t.id], t)
      return qc.invalidateQueries({ queryKey: ['tickets'], exact: true })
    },
  })
}
