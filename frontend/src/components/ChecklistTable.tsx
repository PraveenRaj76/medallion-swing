import type { ChecklistGroup } from '../types'

export function ChecklistTable({ title, group }: { title: string; group: ChecklistGroup }) {
  return (
    <div className="card">
      <h3>{title}</h3>
      <p className="card__muted">
        Subtotal {group.total_marks.toFixed(1)} / {group.max_marks} · cleared {group.cleared}/
        {group.total_filters} filters · {group.pct.toFixed(1)}%
      </p>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Filter</th>
              <th>Value</th>
              <th>Marks</th>
              <th>Status</th>
              <th>Why</th>
            </tr>
          </thead>
          <tbody>
            {group.items.map((item) => (
              <tr key={item.name}>
                <td style={{ fontWeight: 600 }}>{item.name}</td>
                <td className="tabular">{item.value}</td>
                <td className="tabular">
                  {item.marks.toFixed(1)}/{item.max_marks}
                </td>
                <td>
                  <span className={`chip ${item.passed ? 'good' : item.max_marks === 0 ? 'neutral' : 'bad'}`}>
                    {item.max_marks === 0 ? 'N/A' : item.passed ? 'PASS' : 'FAIL'}
                  </span>
                </td>
                <td style={{ color: 'var(--muted)', whiteSpace: 'normal', minWidth: 220 }}>{item.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
