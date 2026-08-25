import { useMemo, useState } from 'react'

export function useSort<T>(rows: T[], getValue: (row: T, key: string) => string | number, initialKey: string, initialDir: 'asc' | 'desc' = 'desc') {
  const [key, setKey] = useState(initialKey)
  const [dir, setDir] = useState<'asc' | 'desc'>(initialDir)

  const sorted = useMemo(() => {
    const copy = [...rows]
    copy.sort((a, b) => {
      const va = getValue(a, key)
      const vb = getValue(b, key)
      let cmp: number
      if (typeof va === 'number' && typeof vb === 'number') {
        cmp = va - vb
      } else {
        cmp = String(va).localeCompare(String(vb))
      }
      return dir === 'asc' ? cmp : -cmp
    })
    return copy
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, key, dir])

  function toggle(nextKey: string) {
    if (nextKey === key) {
      setDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setKey(nextKey)
      setDir('desc')
    }
  }

  function arrow(colKey: string) {
    if (colKey !== key) return ''
    return dir === 'asc' ? 'sort-asc' : 'sort-desc'
  }

  return { sorted, key, dir, toggle, arrow }
}
