class Table {
  constructor(config) {
    this.columns = config.columns;
    this.data = config.data || [];
    this.onRowClick = config.onRowClick;
  }

  render() {
    return `
      <div class="table-container">
        <table class="data-table">
          <thead>
            <tr>
              ${this.columns.map(col => `<th>${col.label}</th>`).join('')}
            </tr>
          </thead>
          <tbody>
            ${this.data.map((row, index) => `
              <tr onclick="window.Table.handleRowClick(${index})">
                ${this.columns.map(col => `<td>${this.renderCell(row, col)}</td>`).join('')}
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  renderCell(row, col) {
    if (col.render) {
      return col.render(row[col.key], row);
    }
    return row[col.key] || '-';
  }

  static handleRowClick(index) {
    console.log('Row clicked', index);
  }
}

window.Table = Table;
