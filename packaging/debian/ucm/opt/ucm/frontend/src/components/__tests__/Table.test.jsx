import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Table } from '../Table'

const mockColumns = [
  { key: 'name', label: 'Name' },
  { key: 'status', label: 'Status' },
]

const mockData = [
  { id: 1, name: 'Item 1', status: 'Active' },
  { id: 2, name: 'Item 2', status: 'Inactive' },
  { id: 3, name: 'Item 3', status: 'Active' },
]

describe('Table Component', () => {
  it('renders table headers', () => {
    render(<Table columns={mockColumns} data={mockData} />)
    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.getByText('Status')).toBeInTheDocument()
  })

  it('renders table data', () => {
    render(<Table columns={mockColumns} data={mockData} />)
    expect(screen.getByText('Item 1')).toBeInTheDocument()
    expect(screen.getByText('Item 2')).toBeInTheDocument()
    expect(screen.getAllByText('Active').length).toBeGreaterThan(0)
  })

  it('shows empty state when no data', () => {
    render(<Table columns={mockColumns} data={[]} emptyMessage="No items" />)
    expect(screen.getByText('No items')).toBeInTheDocument()
  })

  it('shows loading state', () => {
    render(<Table columns={mockColumns} data={[]} loading={true} />)
    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('handles row click', () => {
    const handleClick = vi.fn()
    render(<Table columns={mockColumns} data={mockData} onRowClick={handleClick} />)
    
    fireEvent.click(screen.getByText('Item 1'))
    expect(handleClick).toHaveBeenCalledWith(mockData[0])
  })

  it('highlights selected row', () => {
    render(
      <Table 
        columns={mockColumns} 
        data={mockData} 
        selectedId={2}
        idKey="id"
      />
    )
    const row = screen.getByText('Item 2').closest('tr')
    expect(row.className).toContain('row-selected')
  })

  it('supports custom column renderer', () => {
    const columnsWithRender = [
      { key: 'name', label: 'Name', render: (val) => <strong data-testid="strong">{val}</strong> },
    ]
    render(<Table columns={columnsWithRender} data={mockData} />)
    expect(screen.getAllByTestId('strong')[0]).toBeInTheDocument()
  })

  it('handles sorting', () => {
    render(<Table columns={mockColumns} data={mockData} sortable={true} />)
    
    // Click on header to sort
    fireEvent.click(screen.getByText('Name'))
    
    // Data should still be present
    expect(screen.getByText('Item 1')).toBeInTheDocument()
  })

  it('handles selectable rows', () => {
    const onSelectionChange = vi.fn()
    render(
      <Table 
        columns={mockColumns} 
        data={mockData} 
        selectable={true}
        onSelectionChange={onSelectionChange}
      />
    )
    
    const checkboxes = screen.getAllByRole('checkbox')
    expect(checkboxes.length).toBeGreaterThan(0)
  })
})
