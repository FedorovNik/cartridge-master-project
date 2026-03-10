async function updateTable() {
    const response = await fetch('/api/v1/cartridges');
    const data = await response.json();
    const tbody = document.querySelector('#inv-table tbody');
    tbody.innerHTML = '';

    data.forEach(item => {
        const barcodes = item.barcodes.map(b => `<span class="barcode-badge">${b}</span>`).join('');
        const row = `<tr>
            <td>${item.id}</td>
            <td>${item.name}</td>
            <td>${barcodes}</td>
            <td><strong>${item.stock}</strong></td>
        </tr>`;
        tbody.innerHTML += row;
    });
}
updateTable();
setInterval(updateTable, 15000);